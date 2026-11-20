#!/usr/bin/env python3
"""Refresh web/baselines/web_golden.json from the DESKTOP app (single source of truth).

Run it with the **desktop** venv, from app/:

    .venv/bin/python web/baselines/capture_from_desktop.py > /tmp/golden.new.json

It prints the JSON. Compare it with the current file, then replace it and run
`web/.venv/bin/python -m pytest web/tests -q`: the web tests assert the web app
reproduces exactly these bytes and numbers. Nothing here writes the baseline file
itself, on purpose - a baseline change should be a deliberate edit.

What it captures, with the desktop sidebar checkboxes set the way webapp/context.
DEFAULTS sets them:

* three figures (dpi 200, savefig with facecolor, no VAMPIRE run loaded, 500 K/ns):
  dark + no smoothing, light + no smoothing, light + smoothing  <- the web default
* the VAMPIRE comparison of every bundled sample run, through studio.core
  (AnalysisSession -> run_comparison -> validate), i.e. the code both apps use.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import matplotlib                                                  # noqa: E402
matplotlib.use("Agg")
import numpy as np                                                # noqa: E402
from PySide6.QtCore import QSettings                               # noqa: E402
from PySide6.QtWidgets import QApplication                        # noqa: E402

APP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, APP)
WEB = os.path.join(APP, "web")

RATE = 500.0
VARIANTS = [("figure", False, True),           # (key, sg_on, dark)
            ("figure_light", False, False),
            ("figure_default", True, False)]   # <- what the web app opens with
ORG, APPN = "CoolingModelComparison", "MECoolingSimulator"


def figure_hash(sg_on: bool, dark: bool) -> dict:
    """One figure straight out of SimpleWindow._plot."""
    from studio.gui.simple_window import SimpleWindow
    w = SimpleWindow()
    w.cb_dark.setChecked(dark)                 # the desktop starts light (app.py)
    w.cb_sg.setChecked(sg_on)
    w.ed_rates.setText(f"{RATE:g}")
    _pump(0.5)
    w.run_me()
    _wait(lambda: bool(getattr(w, "results", None)))
    _pump(0.2)
    buf = io.BytesIO()
    w.fig.savefig(buf, format="png", dpi=200, facecolor=w.fig.get_facecolor())
    b = buf.getvalue()
    assert len(w.fig.axes[0].get_lines()) == (3 if sg_on else 2), "unexpected plot content"
    assert (w.session is None or not w.session.seeds), "a VAMPIRE run leaked into the capture"
    return {"dpi": 200, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}


def sample_contract(run_dir: str) -> dict:
    """Comparison numbers for one bundled run, from studio.core (shared by both apps)."""
    from studio.core.session import AnalysisSession
    s = AnalysisSession(run_dir)
    s.load_seeds()
    s.apply_settings(d_nm=4.0, rate_K_per_ns=s.rate_deck)
    r = s.run_comparison()
    st = r.stats
    i = int(np.argmin(np.abs(st.T - 300.0)))
    assert abs(st.T[i] - 300.0) <= 0.5, "no VAMPIRE row at 300 K"
    mz = float(np.median(st.mz_per_seed[:, i]))
    msv = float(np.median(st.mlen[:, i]))
    me = float(r.m_me[-1] / r.ms_me[-1])
    iss = s.validate()
    return dict(
        seeds=len(s.seeds), rate_deck=float(s.rate_deck), mapping_ok=s.cfg is not None,
        me_ratio_at_300K=round(me, 4),
        vampire_ratio_at_300K=round(mz / msv, 4),
        me_minus_vampire=round(abs(me - mz / msv), 4),
        rmse_vs_vampire=round(float(r.rmse), 4),
        mean_mz_final=round(float(np.mean(st.mz_per_seed[:, i])), 4),
        up=int(st.up), down=int(st.down),
        reversed_seeds=int((st.mz_per_seed[:, i] < 0).sum()),
        validation={"pss": sum(1 for x in iss if x.severity == "pass"),
                    "warning": sum(1 for x in iss if x.severity == "warning"),
                    "critical": sum(1 for x in iss if x.severity == "critical")},
    )


def _pump(dt: float) -> None:
    end = time.time() + dt
    while time.time() < end:
        QApplication.processEvents()
        time.sleep(0.01)


def _wait(cond, timeout: float = 180.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        QApplication.processEvents()
        if cond():
            return
        time.sleep(0.01)
    raise RuntimeError("timed out waiting for the desktop app")


def main() -> None:
    app = QApplication.instance() or QApplication([])          # noqa: F841
    st = QSettings(ORG, APPN)
    saved = dict((k, st.value(k)) for k in st.allKeys())
    st.remove("vampire_path")                                  # capture without VAMPIRE data
    st.sync()
    from importlib.metadata import version as pkg_version
    out = {"matplotlib": pkg_version("matplotlib")}
    for key, sg, dark in VARIANTS:
        out[key] = figure_hash(sg, dark)
        print(f"# {key}: {out[key]}", file=sys.stderr)
    runs = os.path.join(WEB, "sample_data", "vampire_damp0p05_D4nm",
                        "cooling_T800", "runs")
    out["vampire_samples"] = {
        "how": ("captured with the desktop venv using studio.core only (AnalysisSession."
                "load_seeds -> apply_settings(d_nm=4.0, rate=<deck rate>) -> "
                "run_comparison() -> validate()), i.e. the same calls the desktop "
                "SimpleWindow makes; the web app must reproduce every value below"),
        "runs": {n: sample_contract(os.path.join(runs, n))
                 for n in sorted(os.listdir(runs))},
    }
    for k, v in saved.items():
        if k != "vampire_path":
            st.setValue(k, v)
    st.sync()
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
