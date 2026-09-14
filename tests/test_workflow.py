import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine/scripts"))
import build
import normalize
import validate_meta


@pytest.fixture
def manuscript(tmp_path):
    p = tmp_path / "TEST.001"
    p.mkdir()
    (p / "article.qmd").write_text('''---
title: A test article
author:
  - name: {given: Alex, family: Example}
    email: alex@example.org
    corresponding: true
    affiliations: [{ref: a}]
affiliations: [{id: a, name: Example Institute}]
abstract: An abstract with complete metadata.
keywords: [testing]
bibliography: references.bib
---

A citation [@example].
''')
    (p / "references.bib").write_text('@article{example, author={Example, Alex}, title={Test}, year={2026}, journal={Tests}}')
    (p / "_metadata.yml").write_text('''date: 2026-09-14
r2:
  article-id: TEST.001
  volume: 1
  year: 2026
  article-type: Methods
  discipline: Metascience
  doi: 10.1234/test.001
''')
    return p


def test_build_import_preserves_edits(manuscript):
    (manuscript / "source").mkdir()
    (manuscript / "source/accepted.md").write_text("Original unedited text")
    before = (manuscript / "article.qmd").read_bytes()
    normalize.main(str(manuscript))
    assert (manuscript / "article.qmd").read_bytes() == before
    normalize.main(str(manuscript), reimport=True)
    assert (manuscript / "article.qmd").read_bytes() == before
    assert next((manuscript / ".imports").glob("*/article.qmd")).read_text() == "Original unedited text"


def test_source_ambiguity_never_chooses_largest(tmp_path):
    (tmp_path / "source").mkdir()
    (tmp_path / "source/one.md").write_text("one")
    (tmp_path / "source/two.md").write_text("two two two")
    with pytest.raises(SystemExit, match="Ambiguous"):
        normalize.find_source(tmp_path)


def test_template_instruction_is_not_an_upload(tmp_path):
    (tmp_path / "source").mkdir()
    (tmp_path / "source/PUT_MANUSCRIPT_HERE.md").write_text("Instructions")
    with pytest.raises(SystemExit, match="No supported upload"):
        normalize.find_source(tmp_path)


def test_valid_article(manuscript):
    assert validate_meta.check(manuscript) == []


def test_placeholders_and_wrong_id_block_release(manuscript):
    p = manuscript / "article.qmd"
    p.write_text(p.read_text().replace("A test article", '"TODO: title"'))
    meta = manuscript / "_metadata.yml"
    meta.write_text(meta.read_text().replace("TEST.001", "WRONG"))
    issues = validate_meta.check(manuscript)
    assert {"placeholder", "article-id"} <= {i["code"] for i in issues}
    assert all(i["severity"] == "error" for i in issues)
    assert all(i["severity"] == "warning" for i in validate_meta.check(manuscript, "draft"))


def test_missing_citation_and_figure(manuscript):
    p = manuscript / "article.qmd"
    p.write_text(p.read_text() + '\nA missing citation [@absent].\n\n![Figure](figures/missing.png)\n')
    codes = {i["code"] for i in validate_meta.check(manuscript)}
    assert {"citation", "image"} <= codes


def test_empty_bibliography_with_citations_fails(manuscript):
    (manuscript / "references.bib").write_text("")
    assert any(i["code"] == "citation" for i in validate_meta.check(manuscript))


def test_bad_orcid_and_unresolved_affiliation(manuscript):
    p = manuscript / "article.qmd"
    p.write_text(p.read_text().replace("email: alex", "orcid: 0000-0000-0000-0000\n    email: alex").replace("ref: a", "ref: absent"))
    assert {"orcid", "author"} <= {i["code"] for i in validate_meta.check(manuscript)}


def test_approval_rejects_stale_and_modified_proofs(manuscript, tmp_path):
    run = tmp_path / "proof"
    (run / "outputs").mkdir(parents=True)
    for name in ("article.html", "article.pdf", "article.xml", "article-jats.zip", "TEST.001_ojs_import.xml"):
        (run / "outputs" / name).write_text("Reviewed proof")
    manifest = dict(article_id=manuscript.name, revision=build.fingerprint(manuscript)[0],
                    state="built", release_ready=True, outputs=build.file_hashes(run / "outputs"))
    (run / "manifest.json").write_text(json.dumps(manifest))
    assert build.approve(manuscript, run).is_file()
    (run / "outputs/article.html").write_text("Different proof")
    with pytest.raises(ValueError, match="Proof files changed"):
        build.approve(manuscript, run)
    (manuscript / "references.bib").write_text("Changed reference")
    with pytest.raises(ValueError, match="changed; build"):
        build.approve(manuscript, run)


def test_incomplete_proof_cannot_be_approved(manuscript, tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps(dict(article_id=manuscript.name,
        revision=build.fingerprint(manuscript)[0], state="built", release_ready=False)))
    with pytest.raises(ValueError, match="incomplete"):
        build.approve(manuscript, tmp_path)


def test_ojs_package_validates_and_keeps_correct_contact(manuscript):
    import base64
    from lxml import etree
    import build_ojs
    for name, data in [('article.pdf', b'%PDF fixture'), ('article.html', b'<html>Reviewed text</html>'), ('article.xml', b'<article/>')]:
        (manuscript / name).write_bytes(data)
    p = build_ojs.build(manuscript, None)
    tree = etree.parse(str(p))
    ns = {'p': 'http://pkp.sfu.ca'}
    assert tree.xpath('string(//p:publication/@primary_contact_id)', namespaces=ns) == '1'
    assert tree.xpath('string(//p:publication/@status)', namespaces=ns) == '1'
    embedded = tree.xpath('//p:embed/text()', namespaces=ns)
    assert base64.b64decode(embedded[1]) == b'<html>Reviewed text</html>'
    (manuscript / 'article.pdf').unlink()
    with pytest.raises(ValueError, match='Required galley missing'):
        build_ojs.build(manuscript, None)


def test_jats_enrichment_is_valid_and_idempotent(manuscript):
    from lxml import etree
    import enrich_jats
    p = manuscript / 'article.xml'
    p.write_text('''<article><front><article-meta><title-group><article-title>A test article</article-title></title-group><history/><abstract><p>Abstract</p></abstract></article-meta></front><body><p>Body</p></body></article>''')
    enrich_jats.enrich(p, manuscript)
    before = p.read_bytes()
    enrich_jats.enrich(p, manuscript)
    assert p.read_bytes() == before
    tree = etree.parse(str(p))
    assert tree.xpath('string(//article-id[@pub-id-type="doi"])') == '10.1234/test.001'
    assert tree.xpath('string(//journal-title)') == 'Replication Research (R2)'


def test_engine_changes_build_all_fixtures(tmp_path):
    from detect_manuscripts import select
    for name in ('One', 'Two', '_TEMPLATE'):
        (tmp_path / 'manuscripts' / name).mkdir(parents=True)
    assert select(['engine/scripts/build.py'], tmp_path) == ['One', 'Two']
    assert select(['_quarto.yml'], tmp_path) == ['One', 'Two']
    assert select(['manuscripts/One/article.qmd', 'manuscripts/Deleted/article.qmd'], tmp_path) == ['One']


def test_workspace_refuses_to_overwrite_concurrent_edits(manuscript):
    import workspace
    files = workspace.read_files(manuscript)
    revision = workspace.edit_revision(files)
    (manuscript / 'article.qmd').write_text('An external edit')
    with pytest.raises(ValueError, match='changed outside'):
        workspace.save_files(manuscript, files, revision)
    assert (manuscript / 'article.qmd').read_text() == 'An external edit'


@pytest.mark.skipif(__import__('os').environ.get('R2_INTEGRATION') != '1', reason='Requires full LaTeX toolchain; R2_INTEGRATION=1 enables it')
def test_release_pipeline_preserves_copyedits_in_every_format(manuscript):
    import shutil
    import subprocess
    import zipfile
    from lxml import etree, html
    (manuscript / 'source').mkdir()
    (manuscript / 'source/accepted.md').write_text('Unedited original manuscript')
    (manuscript / 'figures').mkdir()
    shutil.copyfile(build.ROOT / 'themes/r2/assets/logo.png', manuscript / 'figures/figure.png')
    p = manuscript / 'article.qmd'
    p.write_text(p.read_text().replace('Example Institute', 'Revised Institute') + '\nCopyedited sentence survives every format.\n\n![Revised figure caption.](figures/figure.png){#fig-example}\n\nAn equation: $x^2 + y^2 = z^2$.\n')
    before = p.read_bytes()
    run = build.build(manuscript, mode='release')
    manifest = json.loads((run / 'manifest.json').read_text())
    assert manifest['state'] == 'built', (manifest, (run / 'build.log').read_text()[-3000:])
    assert manifest['release_ready']
    assert p.read_bytes() == before
    for name in ('article.html', 'article.xml'):
        parser = html.parse if name.endswith('html') else etree.parse
        document = parser(str(run / 'outputs' / name))
        text = ' '.join(document.getroot().itertext())
        assert 'Copyedited sentence survives every format.' in text
        assert 'Revised Institute' in text
        assert 'Revised figure caption.' in text
    text = subprocess.check_output(['pdftotext', str(run / 'outputs/article.pdf'), '-'], text=True)
    assert 'Copyedited sentence survives every format.' in text
    assert 'Revised Institute' in text
    archive = build.approve(manuscript, run)
    with zipfile.ZipFile(archive) as z:
        assert z.read('article.pdf') == (run / 'outputs/article.pdf').read_bytes()
    with zipfile.ZipFile(run / 'outputs/article-jats.zip') as z:
        assert 'figures/figure.png' in z.namelist()


def test_real_word_import_preserves_citations_and_figures(tmp_path):
    import shutil
    target = tmp_path / 'Word'
    (target / 'source').mkdir(parents=True)
    original = build.ROOT / 'manuscripts/Hussey/source/manuscript.docx'
    shutil.copyfile(original, target / 'source/accepted.docx')
    normalize.main(str(target))
    text = (target / 'article.qmd').read_text()
    assert 'Foody' in text and '@' in text
    assert (target / 'references.bib').stat().st_size > 1000
    assert len(list((target / 'figures').rglob('image*'))) >= 4
    assert (target / 'source/accepted.docx').read_bytes() == original.read_bytes()


def test_real_latex_import_uses_selected_version_and_declared_bibliography(tmp_path):
    import shutil
    target = tmp_path / 'Latex'
    (target / 'source').mkdir(parents=True)
    original = build.ROOT / 'manuscripts/Stylometry/source/accepted-source.zip'
    shutil.copyfile(original, target / 'source/accepted.zip')
    normalize.main(str(target), source=str(target / 'source/main.tex'))
    text = (target / 'article.qmd').read_text()
    assert 'Reproduction and Replication of an Adversarial Stylometry Experiment' in text
    assert '@brennan2012adversarial' in text
    assert (target / 'references.bib').read_text() == (target / 'source/references.bib').read_text()
    assert '#tbl:demographics' in text
    assert '| RJ' in text and '| Age' in text
    assert '| 1-5' not in text and '2-5 Paraphrasing' not in text
