"""Stage new manuscript uploads without replacing any existing manuscript."""
import base64
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import zipfile

import build

MAX_BYTES = 30_000_000
ALLOWED = {'.docx', '.qmd', '.md', '.tex', '.zip', '.pdf', '.bib', '.png', '.jpg', '.jpeg', '.svg'}


def check_zip(data, allow_hidden=False):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        if len(infos) > 2000 or sum(i.file_size for i in infos) > 100_000_000:
            raise ValueError('Archive exceeds 2,000 files or 100 MB expanded')
        seen = set()
        for info in infos:
            normalized = str(PurePosixPath(info.filename)).casefold()
            if normalized in seen:
                raise ValueError('Archive contains duplicate paths')
            seen.add(normalized)
            path = PurePosixPath(info.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in info.filename or ':' in info.filename:
                raise ValueError('Archive contains an unsafe path')
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Archive symlinks are not supported')
            if not allow_hidden and any(part.startswith('.') for part in path.parts):
                raise ValueError('Remove hidden configuration files from the source archive')


def create(name, files, main=''):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', name):
        raise ValueError('Use an article ID of letters, numbers, dots, underscores or hyphens')
    destination = build.ROOT / 'manuscripts' / name
    if destination.exists():
        raise ValueError('That manuscript already exists. Choose a new article ID.')
    if not isinstance(files, list) or not 1 <= len(files) <= 100:
        raise ValueError('Choose 1–100 source files, up to 30 MB total')
    decoded = {}
    for item in files:
        filename = item['name']
        if not isinstance(filename, str) or Path(filename).name != filename or filename.startswith('.') or '\\' in filename:
            raise ValueError('Invalid upload filename')
        if filename in decoded or Path(filename).suffix.lower() not in ALLOWED:
            raise ValueError('Duplicate or unsupported upload: ' + filename)
        data = base64.b64decode(item['data'], validate=True)
        if Path(filename).suffix.lower() in {'.zip', '.docx'}:
            check_zip(data, allow_hidden=Path(filename).suffix.lower() == '.docx')
        decoded[filename] = data
    if sum(map(len, decoded.values())) > MAX_BYTES:
        raise ValueError('Upload exceeds 30 MB')
    if not any(Path(n).suffix.lower() in {'.docx', '.qmd', '.md', '.tex', '.zip'} for n in decoded):
        raise ValueError('Include an editable Word, Quarto, Markdown or LaTeX source; PDF alone is reference evidence')
    stage_parent = build.ROOT / '_build/uploads'
    stage_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=stage_parent) as staging:
        work = Path(staging) / name
        source = work / 'source'
        source.mkdir(parents=True)
        for filename, data in decoded.items():
            (source / filename).write_bytes(data)
        # Expand once before selecting the main, after checking archive paths/sizes.
        for filename in decoded:
            if Path(filename).suffix.lower() == '.zip':
                with zipfile.ZipFile(source / filename) as archive:
                    for info in archive.infolist():
                        target = source / info.filename
                        if target.exists() and not info.is_dir():
                            raise ValueError('Archive would overwrite another upload: ' + info.filename)
                    archive.extractall(source)
        import normalize
        candidates = [p for p in source.rglob('*') if normalize._is_real_source(p)]
        if main:
            selected = (source / main).resolve()
            if not selected.is_relative_to(source.resolve()) or selected not in candidates:
                raise ValueError('Main source must name an editable file inside the upload')
        elif len(candidates) == 1:
            selected = candidates[0]
        else:
            mains = [p for p in candidates if p.suffix.lower() == '.tex' and '\\begin{document}' in p.read_text(errors='ignore')]
            if len(mains) != 1:
                raise ValueError('Choose Main source from: ' + ', '.join(str(p.relative_to(source)) for p in candidates))
            selected = mains[0]
        cmd = [sys.executable, str(build.ROOT / 'engine/scripts/normalize.py'), str(work), '--source', str(selected)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode:
            raise ValueError('Import failed: ' + (result.stderr or result.stdout)[-1500:])
        (work / '_metadata.yml').write_text('r2:\n  article-id: ' + name + '\n')
        (work / 'references.bib').touch(exist_ok=True)
        (source / 'selection.json').write_text(json.dumps({'main': str(selected.relative_to(source)), 'uploaded_files': list(decoded)}, indent=2))
        # Atomic installation after successful import; caller holds the workspace lock.
        work.rename(destination)
    return name
