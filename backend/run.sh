#!/usr/bin/env bash
# One-command backend launcher. Uses the project's venv Python directly so you
# don't have to `source .venv/Scripts/activate` first. Forwards any extra args
# straight to main.py (e.g. ./run.sh --port 9000).

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$SCRIPT_DIR"

# Pick the right Python path for Windows (Git Bash / MSYS) vs *nix.
if [[ -x ".venv/Scripts/python.exe" ]]; then
  PY=".venv/Scripts/python.exe"
elif [[ -x ".venv/bin/python" ]]; then
  PY=".venv/bin/python"
else
  echo "error: no virtualenv found. Run setup first:" >&2
  echo "  python -m venv .venv && source .venv/Scripts/activate && pip install -e ." >&2
  exit 1
fi

exec "$PY" main.py "$@"
