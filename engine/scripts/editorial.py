"""Persist review decisions and selection-anchored editorial comments."""
import datetime as dt
import json
from pathlib import Path
import uuid

import build
import review_packet


def identifier(value):
    if not isinstance(value, str) or len(value) != 32 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('Invalid editorial record ID')
    return value


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.saving')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(path)


def decide(mdir, report_id, packet_id, index, decision, files, save):
    root = build.ROOT / '_build/llm-review' / mdir.name / identifier(packet_id)
    path = root / 'returned' / (identifier(report_id) + '.json')
    report = json.loads(path.read_text())
    if decision not in {'accepted', 'rejected'}:
        raise ValueError('Choose Accept or Reject')
    if type(index) is not int or not 0 <= index < len(report['result']['issues']):
        raise ValueError('Unknown finding')
    if str(index) in report.get('decisions', {}):
        raise ValueError('This finding already has an editorial decision')
    issue = report['result']['issues'][index]
    if decision == 'accepted':
        packet = review_packet.portable.verify(root)
        if report.get('working_revision', packet['revision']) != build.fingerprint(mdir)[0] or packet['originals'] != review_packet.original_hashes(mdir):
            raise ValueError('Review is stale. Export a fresh review or make the change manually.')
        proof = packet.get('proof')
        if proof and proof['hashes'] != build.file_hashes(build.ROOT / '_build' / mdir.name / proof['run'] / 'outputs'):
            raise ValueError('Review is stale because its proof files changed')
        name = issue['file'].removeprefix('canonical/')
        quote, replacement = issue['quote'], issue['suggested_correction']
        if not issue['file'].startswith('canonical/') or name not in files or replacement is None:
            raise ValueError('This finding needs a manual edit')
        if not quote or files[name].count(quote) != 1:
            raise ValueError('The quoted passage is missing or ambiguous. Locate it and edit manually.')
        updated = dict(files)
        updated[name] = files[name].replace(quote, replacement, 1)
        save(updated)
        report['working_revision'] = build.fingerprint(mdir)[0]
    report.setdefault('decisions', {})[str(index)] = {'decision': decision, 'at': dt.datetime.now(dt.timezone.utc).isoformat()}
    write(path, report)


def comments_path(mdir):
    return build.ROOT / '_build/editorial' / mdir.name / 'comments.json'


def comments(mdir, files):
    path = comments_path(mdir)
    data = json.loads(path.read_text()) if path.exists() else []
    for item in data:
        text = files.get(item['file'], '')
        anchor = item['before'] + item['quote'] + item['after']
        item['current'] = bool(anchor) and text.count(anchor) == 1
        item['start'] = text.find(anchor) + len(item['before']) if item['current'] else None
    return data


def comment(mdir, files, data):
    path = comments_path(mdir)
    items = json.loads(path.read_text()) if path.exists() else []
    if data.get('resolve'):
        found = next((item for item in items if item['id'] == data['resolve']), None)
        if not found:
            raise ValueError('Unknown comment')
        found['resolved'] = True
    else:
        name, start, end = data.get('file'), data.get('start'), data.get('end')
        text = files.get(name, '')
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
            raise ValueError('Select a passage to comment on')
        note = data.get('text', '').strip()
        if not note or len(note) > 10000:
            raise ValueError('Enter a comment of 1–10,000 characters')
        items.append(dict(id=uuid.uuid4().hex, file=name, quote=text[start:end], before=text[max(0,start-32):start], after=text[end:end+32],
                          text=note, resolved=False, at=dt.datetime.now(dt.timezone.utc).isoformat()))
    write(path, items)
    return comments(mdir, files)


def details(files, updated=None):
    """Edit YAML data while preserving the manuscript body byte for byte."""
    import re
    import yaml
    match = re.match(r'^---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)', files['article.qmd'])
    front = yaml.safe_load(match[1]) or {} if match else {}
    publication = yaml.safe_load(files['_metadata.yml']) or {}
    if not isinstance(front, dict) or not isinstance(publication, dict):
        raise ValueError('Metadata must be YAML mappings; use the source tabs to repair it')
    if updated is None:
        front.setdefault('title', '')
        front.setdefault('abstract', '')
        front.setdefault('author', [])
        front.setdefault('affiliations', [])
        authors = front['author'] if isinstance(front['author'], list) else []
        for author in authors:
            if isinstance(author, dict):
                for key, default in {'email':'', 'orcid':'', 'corresponding':False, 'affiliations':[]}.items():
                    author.setdefault(key, default)
        publication.setdefault('date', '')
        r2 = publication.setdefault('r2', {})
        for name in ('article-id','volume','year','doi','article-type','discipline'):
            r2.setdefault(name, '')
        return json.loads(json.dumps({'article': front, 'publication': publication}, default=str))
    if set(updated) != {'article', 'publication'} or not all(isinstance(v, dict) for v in updated.values()):
        raise ValueError('Invalid metadata form')
    authors = updated['article'].get('author', [])
    for author in authors if isinstance(authors, list) else []:
        if isinstance(author, dict) and author.get('orcid') == '':
            author.pop('orcid')
    body = files['article.qmd'][match.end():] if match else files['article.qmd']
    return dict(files, **{'article.qmd': '---\n' + yaml.safe_dump(updated['article'], sort_keys=False, allow_unicode=True) + '---\n' + body,
                         '_metadata.yml': yaml.safe_dump(updated['publication'], sort_keys=False, allow_unicode=True)})
