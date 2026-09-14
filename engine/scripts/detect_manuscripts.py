"""Select existing manuscripts affected by source or shared-pipeline changes."""
import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHARED = ("engine/", "_extensions/", "themes/", ".github/workflows/", "tests/", "_quarto.yml", "requirements")


def select(paths, root=ROOT):
    all_ids = sorted(p.name for p in (root / "manuscripts").iterdir()
                     if p.is_dir() and not p.name.startswith("_"))
    if any(path.startswith(SHARED) for path in paths):
        return all_ids
    changed = {path.split("/")[1] for path in paths if path.startswith("manuscripts/") and len(path.split("/")) >= 3}
    return [name for name in all_ids if name in changed]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base")
    args = ap.parse_args()
    paths = subprocess.check_output(["git", "diff", "--name-only", args.base + "...HEAD"], text=True).splitlines() if args.base else ["engine/"]
    print(json.dumps(dict(id=select(paths))))
