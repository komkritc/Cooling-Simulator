"""VAMPIRE run ingest for the browser.

Browsers cannot pick a directory, so the web app accepts
  * a ZIP of a run folder (recommended: it keeps the on-disk layout, so every parser
    and validator in studio.core runs unchanged), or
  * a multi-file selection (*_input.json / .mat / output_seedN.dat / manifest.tsv).
Uploads are staged in a temp dir, never in the project data tree, and are removed
when the process exits (plus stale ones swept per run).
Zip-slip protection: absolute paths, drive letters, '..' traversal.
"""
from __future__ import annotations

import atexit
import io
import os
import shutil
import time
import zipfile

_ROOTS: set[str] = set()
MAX_ZIP_FILES = 4000
STALE_SECONDS = 6 * 3600


def track(dest: str) -> None:
    """Register a staging directory so it is cleaned up on exit."""
    _ROOTS.add(dest)


def cleanup_all() -> None:
    for d in list(_ROOTS):
        shutil.rmtree(d, ignore_errors=True)
        _ROOTS.discard(d)


def cleanup_stale(now: float | None = None) -> int:
    """Remove staging dirs older than STALE_SECONDS (a browser tab may vanish)."""
    now = time.time() if now is None else now
    n = 0
    for d in list(_ROOTS):
        try:
            if now - os.path.getmtime(d) > STALE_SECONDS:
                shutil.rmtree(d, ignore_errors=True)
                _ROOTS.discard(d)
                n += 1
        except OSError:
            _ROOTS.discard(d)
    return n


atexit.register(cleanup_all)


# ------------------------------------------------------------------ safety ----
def safe_join(dest: str, name: str) -> str:
    """Reject absolute paths, drive letters, '..' traversal: anything escaping dest."""
    name = name.replace("\\", "/")
    if not name or name.startswith("/") or (len(name) > 1 and name[1] == ":"):
        raise ValueError(f"refusing unsafe path in the upload: {name}")
    root = os.path.normpath(os.path.abspath(dest))
    p = os.path.normpath(os.path.join(root, name))
    if p != root and not p.startswith(root + os.sep):
        raise ValueError(f"refusing unsafe path in the upload: {name}")
    return p


def extract_zip(uploaded, dest: str) -> str:
    """Unpack an uploaded ZIP into dest; returns the run folder to hand to AnalysisSession."""
    data = io.BytesIO(uploaded.getvalue())
    if not zipfile.is_zipfile(data):
        raise ValueError("that file is not a .zip archive")
    data.seek(0)
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest, exist_ok=True)
    with zipfile.ZipFile(data) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        if len(names) > MAX_ZIP_FILES:
            raise ValueError(f"too many files in the ZIP ({len(names)}); zip a single "
                             "rate_*Kns run folder, not the whole ensemble")
        for n in names:
            target = safe_join(dest, n)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(n) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    return _resolve_run_dir(dest)


def write_files(files, dest: str) -> str:
    """Write individually-uploaded files, keeping their relative paths."""
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest, exist_ok=True)
    for f in files:
        target = safe_join(dest, f.name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as out:
            out.write(f.getvalue())
    return _resolve_run_dir(dest)


def _resolve_run_dir(d: str) -> str:
    """SimpleWindow._resolve(): dig down to a folder holding seed_* directories."""
    if not any(n.startswith("seed_") for n in os.listdir(d)):
        for root, dirs, _ in os.walk(d):
            if any(n.startswith("rate_") for n in dirs):
                return os.path.join(root, sorted(n for n in dirs
                                                 if n.startswith("rate_"))[0])
    return d
