"""Audit manager: comparison records that make any comparison reproducible.

A record is a folder `cmp_<UTC timestamp>/` containing:
  record.json      - parameters, mapping, validation, model id, settings, env
  numbers.txt      - numeric summary (same format as validated numbers_<rate>.txt)
  arrays.csv       - T, mean, sem, ME curve, Gamma
  mz.png/pdf/svg   - exported figures
  checksums.sha256 - of every file in the record
Re-running a record rebuilds the session from stored settings and re-executes
the comparison (acceptance: identical numbers).
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import time

import numpy as np


def _env_versions() -> dict:
    import matplotlib
    import sys
    return {"python": sys.version, "numpy": np.__version__,
            "matplotlib": matplotlib.__version__, 
            "platform": platform.platform()}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def save_record(session, result, issues, figures: dict[str, bytes] | None = None,
                out_root: str | None = None, accepted_warnings: list[str] | None = None,
                ) -> str:
    """Write a comparison record; returns the record directory path."""
    out_root = out_root or os.path.join(session.data_root, "records")
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    rec = os.path.join(out_root, f"cmp_{stamp}")
    os.makedirs(rec, exist_ok=True)

    numbers = session.numbers_lines(result)
    with open(os.path.join(rec, "numbers.txt"), "w") as f:
        f.write("\n".join(numbers) + "\n")

    from .plotting_engine import arrays_csv
    arrays_csv(os.path.join(rec, "arrays.csv"), result)

    if figures:
        for name, png_bytes in figures.items():
            with open(os.path.join(rec, name), "wb") as f:
                f.write(png_bytes)

    record = {
        "id": f"cmp_{stamp}",
        "created_utc": stamp,
        "run_dir": session.run_dir,
        "settings": {"rf_d_nm": session.rf_d, "rf_d_snapped": session.rf_d_snapped,
                     "damping_interpretation": session.damping_interpretation,
                     "dT_grid_K": session.dT_grid_K,
                     "overrides": getattr(session, "overrides", {}),
                     "volume_mode": (session.cfg.volume_mode
                                     if session.cfg else "deck")},
        "extracted_parameters": session.table.as_dicts(),
        "unrecognised": [{"file": s.file, "line": s.line, "raw": s.raw}
                         for s in session.table.unrecognised],
        "me_config": session.cfg.as_dict() if session.cfg else None,
        "rf_model": session.model_meta,
        "deck_md5": (hashlib.md5(open(session.deck.path, "rb").read()).hexdigest()
                     if session.deck.path else None),
        "output_provenance": session.provenance,
        "validation": [{"rule": i.rule, "severity": i.severity, "message": i.message,
                        "evidence": [s.cite() for s in i.evidence]} for i in issues],
        "accepted_warnings": accepted_warnings or [],
        "seeds": {"loaded": len(session.seeds),
                  "ids": [s.seed for s in session.seeds],
                  "paths": [s.path for s in session.seeds]},
        "result_summary": {"m300_ME": result.m300, "P_rev_ME": result.prev300,
                           "rmse": result.rmse,
                           "vampire_mean_final": result.stats.mean_final,
                           "vampire_sem_final": result.stats.sem_final,
                           "up": result.stats.up, "down": result.stats.down,
                           "partial": result.stats.partial},
        "environment": _env_versions(),
    }
    with open(os.path.join(rec, "record.json"), "w") as f:
        json.dump(record, f, indent=1, default=str)

    with open(os.path.join(rec, "checksums.sha256"), "w") as f:
        for name in sorted(os.listdir(rec)):
            if name != "checksums.sha256":
                f.write(f"{sha256_file(os.path.join(rec, name))}  {name}\n")
    return rec


def load_record(path: str) -> dict:
    with open(os.path.join(path, "record.json")) as f:
        return json.load(f)


def rerun_from_record(record: dict):
    """Rebuild an AnalysisSession with the stored settings (for exact re-runs)."""
    from .session import AnalysisSession
    st = record["settings"]
    s = AnalysisSession(record["run_dir"], rf_d_nm=st["rf_d_nm"],
                        damping_interpretation=st["damping_interpretation"],
                        dT_grid_K=st["dT_grid_K"])
    ov = st.get("overrides", {})
    if ov:
        s.apply_settings(d_nm=ov.get("d_nm"),
                         rate_K_per_ns=ov.get("rate_K_per_ns"),
                         volume_mode=ov.get("volume_mode"))
    return s
