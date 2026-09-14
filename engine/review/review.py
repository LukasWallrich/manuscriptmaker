"""Portable review runner and evidence validator; Python 3.10+, standard library only."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request
import uuid

PASSES = ['import-fidelity', 'proof-fidelity', 'proofreading']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def obj(properties):
    return dict(type='object', properties=properties, required=list(properties), additionalProperties=False)


def enum(values):
    return dict(type='string', enum=values)


STRING = dict(type='string')
SCHEMA = obj({
    'packet_id': STRING, 'passes': dict(type='array', items=enum(PASSES)),
    'summary': STRING, 'limitations': dict(type='array', items=STRING),
    'coverage': dict(type='array', items=obj({'file': STRING, 'status': enum(['checked', 'partial', 'unread']), 'notes': STRING})),
    'issues': dict(type='array', items=obj({
        'pass': enum(PASSES), 'severity': enum(['blocker', 'warning', 'suggestion']),
        'category': STRING, 'file': STRING, 'quote': STRING,
        'source_file': STRING, 'source_quote': STRING,
        'location': STRING, 'explanation': STRING,
        'suggested_correction': dict(type=['string', 'null']),
        'confidence': enum(['high', 'medium', 'low'])}))})


def shape(value, schema):
    kind = schema['type']
    if isinstance(kind, list):
        if value is None and 'null' in kind:
            return
        kind = 'string'
    valid = {'object': isinstance(value, dict), 'array': isinstance(value, list), 'string': isinstance(value, str)}
    if not valid.get(kind, False):
        raise ValueError('Result does not match the review schema: expected ' + kind)
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError('Unknown review value: ' + str(value))
    if kind == 'object':
        if set(value) != set(schema['properties']):
            raise ValueError('Missing or unexpected review fields')
        for key, child in schema['properties'].items():
            shape(value[key], child)
    elif kind == 'array':
        for item in value:
            shape(item, schema['items'])


def verify(root):
    packet = json.loads((root / 'packet.json').read_text())
    for name, expected in packet['hashes'].items():
        p = (root / name).resolve()
        if not p.is_relative_to(root.resolve()) or not p.is_file() or digest(p) != expected:
            raise ValueError('Package evidence changed or missing: ' + name)
    return packet


def validate(root, result):
    packet = verify(root)
    shape(result, SCHEMA)
    if result['packet_id'] != packet['packet_id']:
        raise ValueError('Result belongs to a different review package')
    if not result['passes'] or len(set(result['passes'])) != len(result['passes']):
        raise ValueError('Specify unique completed review passes')
    evidence = set(packet['evidence'])
    if {c['file'] for c in result['coverage']} != evidence or len(result['coverage']) != len(evidence):
        raise ValueError('Coverage must list every evidence file exactly once, including unread files')
    warnings = []
    for issue in result['issues']:
        if issue['pass'] not in result['passes']:
            raise ValueError('Issue is outside the declared review passes')
        if not issue['quote'].strip() or not issue['explanation'].strip() or not issue['location'].strip():
            raise ValueError('Each issue needs a quote, location and explanation')
        for key, quote_key in [('file', 'quote'), ('source_file', 'source_quote')]:
            name, quote = issue[key], issue[quote_key]
            if not name and key == 'source_file' and not quote and issue['pass'] == 'proofreading':
                continue
            if name not in evidence or not quote.strip():
                raise ValueError('Issue needs a known evidence file and quotation')
            try:
                content = (root / name).read_text(encoding='utf-8')
            except UnicodeError:
                warnings.append('Visual evidence requires human verification: ' + name)
                continue
            normalize = lambda s: ' '.join(s.split())
            if normalize(quote) not in normalize(content):
                raise ValueError('Quoted evidence is not present in ' + name)
    return sorted(set(warnings))


def parse_result(raw):
    raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip())
    value = json.loads(raw)
    if isinstance(value, dict) and 'structured_output' in value:
        value = value['structured_output']
    elif isinstance(value, dict) and 'result' in value and isinstance(value['result'], str):
        value = value['result']
    if isinstance(value, str):
        value = json.loads(re.sub(r'^```(?:json)?\s*|\s*```$', '', value.strip()))
    return value


def command(provider, root, prompt, model, output):
    if provider == 'codex':
        cmd = ['codex', 'exec', '--skip-git-repo-check', '--sandbox', 'read-only', '--output-schema', str(root / 'schema.json'), '-o', str(output), '-']
    elif provider == 'claude':
        cmd = ['claude', '-p', '--tools', 'Read,Glob,Grep', '--allowedTools', 'Read,Glob,Grep', '--strict-mcp-config', '--output-format', 'json', '--json-schema', json.dumps(SCHEMA)]
    else:
        if not model or not re.search(r'Gemini (\d+\.\d+) Flash', model) or float(re.search(r'Gemini (\d+\.\d+) Flash', model)[1]) < 3.8:
            raise ValueError('Choose an explicit Gemini Flash model at 3.8 or above from agy models')
        cmd = ['agy', '-p', prompt, '--sandbox', '--add-dir', str(root), '--print-timeout', '15m', '--json-schema', str(root / 'schema.json')]
    if model:
        cmd += ['--model', model]
    return cmd


def openrouter_payload(root, packet, prompt, model, max_tokens):
    texts, images = {}, []
    for name in packet['evidence']:
        suffix = Path(name).suffix.lower()
        if suffix in {'.txt', '.qmd', '.md', '.bib', '.yml', '.json', '.tex', '.xml'}:
            texts[name] = (root / name).read_text()
        elif suffix in {'.png', '.jpg', '.jpeg', '.webp'}:
            mime = 'image/jpeg' if suffix in {'.jpg', '.jpeg'} else 'image/' + suffix[1:]
            images.extend([{'type': 'text', 'text': 'Evidence image: ' + name},
                           {'type': 'image_url', 'image_url': {'url': 'data:' + mime + ';base64,' + base64.b64encode((root / name).read_bytes()).decode()}}])
    content = [{'type': 'text', 'text': json.dumps({'packet': packet, 'evidence_text': texts})}] + images
    payload = {'model': model, 'max_tokens': max_tokens,
        'messages': [{'role': 'system', 'content': prompt + '\nYou receive text and labeled images, including rendered PDF pages when available. Mark absent/unreadable files unread. Review PDF layout through page-images; do not claim to have opened binary archives or documents.'},
                     {'role': 'user', 'content': content}],
        'response_format': {'type': 'json_schema', 'json_schema': {'name': 'manuscript_review', 'strict': True, 'schema': SCHEMA}}}
    return json.dumps(payload).encode(), len(images) // 2


def run(args, root):
    packet = verify(root)
    packet_digest = digest(root / 'packet.json')
    prompt = (root / 'prompt.md').read_text() + '\nReview passes: ' + ', '.join(args.passes) + '\nPackage directory: ' + str(root)
    outdir = root / 'results' / uuid.uuid4().hex[:12]
    outdir.mkdir(parents=True)
    if args.provider == 'openrouter':
        if not args.model:
            raise ValueError('OpenRouter requires an explicit --model')
        payload, image_count = openrouter_payload(root, packet, prompt, args.model, args.max_tokens)
        print(f'OpenRouter request: {len(payload):,} bytes, {image_count} images; output limit {args.max_tokens} tokens. Check model pricing before running with --send.')
        if len(payload) > args.max_request_mb * 1_000_000:
            raise ValueError('Request exceeds --max-request-mb; nothing sent. Choose a suitable model and explicitly increase the limit, or review a smaller package.')
        if not args.send:
            print('Dry run only; no content sent. Add --send after checking cost and data policy.')
            return
        key = os.environ.get('OPENROUTER_API_KEY')
        if not key:
            raise ValueError('Set OPENROUTER_API_KEY in your environment')
        request = urllib.request.Request('https://openrouter.ai/api/v1/chat/completions', data=payload,
            headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=900) as response:
            envelope = json.load(response)
        raw = envelope['choices'][0]['message']['content']
        (outdir / 'usage.json').write_text(json.dumps(envelope.get('usage', {}), indent=2))
    else:
        target = outdir / 'response.json'
        cmd = command(args.provider, root, prompt, args.model, target)
        result = subprocess.run(cmd, input=prompt if args.provider != 'agy' else None, cwd=root, text=True, capture_output=True, timeout=1200)
        (outdir / 'agent.log').write_text(result.stderr)
        (outdir / 'stdout.txt').write_text(result.stdout)
        if result.returncode:
            raise ValueError('Agent failed; inspect ' + str(outdir / 'agent.log'))
        raw = target.read_text() if args.provider == 'codex' else result.stdout
    (outdir / 'raw-response.txt').write_text(raw)
    if digest(root / 'packet.json') != packet_digest:
        raise ValueError('Agent modified packet.json; export a fresh package')
    review = parse_result(raw)
    warnings = validate(root, review)
    if set(review['passes']) != set(args.passes):
        raise ValueError('Agent did not return the requested passes')
    # Detect modifications by agents with file-writing capabilities (notably agy).
    verify(root)
    (outdir / 'review.json').write_text(json.dumps(review, ensure_ascii=False, indent=2))
    (outdir / 'runner.json').write_text(json.dumps({'provider': args.provider, 'requested_model': args.model, 'warnings': warnings}, indent=2))
    print('Validated findings: ' + str(outdir / 'review.json'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    r = sub.add_parser('run')
    r.add_argument('--provider', choices=['codex', 'claude', 'agy', 'openrouter'], required=True)
    r.add_argument('--model')
    r.add_argument('--passes', nargs='+', choices=PASSES, default=PASSES)
    r.add_argument('--max-tokens', type=int, default=12000)
    r.add_argument('--max-request-mb', type=int, default=32)
    r.add_argument('--send', action='store_true', help='Send the paid OpenRouter request; otherwise dry run')
    v = sub.add_parser('validate')
    v.add_argument('result', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    try:
        if args.action == 'run':
            run(args, root)
        else:
            print(json.dumps(validate(root, parse_result(args.result.read_text()))))
    except (ValueError, OSError, subprocess.SubprocessError, KeyError) as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
