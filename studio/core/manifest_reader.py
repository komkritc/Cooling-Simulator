"""Optional reader for `manifest.tsv` provenance (deck md5, mat md5, status)."""
from __future__ import annotations

import csv
import os


def read_manifest(root: str) -> list[dict]:
    path = os.path.join(root, "manifest.tsv")
    if not os.path.isfile(path):
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def manifest_for(manifest: list[dict], run_hint: str) -> list[dict]:
    """Rows whose run_path mentions the given run directory name."""
    if not run_hint:
        return []
    key = run_hint.rstrip("/").split("/")[-1]
    return [r for r in manifest if key in (r.get("run_path") or "")]
