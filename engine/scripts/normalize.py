"""Normalize a submitted manuscript into the canonical R2 source.

Input  : manuscripts/<id>/source/  containing ONE of
           *.qmd | *.md | *.rmd            (passthrough)
           *.docx | *.doc                  (Word, incl. Zotero/Mendeley cites)
           *.tex                           (LaTeX / Overleaf)
           *.zip                           (Overleaf project export)
Output : manuscripts/<id>/article.qmd  +  references.bib  +  figures/

The canonical → {HTML, PDF, JATS} path is identical for every input; only
this input → canonical step differs per format. Run it before `quarto render`.

Usage:
    python engine/scripts/normalize.py manuscripts/<id>
"""
from __future__ import annotations

import argparse
import datetime
import os
import signal
import re
import shutil
import subprocess
import sys
import zipfile

import yaml
from pathlib import Path

PANDOC = ["quarto", "pandoc"]  # Pandoc shipped with Quarto; no separate install
SUPPORTED = {".qmd", ".md", ".rmd", ".docx", ".doc", ".tex", ".zip"}

FRONT_MATTER_SKELETON = """---
title: "TODO: article title"
author:
  - name: {{ given: TODO, family: TODO }}
    email: ""
    corresponding: true
    affiliations: [{{ ref: aff1 }}]
    # No orcid key when unknown - leave it OUT rather than blank. Pandoc's
    # conditional treats an empty string as set, so a blank value renders
    # as a literal, invalid orcidlink command in the PDF template.
affiliations:
  - {{ id: aff1, name: "TODO: affiliation" }}
abstract: >
  TODO: abstract (paste here if it was not detected automatically).
keywords: [TODO]
bibliography: references.bib
---

{body}
"""


def run(cmd: list[str], cwd: Path | None = None, input_text=None) -> None:
    print("  $", " ".join(str(c) for c in cmd), flush=True)
    proc = subprocess.Popen(cmd, cwd=cwd, text=True, start_new_session=True,
                            stdin=subprocess.PIPE if input_text is not None else None)
    try:
        proc.communicate(input_text, timeout=90)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        raise SystemExit("Import exceeded 90 seconds; inspect the source for unsupported macros")
    if proc.returncode:
        raise subprocess.CalledProcessError(proc.returncode, cmd)


def _is_real_source(p: Path) -> bool:
    """A candidate source file — skips Office lock files (~$foo.docx)."""
    return (p.is_file()
            and p.suffix.lower() in SUPPORTED - {".zip"}
            and not p.name.startswith("~$")
            and p.name != "PUT_MANUSCRIPT_HERE.md")


def _candidates_in(search: Path) -> list[Path]:
    # Unzip an Overleaf export first, if present.
    for z in sorted(search.glob("*.zip")):
        print(f"  unzipping {z.name}")
        with zipfile.ZipFile(z) as zf:
            for info in zf.infolist():
                target = (search / info.filename).resolve()
                if not target.is_relative_to(search.resolve()):
                    raise SystemExit(f"Archive member escapes source directory: {info.filename}")
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise SystemExit("Archive symlinks are not supported")
            zf.extractall(search)
    return [p for p in search.rglob("*") if _is_real_source(p)]


def find_source(mdir: Path) -> Path:
    src_dir = mdir / "source"
    candidates = _candidates_in(src_dir) if src_dir.is_dir() else []
    if not candidates:
        raise SystemExit(f"No supported upload found in {src_dir}")
    if len(candidates) == 1:
        return candidates[0]
    mains = [p for p in candidates if p.suffix.lower() == ".tex"
             and "\\begin{document}" in p.read_text(encoding="utf-8", errors="ignore")]
    if len(mains) == 1:
        return mains[0]
    names = ", ".join(str(p.relative_to(src_dir)) for p in candidates)
    raise SystemExit(f"Ambiguous upload ({names}); specify --source PATH")


def passthrough(src: Path, mdir: Path) -> None:
    dst = mdir / "article.qmd"
    if src.resolve() != dst.resolve():
        shutil.copyfile(src, dst)
    print(f"  passthrough -> {dst.name}")


def from_docx(src: Path, mdir: Path) -> None:
    if src.suffix.lower() == ".doc":  # legacy .doc -> .docx via LibreOffice
        run(["soffice", "--headless", "--convert-to", "docx",
             "--outdir", str(src.parent), str(src)])
        src = src.with_suffix(".docx")

    body = mdir / "_body.md"
    # Run with cwd=mdir so --extract-media writes *relative* figure paths.
    run(PANDOC + [str(src), "-s", "-f", "docx+citations", "-t",
                  "markdown+yaml_metadata_block-raw_attribute",
                  "--extract-media=figures", "--wrap=none", "-o", "_body.md"],
        cwd=mdir)

    # Recover the reference-manager bibliography to BibTeX, if any.
    refs_json = mdir / "_refs.json"
    try:
        run(PANDOC + [str(src), "-f", "docx+citations", "-t", "csljson",
                      "-o", "_refs.json"], cwd=mdir)
        if refs_json.exists() and refs_json.read_text(encoding="utf-8").strip() not in ("", "[]"):
            run(PANDOC + ["_refs.json", "-f", "csljson", "-t", "bibtex",
                          "-o", "references.bib"], cwd=mdir)
        else:
            _warn_no_bib(mdir)
        refs_json.unlink(missing_ok=True)
    except subprocess.CalledProcessError:
        _warn_no_bib(mdir)

    text = _convert_metafiles(mdir, body.read_text(encoding="utf-8"))
    _assemble_qmd(mdir, text)
    body.unlink(missing_ok=True)


def from_latex(src: Path, mdir: Path) -> None:
    text = src.read_text(encoding="utf-8", errors="ignore")
    extracted = _extract_r2_macros(text)

    # Copy any .bib alongside the source.
    declared = re.search(r"\\bibliography\{([^}]+)\}", text)
    bibs = [(src.parent / (name.strip() if name.strip().endswith(".bib") else name.strip() + ".bib"))
            for name in declared.group(1).split(",")] if declared else sorted(src.parent.glob("*.bib"))
    if len(bibs) > 1 and not declared:
        raise SystemExit("Several bibliographies found; declare the intended bibliography in the LaTeX source")
    if bibs:
        (mdir / "references.bib").write_text("\n".join(p.read_text() for p in bibs))
        print(f"  bibliography: {bibs[0].name} -> references.bib")
    else:
        _warn_no_bib(mdir)

    body = mdir / "_body.md"
    # Package files describe layout; expanding arbitrary .sty files can make
    # Pandoc loop (for example PRIMEarxiv's author macros). Retain document
    # content and explicit macros, but omit package loading during import.
    import_text = re.sub(r"\\usepackage(?:\[[^\]]*\])?\{[^}]*\}", "", text)
    import_text = re.sub(r"\\cmidrule(?:\[[^\]]*\])?(?:\([^)]*\))?\{[^}]*\}", "", import_text)
    run(PANDOC + ["-s", "-f", "latex", "-t", "markdown",
                  "--extract-media=" + str(mdir / "figures"), "--wrap=none", "-o", str(body)],
        cwd=src.parent, input_text=import_text)
    text = body.read_text(encoding="utf-8").replace(str(mdir / "figures") + "/", "figures/")
    text = _convert_metafiles(mdir, text)
    _assemble_qmd(mdir, text, extracted)
    body.unlink(missing_ok=True)


def _extract_r2_macros(tex: str) -> dict:
    """Pull \\RtwoAbstract / \\keywords / \\recommendedcitation arguments."""
    out = {}
    for macro, key in (("RtwoAbstract", "abstract"),
                       ("keywords", "keywords"),
                       ("recommendedcitation", "recommended-citation")):
        m = re.search(r"\\" + macro + r"\{", tex)
        if not m:
            continue
        i, depth, start = m.end(), 1, m.end()
        while i < len(tex) and depth:
            if tex[i] == "{":
                depth += 1
            elif tex[i] == "}":
                depth -= 1
            i += 1
        out[key] = re.sub(r"\s+", " ", tex[start:i - 1]).strip()
    return out


def _assemble_qmd(mdir: Path, body: str, extracted: dict | None = None) -> None:
    """Write article.qmd, splitting any YAML pandoc produced from the body."""
    fm = ""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", body, re.DOTALL)
    if m:
        fm, body = m.group(1), m.group(2)

    extracted = extracted or {}
    meta = yaml.safe_load(fm) or {}
    if "abstract" in extracted and not meta.get("abstract"):
        meta["abstract"] = extracted["abstract"]
    if "keywords" in extracted and not meta.get("keywords"):
        meta["keywords"] = [k.strip() for k in re.split(r"[,;]|\\and", extracted["keywords"]) if k.strip()]
    if meta:
        meta["bibliography"] = "references.bib"
        content = "---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False) + "---\n\n" + body
    else:
        content = FRONT_MATTER_SKELETON.format(body=body)
        print("No metadata detected; complete the TODO fields before approval.")
    (mdir / "article.qmd").write_text(content, encoding="utf-8")
    print("  wrote article.qmd")


def _convert_metafiles(mdir: Path, body: str) -> str:
    """Convert extracted EMF/WMF images (Word vector metafiles that neither
    browsers nor most PDF toolchains handle) to PNG, and rewrite the links
    in the markdown body.

    LibreOffice's headless --convert-to does not reliably import bare
    EMF/WMF graphic files outside a document context (this failed silently
    in CI regardless of which LO packages were installed), so this uses
    dedicated converters instead: emf2svg-conv for .emf, wmf2svg (from
    libwmf-bin) for .wmf, then rsvg-convert to rasterize the resulting SVG
    to PNG. CI installs all three; locally we warn and keep the originals
    if they're unavailable.
    """
    metafiles = [p for p in (mdir / "figures").rglob("*")
                 if p.suffix.lower() in {".emf", ".wmf"}]
    if not metafiles:
        return body
    emf2svg, wmf2svg, rsvg = (shutil.which(n) for n in ("emf2svg-conv", "wmf2svg", "rsvg-convert"))
    if not rsvg or not (emf2svg or wmf2svg):
        print(f"::warning::{len(metafiles)} EMF/WMF figure(s) found but the converters "
              "(emf2svg-conv/wmf2svg + rsvg-convert) are not installed — figures left "
              "unconverted. CI converts them automatically.")
        return body
    for mf in metafiles:
        is_emf = mf.suffix.lower() == ".emf"
        converter = emf2svg if is_emf else wmf2svg
        if not converter:
            print(f"::warning::No converter for {mf.suffix} — skipping {mf.name}.")
            continue
        svg, png = mf.with_suffix(".svg"), mf.with_suffix(".png")
        if is_emf:
            run([converter, "-i", str(mf), "-o", str(svg)])
        else:
            run([converter, "-o", str(svg), str(mf)])
        if svg.exists():
            run([rsvg, "-o", str(png), str(svg)])
            svg.unlink()
        if png.exists():
            rel_old = mf.relative_to(mdir).as_posix()
            rel_new = png.relative_to(mdir).as_posix()
            body = body.replace(rel_old, rel_new)
            mf.unlink()
            print(f"  converted {rel_old} -> {rel_new}")
        else:
            print(f"::warning::Could not convert {mf.name} to PNG.")
    return body


def _warn_no_bib(mdir: Path) -> None:
    print("::warning::No bibliography detected. If the manuscript cites "
          "sources, add a references.bib (Word citations must use live "
          "Zotero/Mendeley field codes to be extracted automatically).")
    (mdir / "references.bib").touch(exist_ok=True)


def main(manuscript_dir: str, *, source: str | None = None,
         reimport: bool = False) -> int:
    mdir = Path(manuscript_dir).resolve()
    if (mdir / "article.qmd").exists() and not reimport:
        print("Canonical article.qmd already exists; preserving copy-edits. "
              "Use --reimport to prepare a separate import for comparison.")
        return 0
    if source and not Path(source).exists() and (mdir / "source").is_dir():
        _candidates_in(mdir / "source")
    src = Path(source).resolve() if source else find_source(mdir)
    if not _is_real_source(src):
        raise SystemExit(f"Unsupported source file: {src}")
    # A reimport is a proposal, never a replacement for the edited article.
    target = mdir
    if reimport:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = mdir / ".imports" / stamp
        target.mkdir(parents=True)
        if (mdir / "references.bib").exists():
            shutil.copyfile(mdir / "references.bib", target / "references.bib")
    print(f"Source: {src}")
    ext = src.suffix.lower()
    (target / "figures").mkdir(exist_ok=True)
    if ext in {".qmd", ".md", ".rmd"}:
        passthrough(src, target)
        # Keep relative links and bibliography usable after an import.
        for asset in src.parent.iterdir():
            if asset == src or asset.name.startswith("."):
                continue
            if asset.name == "figures" and asset.is_dir():
                shutil.copytree(asset, target / "figures", dirs_exist_ok=True)
            elif asset.suffix.lower() in {".bib", ".png", ".jpg", ".jpeg", ".svg", ".pdf"}:
                if asset.resolve() != (target / asset.name).resolve():
                    shutil.copyfile(asset, target / asset.name)
    elif ext in {".docx", ".doc"}:
        from_docx(src, target)
    elif ext == ".tex":
        from_latex(src, target)
    print(f"Import complete: {target / 'article.qmd'}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manuscript_dir")
    ap.add_argument("--source", help="Explicit main upload when several files are present")
    ap.add_argument("--reimport", action="store_true", help="Write a proposal under .imports/; preserve edits")
    args = ap.parse_args()
    sys.exit(main(args.manuscript_dir, source=args.source, reimport=args.reimport))
