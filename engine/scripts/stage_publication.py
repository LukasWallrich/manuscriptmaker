"""Verify a reviewed CI proof bundle and stage its exact files for publication."""
import argparse
import json
import shutil
from pathlib import Path

import build


def stage(mdir, bundle, destination):
    mdir = Path(mdir).resolve()
    fixtures = json.loads((build.ROOT / "engine/fixtures.json").read_text())
    if mdir.name in fixtures:
        raise ValueError("Test fixtures cannot be published")
    # This also checks revision, completeness and every output checksum.
    build.approve(mdir, bundle)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for source in (Path(bundle) / "outputs").rglob("*"):
        if not source.is_file():
            continue
        relative = source.relative_to(Path(bundle) / "outputs")
        name = Path("index.html") if str(relative) == "article.html" else relative
        (destination / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination / name)
    shutil.copyfile(Path(bundle) / "approval.json", destination / "approval.json")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manuscript_dir")
    ap.add_argument("bundle")
    ap.add_argument("destination")
    args = ap.parse_args()
    stage(args.manuscript_dir, args.bundle, args.destination)
