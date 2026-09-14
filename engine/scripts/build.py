"""Build isolated proofs and approve the exact reviewed files, without reimporting edits."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import platform
import zipfile
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import normalize
import r2meta
import validate_meta

ROOT = Path(__file__).resolve().parents[2]
INPUT_NAMES = ("_quarto.yml", "_extensions", "themes", "engine", "requirements.txt")
IGNORED = {".imports", ".quarto", "__pycache__", "ojs", "source", "approval.json"}
OUTPUT_SUFFIXES = {".aux", ".log", ".bcf", ".bbl", ".blg", ".out", ".pyc"}


def source_files(mdir):
    for base in [ROOT / name for name in INPUT_NAMES] + [mdir]:
        for p in sorted(base.rglob("*") if base.is_dir() else [base]):
            if not p.is_file() or any(part in IGNORED for part in p.relative_to(base.parent).parts):
                continue
            if p.suffix in OUTPUT_SUFFIXES or p.name in {"article.html", "article.pdf", "article.xml", "article.tex", "article-jats.zip", "_body.md", "_refs.json", "article.run.xml"}:
                continue
            yield p


def fingerprint(mdir):
    hashes = {}
    for p in source_files(mdir):
        key = ("manuscript/" + str(p.relative_to(mdir))) if p.is_relative_to(mdir) else str(p.relative_to(ROOT))
        hashes[key] = hashlib.sha256(p.read_bytes()).hexdigest()
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    return digest, hashes


def file_hashes(directory):
    return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(directory.rglob("*")) if p.is_file()}


def build(mdir, no_pdf=False, mode="draft"):
    mdir = Path(mdir).resolve()
    normalize.main(str(mdir))
    revision, sources = fingerprint(mdir)
    run_dir = ROOT / "_build" / mdir.name / (dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8])
    project = run_dir / "project"
    work = project / "manuscripts" / mdir.name
    work.mkdir(parents=True)
    for p in source_files(mdir):
        target = work / p.relative_to(mdir) if p.is_relative_to(mdir) else project / p.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, target)
    # Resolve relative assets in precisely the same two-level manuscript layout.
    manifest = dict(article_id=mdir.name, revision=revision, sources=sources,
                    created_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                    state="building", release_ready=False, mode=mode)
    manifest_path = run_dir / "manifest.json"

    def save():
        manifest_path.write_text(json.dumps(manifest, indent=2))

    def run(cmd, cwd=project):
        with (run_dir / "build.log").open("a") as log:
            log.write("\n$ " + " ".join(map(str, cmd)) + "\n")
            log.flush()
            subprocess.run(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, check=True)

    save()
    try:
        # Convert Word metafiles only in the isolated proof snapshot.
        qmd = work / "article.qmd"
        qmd.write_text(normalize._convert_metafiles(work, qmd.read_text()))
        manifest["tools"] = {
            "python": platform.python_version(),
            "quarto": subprocess.check_output(["quarto", "--version"], text=True).strip(),
            "pandoc": subprocess.check_output(["quarto", "pandoc", "--version"], text=True).splitlines()[0],
        }
        try:
            tex = json.loads(subprocess.check_output(["quarto", "tools", "info", "tinytex"], text=True))
            manifest["tools"]["tinytex"] = tex.get("version")
        except (subprocess.CalledProcessError, ValueError):
            manifest["tools"]["tinytex"] = "system LaTeX or unavailable"
        # Validate against the snapshotted configuration, not mutable live files.
        old_root = r2meta.REPO_ROOT
        try:
            r2meta.REPO_ROOT = project
            issues = validate_meta.check(work, mode)
            release_issues = validate_meta.check(work, "release") if mode != "release" else issues
        finally:
            r2meta.REPO_ROOT = old_root
        (run_dir / "issues.json").write_text(json.dumps(release_issues, indent=2))
        if any(i["severity"] == "error" for i in issues):
            raise ValueError("Source validation failed; see issues.json")
        article = str(work.relative_to(project) / "article.qmd")
        run(["quarto", "render", article, "--to", "r2-html", "--no-execute"])
        if not no_pdf:
            run(["quarto", "render", article, "--to", "r2-pdf", "--no-execute",
                 "-M", "latex-auto-install:false"])
        run(["quarto", "render", article, "--to", "r2-jats", "--no-execute"])
        jats_cmd = [sys.executable, str(project / "engine/scripts/enrich_jats.py"), str(work / "article.xml"), str(work),
                    "--issues", str(run_dir / "jats-issues.json")]
        if mode == "draft":
            jats_cmd.append("--draft")
        run(jats_cmd)
        release_issues.extend(json.loads((run_dir / "jats-issues.json").read_text()))
        (run_dir / "issues.json").write_text(json.dumps(release_issues, indent=2))
        outputs = run_dir / "outputs"
        outputs.mkdir()
        expected = ["article.html", "article.xml"] + ([] if no_pdf else ["article.pdf"])
        for name in expected:
            p = work / name
            if not p.is_file() or not p.stat().st_size:
                raise ValueError(f"Missing or empty output: {name}")
            shutil.copyfile(p, outputs / name)
        # Carry linked JATS assets alongside the XML in the proof bundle.
        from lxml import etree
        from urllib.parse import unquote, urlparse
        tree = etree.parse(str(work / "article.xml"), etree.XMLParser(resolve_entities=False, no_network=True))
        for href in set(tree.xpath('//@xlink:href', namespaces={"xlink": "http://www.w3.org/1999/xlink"})):
            if urlparse(href).scheme or href.startswith("#"):
                continue
            asset = (work / unquote(href)).resolve()
            if not asset.is_relative_to(work) or not asset.is_file():
                raise ValueError(f"Missing JATS asset: {href}")
            dest = outputs / asset.relative_to(work)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(asset, dest)
        # Packaging is only allowed when full publication metadata is available.
        ready = not no_pdf and not release_issues
        if ready:
            run([sys.executable, str(project / "engine/scripts/build_ojs.py"), str(work)])
            shutil.copyfile(work / "article-jats.zip", outputs / "article-jats.zip")
            for p in (work / "ojs").glob("*.xml"):
                shutil.copyfile(p, outputs / p.name)
        manifest.update(state="built", release_ready=ready, outputs=file_hashes(outputs))
        if fingerprint(mdir)[0] != revision:
            manifest["release_ready"] = False
            manifest["source_changed_during_build"] = True
    except Exception as e:
        manifest.update(state="failed", error=str(e), release_ready=False)
    finally:
        if manifest["state"] == "failed":
            # Keep successfully generated draft proofs available after a later
            # format fails. A failed bundle is never eligible for approval.
            outputs = run_dir / "outputs"
            outputs.mkdir(exist_ok=True)
            for name in ("article.html", "article.pdf", "article.xml"):
                if (work / name).is_file():
                    shutil.copyfile(work / name, outputs / name)
            manifest["outputs"] = file_hashes(outputs)
        save()
    print(f"Proof bundle: {run_dir}", flush=True)
    return run_dir


def approve(mdir, run_dir):
    mdir, run_dir = Path(mdir).resolve(), Path(run_dir).resolve()
    manifest = json.loads((run_dir / "manifest.json").read_text())
    if manifest["article_id"] != mdir.name or manifest["revision"] != fingerprint(mdir)[0]:
        raise ValueError("The manuscript or rendering engine changed; build and review a new proof")
    if manifest["state"] != "built" or not manifest["release_ready"]:
        raise ValueError("This proof is incomplete or has unresolved publication issues")
    expected = {"article.html", "article.pdf", "article.xml", "article-jats.zip", f"{mdir.name}_ojs_import.xml"}
    if not expected <= set(manifest.get("outputs", {})):
        raise ValueError("The proof bundle lacks required publication outputs")
    if file_hashes(run_dir / "outputs") != manifest["outputs"]:
        raise ValueError("Proof files changed since the build; approval refused")
    approval = dict(article_id=mdir.name, revision=manifest["revision"],
                    outputs=manifest["outputs"], approved_at=dt.datetime.now(dt.timezone.utc).isoformat())
    (run_dir / "approval.json").write_text(json.dumps(approval, indent=2))
    archive = shutil.make_archive(str(run_dir / "publication"), "zip", run_dir / "outputs")
    with zipfile.ZipFile(archive, "a", zipfile.ZIP_DEFLATED) as bundle:
        bundle.write(run_dir / "approval.json", "approval.json")
        bundle.write(run_dir / "manifest.json", "manifest.json")
    return Path(archive)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manuscript_dir")
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--mode", choices=["draft", "release"], default="draft")
    ap.add_argument("--approve", metavar="PROOF_DIRECTORY")
    args = ap.parse_args()
    if args.approve:
        print(approve(args.manuscript_dir, args.approve))
    else:
        result = build(args.manuscript_dir, args.no_pdf, args.mode)
        sys.exit(json.loads((result / "manifest.json").read_text())["state"] != "built")
