#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON="$ROOT/.venv/bin/python"
else
    PYTHON="${PYTHON:-python3}"
fi

if ! "$PYTHON" -c "import PySide6, psutil" >/dev/null 2>&1; then
    printf '%s\n' "BrightNova dependencies are missing."
    printf '%s\n' "Install them with:"
    printf '%s\n' "  cd \"$ROOT\""
    printf '%s\n' "  python3 -m venv .venv"
    printf '%s\n' "  .venv/bin/pip install -r requirements.txt"
    exit 1
fi

exec "$PYTHON" "$ROOT/main.py" "$@"
