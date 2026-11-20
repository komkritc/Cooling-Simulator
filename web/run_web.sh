#!/usr/bin/env bash
# Launch the Streamlit web app.  Uses web/.venv (a real directory) so the shared
# app/.venv used by the desktop Qt app is never touched.
#
#   ./run_web.sh              -> serve on :8590 (headless)
#   ./run_web.sh 8600         -> serve on :8600
#   ./run_web.sh --open       -> serve and open a browser
#   ./run_web.sh --tests      -> run the acceptance suite, no server
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "creating web/.venv (streamlit + pinned numpy/matplotlib) ..."
  python3 -m venv .venv
  .venv/bin/python -m pip install -q --upgrade pip
  .venv/bin/python -m pip install -q -r requirements.txt
fi
PY=.venv/bin/python

PORT=8590; OPEN=""
for a in "$@"; do
  case "$a" in
    --tests) exec "$PY" -m pytest tests -q ;;
    --open)  OPEN="--server.headless false" ;;
    ''|*[!0-9]*) ;;                      # ignore other args for now
    *) PORT="$a" ;;
  esac
done

# stale uploads from dead sessions are removed at start-up (uploads.cleanup_stale
# also runs on every page load).
exec "$PY" -m streamlit run streamlit_app.py \
  --server.port "$PORT" --server.headless true $OPEN
