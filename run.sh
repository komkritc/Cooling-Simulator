#!/usr/bin/env bash
# Launch the VAMPIRE - ME Comparison Studio (uses the project's pinned venv).
cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then PY=.venv/bin/python; else PY=python3; fi
exec "$PY" app.py "$@"
