import base64
import io
import json
from pathlib import Path
import sys
import zipfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine/scripts'))
import build
import review_packet as review
import upload


@pytest.fixture
def project(tmp_path, monkeypatch):
    actual = build.ROOT
    monkeypatch.setattr(build, 'ROOT', tmp_path)
    (tmp_path / 'engine').symlink_to(actual / 'engine', target_is_directory=True)
    mdir = tmp_path / 'manuscripts/TEST'
    (mdir / 'source').mkdir(parents=True)
    (mdir / 'article.qmd').write_text('---\ntitle: Test\n---\n\nThis is teh test.\n')
    (mdir / '_metadata.yml').write_text('r2: {}\n')
    (mdir / 'references.bib').write_text('')
    (mdir / 'source/original.md').write_text('This is the test.\n')
    monkeypatch.setattr(review.validate_meta, 'check', lambda p: [])
    return mdir


def result_for(root):
    packet = json.loads((root / 'packet.json').read_text())
    return dict(packet_id=packet['packet_id'], passes=['proofreading'], summary='One typo.', limitations=['No proof review.'],
                coverage=[dict(file=f, status='partial', notes='Text only.') for f in packet['evidence']],
                issues=[dict(pass_='proofreading')])


def valid_result(root):
    result = result_for(root)
    result['issues'] = [{'pass': 'proofreading', 'severity': 'warning', 'category': 'spelling',
        'file': 'canonical/article.qmd', 'quote': 'teh test', 'source_file': '', 'source_quote': '',
        'location': 'First paragraph', 'explanation': 'Transposed letters.', 'suggested_correction': 'the test', 'confidence': 'high'}]
    return result


def test_portable_export_and_returned_evidence(project):
    root = review.packet(project)
    with zipfile.ZipFile(root / 'review-package.zip') as z:
        assert 'review-package/originals/original.md' in z.namelist()
        assert 'review-package/review.py' in z.namelist()
        assert not any(str(project) in n for n in z.namelist())
    result = valid_result(root)
    assert review.portable.validate(root, result) == []
    report = review.import_result(project, result)
    assert report['current']
    (project / 'source/original.md').write_text('Changed original')
    assert not review.review_state(project)['current']
    assert (project / 'article.qmd').read_text().endswith('This is teh test.\n')


def test_reject_fabricated_quotes_wrong_package_missing_coverage(project):
    root = review.packet(project)
    for mutation in ['quote', 'id', 'coverage']:
        result = valid_result(root)
        if mutation == 'quote':
            result['issues'][0]['quote'] = 'not in this manuscript'
        elif mutation == 'id':
            result['packet_id'] = '0' * 32
        else:
            result['coverage'].pop()
        with pytest.raises(ValueError):
            review.portable.validate(root, result)
    (root / 'canonical/article.qmd').write_text('Altered packet')
    with pytest.raises(ValueError, match='changed or missing'):
        review.portable.validate(root, valid_result(root))


def test_multimodal_openrouter_includes_labeled_bytes(project):
    (project / 'figure.png').write_bytes(b'\x89PNG\r\n\x1a\nexample')
    root = review.packet(project)
    packet = review.portable.verify(root)
    payload, count = review.portable.openrouter_payload(root, packet, 'Review', 'vision/model', 1000)
    assert count == 1
    body = json.loads(payload)
    content = body['messages'][1]['content']
    assert content[1]['text'] == 'Evidence image: canonical/figure.png'
    encoded = content[2]['image_url']['url'].split(',')[1]
    assert base64.b64decode(encoded) == (project / 'figure.png').read_bytes()
    assert body['response_format']['json_schema']['strict'] is True


def encoded(name, content):
    return {'name': name, 'data': base64.b64encode(content).decode()}


def archive(name, content):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        z.writestr(name, content)
    return stream.getvalue()


def test_upload_creates_new_manuscript_preserves_original(project):
    files = [encoded('paper.qmd', b'---\ntitle: Upload test\n---\n\nOriginal prose.\n')]
    assert upload.create('NEW.001', files) == 'NEW.001'
    mdir = build.ROOT / 'manuscripts/NEW.001'
    assert (mdir / 'article.qmd').read_bytes() == (mdir / 'source/paper.qmd').read_bytes()
    with pytest.raises(ValueError, match='already exists'):
        upload.create('NEW.001', files)
    assert (mdir / '_metadata.yml').read_text() == 'r2:\n  article-id: NEW.001\n'


def test_upload_rejects_unsafe_archive_and_pdf_only(project):
    with pytest.raises(ValueError, match='unsafe path'):
        upload.create('BAD', [encoded('source.zip', archive('../escape.qmd', 'text'))])
    with pytest.raises(ValueError, match='editable'):
        upload.create('PDF', [encoded('proof.pdf', b'%PDF')])
    assert not (build.ROOT / 'manuscripts/BAD').exists()
    assert not (build.ROOT / 'manuscripts/PDF').exists()


def test_upload_ambiguous_project_requires_main(project):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        z.writestr('old.qmd', 'Old draft')
        z.writestr('accepted.qmd', 'Accepted manuscript')
    files = [encoded('source.zip', stream.getvalue())]
    with pytest.raises(ValueError, match='Main source'):
        upload.create('AMBIG', files)
    assert upload.create('AMBIG', files, 'accepted.qmd') == 'AMBIG'
    assert (build.ROOT / 'manuscripts/AMBIG/article.qmd').read_text() == 'Accepted manuscript'


def test_agent_commands_and_envelope_parsing(tmp_path):
    codex = review.portable.command('codex', tmp_path, 'prompt', None, tmp_path / 'out')
    assert codex[codex.index('--sandbox')+1] == 'read-only'
    claude = review.portable.command('claude', tmp_path, 'prompt', None, tmp_path / 'out')
    assert claude[claude.index('--tools')+1] == 'Read,Glob,Grep'
    with pytest.raises(ValueError, match='Flash'):
        review.portable.command('agy', tmp_path, 'prompt', 'Gemini 3.1 Pro', tmp_path / 'out')
    assert review.portable.parse_result('{"structured_output":{"issues":[]}}') == {'issues': []}


@pytest.mark.parametrize('provider', ['codex', 'claude', 'agy', 'openrouter'])
def test_runner_round_trip_without_provider_calls(project, monkeypatch, provider):
    from types import SimpleNamespace
    root = review.packet(project)
    expected = valid_result(root)
    args = SimpleNamespace(provider=provider, model='Gemini 3.8 Flash (High)' if provider == 'agy' else 'test/model',
                           passes=['proofreading'], max_tokens=1000, max_request_mb=32, send=True)
    def fake_run(cmd, **kwargs):
        if provider == 'codex':
            Path(cmd[cmd.index('-o') + 1]).write_text(json.dumps(expected))
        return SimpleNamespace(returncode=0, stdout=json.dumps({'structured_output': expected}) if provider == 'claude' else json.dumps(expected), stderr='')
    monkeypatch.setattr(review.portable.subprocess, 'run', fake_run)
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-only-not-a-secret')
    def fake_open(request, **kwargs):
        body = json.loads(request.data)
        assert body['model'] == 'test/model'
        return io.BytesIO(json.dumps({'choices': [{'message': {'content': json.dumps(expected)}}], 'usage': {'total_tokens': 123}}).encode())
    monkeypatch.setattr(review.portable.urllib.request, 'urlopen', fake_open)
    review.portable.run(args, root)
    output = list(root.glob('results/*/review.json'))
    assert len(output) == 1 and json.loads(output[0].read_text()) == expected


def test_workspace_upload_export_import_routes(project, monkeypatch):
    import threading
    import urllib.request
    import workspace
    monkeypatch.setattr(workspace, 'ROOT', build.ROOT)
    server = workspace.ThreadingHTTPServer(('127.0.0.1', 0), workspace.Handler)
    port = server.server_address[1]
    server.allowed_hosts = {f'127.0.0.1:{port}'}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def request(path, data=None):
        req = urllib.request.Request(f'http://127.0.0.1:{port}' + path,
            data=json.dumps(data).encode() if data else None,
            headers={'X-Workspace-Token': workspace.TOKEN, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as response:
            return response.read()
    try:
        payload = {'article': 'WEB', 'files': [encoded('accepted.qmd', b'---\ntitle: Web upload\n---\nThis is teh test.')]}
        assert json.loads(request('/api/upload', payload))['article'] == 'WEB'
        download = json.loads(request('/api/review-package', {'article': 'WEB'}))['download']
        with zipfile.ZipFile(io.BytesIO(request(download))) as z:
            packet = json.loads(z.read('review-package/packet.json'))
            assert packet['article_id'] == 'WEB'
        root = build.ROOT / '_build/llm-review/WEB' / packet['packet_id']
        result = json.loads(request('/api/review-import', {'article': 'WEB', 'result': valid_result(root)}))
        assert result['review']['current']
        assert json.loads(request('/api/manuscript/WEB'))['review']['result']['issues'][0]['category'] == 'spelling'
    finally:
        server.shutdown()
        server.server_close()


def test_import_baseline_is_frozen_and_not_a_source_candidate(project):
    import normalize
    project.joinpath('article.qmd').unlink()
    normalize.main(str(project))
    baseline = project / 'source/initial-import/article.qmd'
    original = baseline.read_text()
    (project / 'article.qmd').write_text('Edited canonical')
    normalize.main(str(project))
    assert baseline.read_text() == original
    assert normalize.find_source(project).name == 'original.md'
    exported = review.packet(project)
    assert (exported / 'baseline/article.qmd').read_text() == original


def test_accept_reject_and_stale_decisions(project):
    import editorial
    root = review.packet(project)
    state = review.import_result(project, valid_result(root))
    files = {n: (project/n).read_text() for n in ['article.qmd','_metadata.yml','references.bib']}
    def save(updated):
        for name, text in updated.items(): (project/name).write_text(text)
    editorial.decide(project, state['report_id'], state['result']['packet_id'], 0, 'accepted', files, save)
    assert 'the test' in (project/'article.qmd').read_text()
    assert review.review_state(project)['decisions']['0']['decision'] == 'accepted'
    with pytest.raises(ValueError, match='already'):
        editorial.decide(project, state['report_id'], state['result']['packet_id'], 0, 'accepted', files, save)
    root = review.packet(project)
    result = valid_result(root)
    result['issues'][0]['quote'] = 'the test'
    state = review.import_result(project, result)
    (project/'article.qmd').write_text('Outside edit')
    with pytest.raises(ValueError, match='stale'):
        editorial.decide(project, state['report_id'], state['result']['packet_id'], 0, 'accepted', files, save)


def test_comments_follow_unrelated_edits_and_mark_changed_anchor(project):
    import editorial
    text = 'A'*50 + 'selected passage' + 'B'*50
    files = {'article.qmd': text}
    result = editorial.comment(project, files, dict(file='article.qmd',start=50,end=66,text='Please clarify.'))
    assert result[0]['current']
    shifted = editorial.comments(project, {'article.qmd':'Intro\n'+text})
    assert shifted[0]['current'] and shifted[0]['start'] == 56
    assert not editorial.comments(project, {'article.qmd':text.replace('selected','changed')})[0]['current']
    assert editorial.comment(project,files,{'resolve':result[0]['id']})[0]['resolved']


def test_metadata_form_preserves_body_unknown_fields_and_authors(project):
    import editorial
    files = {'article.qmd':'---\ntitle: Test\ncustom: keep\nauthor:\n- name: {given: A, family: B}\n  orcid: verified\n---\n\nBody $x$ [@key].\n', '_metadata.yml':'r2:\n  doi: 10.1234/test\n', 'references.bib':'unchanged'}
    form = editorial.details(files)
    form['article']['author'][0]['name']['given'] = 'Alex'
    changed = editorial.details(files,form)
    assert changed['article.qmd'].split('---',2)[2] == files['article.qmd'].split('---',2)[2]
    assert 'custom: keep' in changed['article.qmd'] and 'orcid: verified' in changed['article.qmd']
    assert changed['references.bib'] == files['references.bib']


def test_figure_import_preserves_native_citations_and_reference_labels(tmp_path):
    import shutil
    import normalize
    import subprocess
    if not shutil.which('pdftoppm'):
        pytest.skip('Poppler required for PDF figure conversion')
    work=tmp_path/'LATEX'
    source=work/'source'
    source.mkdir(parents=True)
    shutil.copyfile(build.ROOT/'manuscripts/Stylometry/figures/reproduction_summary.pdf',source/'plot.pdf')
    (source/'main.tex').write_text(r'''\documentclass{article}
\begin{document}
\section{Method\label{sec:method}}
See Section~\ref{sec:method} and Figure~\ref{fig:plot}.
\begin{figure}\includegraphics{plot.pdf}\caption{Result from \cite{smith2020}.\label{fig:plot}}\end{figure}
\end{document}''')
    normalize.main(str(work))
    text=(work/'article.qmd').read_text()
    assert '<figure' not in text and '<embed' not in text
    assert '@smith2020' in text and 'figures/plot.png' in text and '[1](#sec:method)' in text
    xml=subprocess.check_output(['quarto','pandoc',str(work/'article.qmd'),'-t','jats'],text=True)
    assert '<fig' in xml and '<graphic' in xml


def test_review_parser_accepts_agy_envelope_and_rejects_empty_response():
    assert review.portable.parse_result(json.dumps({'response':json.dumps({'issues':[]})})) == {'issues':[]}
    with pytest.raises(ValueError,match='denied tools'):
        review.portable.parse_result(json.dumps({'response':'','denied_actions':[{'display_name':'GrepSearch'}]}))


def test_emf_bitmap_and_blank_conversion_guard(tmp_path):
    from metafile import embedded_bitmap, require_visible
    from PIL import Image
    source = build.ROOT/'manuscripts/Hussey/figures/media/image1.emf'
    dest=tmp_path/'plot.png'
    assert embedded_bitmap(source,dest)
    require_visible(dest)
    assert Image.open(dest).size == (720,288)
    Image.new('RGBA',(10,10),(0,0,0,0)).save(dest)
    with pytest.raises(ValueError,match='blank'):
        require_visible(dest)


def test_word_caption_and_bibliography_preservation(tmp_path):
    import normalize, subprocess
    assert normalize._word_captions('**Figure 4.** A flowchart.\n\n![Description automatically generated](image.png){width="2in"}') == '![A flowchart.](image.png){#fig-import-4}'
    records=[{'id':'corporate','type':'article-journal','title':'Test','author':[{'literal':'Research and Science Group'}],'DOI':'10.1234/test'}]
    bib=subprocess.check_output(['quarto','pandoc','-f','csljson','-t','biblatex'],input=json.dumps(records),text=True)
    assert 'doi = {10.1234/test}' in bib and '{{Research and Science Group}}' in bib


def test_review_pdf_hyphen_and_batch_merge(project):
    root=review.packet(project)
    packet=json.loads((root/'packet.json').read_text())
    # Actual evidence quotation normalized across a PDF-like line end.
    (project/'source/original.md').write_text('Brennan-\nGreenstadt')
    root=review.packet(project)
    quoted=valid_result(root)
    quoted['issues'][0]['source_file']='originals/original.md'
    quoted['issues'][0]['source_quote']='Brennan-Greenstadt'
    review.portable.validate(root,quoted)
    first=valid_result(root)
    second=json.loads(json.dumps(first))
    first['coverage'][0]['status']='unread'
    second['coverage'][0]['status']='checked'
    merged=review.portable.merge_reviews([first,second])
    assert len(merged['issues'])==1 and merged['coverage'][0]['status']=='checked'
