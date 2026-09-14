#!/usr/bin/env bash
# Build isolated proofs; outputs and diagnostics are under _build/<id>/<run>/.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
args=()
if [[ "${NO_PDF:-0}" == "1" ]]; then args+=(--no-pdf); fi
exec "$PYTHON" "$HERE/build.py" "$@" "${args[@]}"
