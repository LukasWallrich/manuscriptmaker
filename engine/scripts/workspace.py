"""Local copy-editing workspace. Run: python engine/scripts/workspace.py [--port 8765]."""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import build
import review_packet
import upload

ROOT = build.ROOT
EDITABLE = ("article.qmd", "_metadata.yml", "references.bib")
TOKEN = secrets.token_urlsafe(24)
LOCK = threading.Lock()
JOBS = {}


def manuscript(name):
    if not name or Path(name).name != name or name.startswith("_"):
        raise ValueError("Choose a manuscript from the list")
    p = (ROOT / "manuscripts" / name).resolve()
    if not p.is_relative_to(ROOT / "manuscripts") or not p.is_dir():
        raise ValueError("Unknown manuscript")
    return p


def read_files(p):
    return {name: (p / name).read_text() if (p / name).exists() else "" for name in EDITABLE}


def edit_revision(files):
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def save_files(p, files, revision):
    if set(files) != set(EDITABLE) or not all(isinstance(v, str) for v in files.values()):
        raise ValueError("Save must contain the manuscript, metadata and bibliography")
    with LOCK:
        if edit_revision(read_files(p)) != revision:
            raise ValueError("Files changed outside this window. Reload before saving to preserve those edits.")
        # Each replacement is atomic; the shared lock keeps workspace requests
        # from observing a partially saved set. Git retains editorial history.
        for name, text in files.items():
            tmp = p / (name + ".saving")
            tmp.write_text(text)
            tmp.replace(p / name)
    return edit_revision(files)


def proof_state(p):
    candidates = sorted((ROOT / "_build" / p.name).glob("*/manifest.json"))
    if not candidates:
        return None
    path = candidates[-1]
    manifest = json.loads(path.read_text())
    manifest["run"] = path.parent.name
    manifest["current"] = manifest["revision"] == build.fingerprint(p)[0]
    issues = path.parent / "issues.json"
    manifest["issues"] = json.loads(issues.read_text()) if issues.exists() else []
    return manifest


def start_build(p, no_pdf):
    with LOCK:
        if any(job == "building" for job in JOBS.values()):
            raise ValueError("A proof is already building. Wait for it to finish.")
        JOBS[p.name] = "building"

    def task():
        try:
            cmd = [sys.executable, str(ROOT / "engine/scripts/build.py"), str(p)]
            if no_pdf:
                cmd.append("--no-pdf")
            result = subprocess.run(cmd, capture_output=True, text=True)
            JOBS[p.name] = "done" if result.returncode == 0 else "failed"
        except Exception:
            JOBS[p.name] = "failed"
    threading.Thread(target=task, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, data, mime="application/json", status=200):
        if not isinstance(data, bytes):
            data = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.headers.get("Host") not in self.server.allowed_hosts:
            return self.send({"error": "Invalid host"}, status=403)
        path = unquote(urlparse(self.path).path)
        try:
            if path == "/":
                html = (ROOT / "engine/workspace/index.html").read_text().replace("__TOKEN__", TOKEN)
                return self.send(html.encode(), "text/html; charset=utf-8")
            if path == "/api/manuscripts":
                return self.send([p.name for p in sorted((ROOT / "manuscripts").iterdir())
                                  if p.is_dir() and not p.name.startswith("_")])
            if path.startswith("/api/manuscript/"):
                p = manuscript(path.rsplit("/", 1)[-1])
                files = read_files(p)
                return self.send(dict(files=files, edit_revision=edit_revision(files),
                                      proof=proof_state(p), review=review_packet.review_state(p), job=JOBS.get(p.name)))
            if path.startswith("/review-package/"):
                parts = path.split("/")
                p = manuscript(parts[2])
                packet_id = parts[3]
                if len(packet_id) != 32 or any(c not in "0123456789abcdef" for c in packet_id):
                    raise ValueError("Unknown review package")
                target = ROOT / "_build/llm-review" / p.name / packet_id / "review-package.zip"
                return self.send(target.read_bytes(), "application/zip")
            if path.startswith("/proof/"):
                parts = path.split("/")
                p = manuscript(parts[2])
                base = ROOT / "_build" / p.name
                target = (base / "/".join(parts[3:])).resolve()
                if not target.is_relative_to(base.resolve()) or not target.is_file():
                    raise ValueError("Unknown proof file")
                # Only expose deliverables and the build log, not source snapshots.
                if "outputs" not in target.parts and target.name not in {"build.log", "publication.zip"}:
                    raise ValueError("Unknown proof file")
                import mimetypes
                return self.send(target.read_bytes(), mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            if path == "/logo.png":
                return self.send((ROOT / "themes/r2/assets/logo.png").read_bytes(), "image/png")
            if path == "/Carlito-Regular.ttf":
                return self.send((ROOT / "themes/r2/assets/fonts/Carlito-Regular.ttf").read_bytes(), "font/ttf")
            self.send({"error": "Not found"}, status=404)
        except (OSError, ValueError, KeyError) as e:
            self.send({"error": str(e)}, status=400)

    def do_POST(self):
        if self.headers.get("Host") not in self.server.allowed_hosts or self.headers.get("X-Workspace-Token") != TOKEN:
            return self.send({"error": "Reload the workspace to continue"}, status=403)
        try:
            size = int(self.headers.get("Content-Length", 0))
            if not 0 < size <= (42_000_000 if self.path == "/api/upload" else 10_000_000):
                raise ValueError("Request is empty or too large")
            data = json.loads(self.rfile.read(size))
            if self.path == "/api/upload":
                with LOCK:
                    name = upload.create(data["article"], data["files"], data.get("main", ""))
                return self.send(dict(article=name))
            p = manuscript(data["article"])
            if self.path == "/api/save":
                revision = save_files(p, data["files"], data["edit_revision"])
                return self.send(dict(edit_revision=revision))
            if self.path == "/api/build":
                start_build(p, bool(data.get("no_pdf")))
                return self.send(dict(state="building"))
            if self.path == "/api/review-package":
                with LOCK:
                    if JOBS.get(p.name) == "building":
                        raise ValueError("Wait for the proof build to finish before exporting")
                    folder = review_packet.packet(p)
                return self.send(dict(download=f"/review-package/{p.name}/{folder.name}"))
            if self.path == "/api/review-import":
                if not isinstance(data.get("result"), dict):
                    raise ValueError("Choose a review.json result")
                return self.send(dict(review=review_packet.import_result(p, data["result"])))
            if self.path == "/api/approve":
                state = proof_state(p)
                if not state or data.get("run") != state["run"]:
                    raise ValueError("The proof changed. Review the current proof first.")
                run = ROOT / "_build" / p.name / state["run"]
                build.approve(p, run)
                return self.send(dict(download=f"/proof/{p.name}/{run.name}/publication.zip"))
            self.send({"error": "Not found"}, status=404)
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, upload.zipfile.BadZipFile) as e:
            self.send({"error": str(e)}, status=400)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    port = server.server_address[1]
    server.allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    url = f"http://127.0.0.1:{port}"
    print(f"Copy-editing workspace: {url}", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    server.serve_forever()
