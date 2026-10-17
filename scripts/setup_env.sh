#!/bin/sh
# One command to build the project environment from nothing:   scripts/setup_env.sh [folder]     (default folder: .venv)
# Needs Python 3.14 (Homebrew: brew install python@3.14). Always use `<folder>/bin/python -m pip ...`, never a bare pip.
set -e
cd "$(dirname "$0")/.."
VENV=${1:-.venv}
command -v python3.14 >/dev/null || { echo "python3.14 not found (brew install python@3.14)"; exit 1; }
python3.14 -m venv "$VENV"
"$VENV/bin/python" -m pip install --disable-pip-version-check -r requirements.txt
"$VENV/bin/python" -m pip install --disable-pip-version-check --no-deps -r requirements-generation.txt
echo "environment ready in $VENV ($("$VENV/bin/python" --version)); check it with: $VENV/bin/python -m pytest -q"
