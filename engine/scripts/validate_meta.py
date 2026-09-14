"""Validate editable sources. Draft issues remain visible; release issues block approval."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

import r2meta

REQUIRED = ["title", "abstract", "keywords", "r2.volume", "r2.year",
            "r2.article-id", "r2.article-type", "r2.discipline", "r2.journal"]
PLACEHOLDER = re.compile(r"\b(?:TODO|TBD|FIXME)\b|Your article title|One-paragraph abstract|First University", re.I)


def walk(value):
    if isinstance(value, dict):
        yield value
        for v in value.values():
            yield from walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from walk(v)


def get(meta, dotted):
    for key in dotted.split("."):
        meta = meta.get(key) if isinstance(meta, dict) else None
    return meta


def check(manuscript_dir: str | Path, mode="release", content=True) -> list[dict]:
    mdir = Path(manuscript_dir).resolve()
    issues = []

    def issue(code, message, file="article.qmd", always=False):
        issues.append(dict(code=code, message=message, file=file,
                           severity="error" if mode == "release" or always else "warning"))

    try:
        meta = r2meta.load(mdir)
        text = (mdir / "article.qmd").read_text()
    except (ValueError, TypeError, AttributeError, OSError) as e:
        issue("source", str(e), always=True)
        return issues
    except Exception as e:
        issue("metadata", f"Cannot read metadata: {e}", always=True)
        return issues
    for key in REQUIRED:
        if not get(meta, key):
            issue("required", f"Missing required field: {key}", "_metadata.yml")
    for path in (mdir / "article.qmd", mdir / "_metadata.yml"):
        if path.exists():
            for n, line in enumerate(path.read_text().splitlines(), 1):
                if PLACEHOLDER.search(line):
                    issue("placeholder", f"Replace placeholder on line {n}", path.name)
    if get(meta, "r2.article-id") != mdir.name:
        issue("article-id", "r2.article-id must match the manuscript folder", "_metadata.yml")
    doi = str(get(meta, "r2.doi") or "")
    if not re.fullmatch(r"10\.\d{4,9}/\S+", doi):
        issue("doi", "Supply a DOI in the form 10.xxxx/suffix", "_metadata.yml")
    try:
        date = dt.date.fromisoformat(str(meta.get("date", "")))
        if date.year != int(get(meta, "r2.year")):
            issue("date", "Publication date and r2.year disagree", "_metadata.yml")
    except (ValueError, TypeError):
        issue("date", "Supply a publication date (YYYY-MM-DD) and numeric year", "_metadata.yml")
    for field in ("title", "abstract"):
        if not isinstance(meta.get(field), str):
            issue("type", f"{field} must be text", always=True)
    if not isinstance(meta.get("keywords"), list):
        issue("type", "keywords must be a list", always=True)
    authors = meta.get("_authors", [])
    if not authors:
        issue("authors", "Supply structured author names and affiliations")
    if sum(a["corresponding"] for a in authors) != 1:
        issue("corresponding", "Mark exactly one corresponding author")
    for i, a in enumerate(authors, 1):
        if not a["name"] or not a["affiliations"]:
            issue("author", f"Author {i} needs a name and a resolved affiliation")
        # Native OJS exports require author email fields. Never invent one or
        # silently assign another person's email to an author.
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", str(a["email"])):
            issue("email", f"Author {i} needs an email for the OJS package")
        orcid = str(a["orcid"] or "").removeprefix("https://orcid.org/")
        if orcid:
            digits = orcid.replace("-", "")
            total = 0
            if re.fullmatch(r"\d{15}[\dX]", digits):
                for d in digits[:15]:
                    total = (total + int(d)) * 2
                check_digit = (12 - total % 11) % 11
                valid = digits[-1] == ("X" if check_digit == 10 else str(check_digit))
            else:
                valid = False
            if not valid:
                issue("orcid", f"Author {i} has an invalid ORCID")
    bibs = meta.get("bibliography", [])
    bibs = [bibs] if isinstance(bibs, str) else bibs
    if not isinstance(bibs, list) or any(not isinstance(b, str) for b in bibs):
        issue("bibliography", "bibliography must be a filename or list of filenames", always=True)
        return issues
    paths = []
    for b in bibs:
        p = (mdir / b).resolve()
        if not p.is_relative_to(mdir) or not p.is_file():
            issue("bibliography", f"Bibliography file missing or outside manuscript: {b}", always=True)
        else:
            paths.append(p)
    if not content:
        return issues
    try:
        proc = subprocess.run(["quarto", "pandoc", "article.qmd", "-f", "markdown", "-t", "json"],
                              cwd=mdir, capture_output=True, text=True, check=True)
        ast = json.loads(proc.stdout)
        nodes = list(walk(ast))
        cites = {c["citationId"] for node in nodes if node.get("t") == "Cite" for c in node["c"][0]}
        references = []
        for p in paths:
            if p.stat().st_size:
                proc = subprocess.run(["quarto", "pandoc", str(p), "-t", "csljson"],
                                      capture_output=True, text=True, check=True)
                references.extend(json.loads(proc.stdout))
        keys = [str(r["id"]) for r in references]
        if len(keys) != len(set(keys)):
            issue("duplicate-citation", "Bibliography contains duplicate citation keys")
        ids = set()
        for node in nodes:
            c = node.get("c", [])
            if node.get("t") in {"Div", "Span", "Image", "Table", "CodeBlock"} and c:
                if isinstance(c[0], list) and c[0] and isinstance(c[0][0], str):
                    ids.add(c[0][0])
            elif node.get("t") == "Header":
                ids.add(c[1][0])
        for cite in sorted(cites - set(keys) - ids):
            issue("citation", f"Unresolved citation or cross-reference: @{cite}")
        for node in nodes:
            if node.get("t") == "Link":
                target = node["c"][2][0]
                if target.startswith("#") and unquote(target[1:]) not in ids:
                    issue("cross-reference", f"Unresolved internal link: {target}")
            if node.get("t") == "Image":
                target = node["c"][2][0]
                if urlparse(target).scheme in {"http", "https"}:
                    issue("image", f"Download external figure into the manuscript: {target}")
                elif not target.startswith("data:"):
                    p = (mdir / unquote(target)).resolve()
                    if not p.is_relative_to(mdir) or not p.is_file():
                        issue("image", f"Missing figure: {target}")
                    elif p.suffix.lower() in {".emf", ".wmf"}:
                        issue("image", f"Convert unsupported figure to PNG/SVG: {target}")
    except (OSError, subprocess.CalledProcessError, ValueError) as e:
        detail = getattr(e, "stderr", None) or str(e)
        issue("parse", f"Cannot check citations and figures: {detail}", always=True)
    return issues


def main(manuscript_dir: str, mode="release", json_path=None) -> int:
    issues = check(manuscript_dir, mode)
    for i in issues:
        print(f"::{i['severity']} file={Path(manuscript_dir) / i['file']}::{i['message']}")
    if json_path:
        Path(json_path).write_text(json.dumps(issues, indent=2))
    failed = any(i["severity"] == "error" for i in issues)
    print(f"Validation {'FAILED' if failed else 'passed'} ({mode}; {len(issues)} issue(s)).")
    return int(failed)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manuscript_dir")
    ap.add_argument("--mode", choices=["draft", "release"], default="release")
    ap.add_argument("--json", dest="json_path")
    args = ap.parse_args()
    sys.exit(main(args.manuscript_dir, args.mode, args.json_path))
