"""Web-app acceptance tests: numbers, figure bytes, upload safety.

Run from app/:  web/.venv/bin/python -m pytest web/tests -q
These tests import webapp (Streamlit-free parts only), so they run headless and
need no PySide6 - the figure gate uses a hash captured from the desktop app.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest

WEB = Path(__file__).resolve().parents[1]
APP = WEB.parent
sys.path.insert(0, str(WEB))
sys.path.insert(0, str(APP))

from webapp import context as ctx, runner, plot_simple, uploads  # noqa: E402

GOLD = json.loads((WEB / "baselines" / "web_golden.json").read_text())
DESKTOP_GOLDEN = json.loads((APP / "baselines" / "golden.json").read_text())


def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, facecolor=fig.get_facecolor())
    return buf.getvalue()


# ----------------------------------------------------------------- numbers ----
@pytest.mark.parametrize("rate", sorted(DESKTOP_GOLDEN["rates"], key=float))
def test_rates_match_desktop_golden(rate):
    """Every ME column value in the desktop golden baseline is reproduced (3 dp)."""
    s = dict(ctx.DEFAULTS)
    r, T, m, P, ms, Tc = runner.run_me(s, [float(rate)])[0]
    for line in DESKTOP_GOLDEN["rates"][rate]["raw_lines"]:
        mm = re.match(r"\s*(\d+)\s*\|\s*[-+0-9. ]+\|\s*([-+0-9.]+)\|", line)
        if not mm:
            continue
        Tq, want = float(mm.group(1)), float(mm.group(2))
        i = int(abs(T - Tq).argmin())
        assert abs(T[i] - Tq) < 1e-9, f"{rate}: no row at {Tq} K"
        assert abs(float(m[i]) - want) <= 6e-4, f"{rate} K/ns @{Tq} K: {m[i]} != {want}"


def _fig_hash(dark: bool, sg_on: bool) -> str:
    s = dict(ctx.DEFAULTS, dark=dark, sg_on=sg_on)
    fig, _ = plot_simple.draw(s, runner.run_me(s, [500.0]), None,
                              ctx.palette("dark" if dark else "light"))
    return hashlib.sha256(_png(fig)).hexdigest()


@pytest.mark.parametrize("key,dark,sg", [("figure", True, False),
                                         ("figure_light", False, False),
                                         ("figure_default", False, True)])
def test_figure_is_byte_identical_to_desktop(key, dark, sg):
    """Same matplotlib + same drawing code -> the PNG bytes the desktop app saves.

    Each variant was captured from the desktop app (offscreen, same sidebar
    checkboxes, no VAMPIRE run) and stored in baselines/web_golden.json.
    """
    assert _fig_hash(dark, sg) == GOLD[key]["sha256"], f"{key}: figure bytes changed"


def test_web_default_is_light_with_smoothing():
    """The web app starts light and smoothed; both figures are the desktop bytes."""
    assert ctx.DEFAULTS["dark"] is False and ctx.DARK is False
    assert ctx.DEFAULTS["sg_on"] is True
    assert _fig_hash(ctx.DEFAULTS["dark"], ctx.DEFAULTS["sg_on"]) == \
        GOLD["figure_default"]["sha256"]


def test_pins_are_the_pinned_versions():
    from importlib.metadata import version
    assert version("matplotlib") == GOLD["matplotlib"] == ctx.MPL_VERSION


# ------------------------------------------------------- VAMPIRE sample data ----
SAMPLE_RUNS = sorted(GOLD["vampire_samples"]["runs"])


def test_bundled_runs_are_all_present():
    """Every run named in the contract is bundled, with the same seed count."""
    got = {Path(d).name for d in ctx.sample_run_dirs()}
    assert set(SAMPLE_RUNS) <= got, f"missing {set(SAMPLE_RUNS) - got}"


@pytest.mark.parametrize("name", SAMPLE_RUNS)
def test_bundled_sample_matches_desktop_contract(name):
    """The web app reproduces the desktop comparison for every bundled run."""
    from studio.core.session import AnalysisSession
    v = GOLD["vampire_samples"]["runs"][name]
    run = next(d for d in ctx.sample_run_dirs() if Path(d).name == name)
    s = AnalysisSession(run)
    s.load_seeds()
    assert len(s.seeds) == v["seeds"], f"{name}: seed count changed"
    assert abs(s.rate_deck - v["rate_deck"]) < 1e-9
    assert s.cfg is not None, s.mapping_error

    st = runner.vampire_stats(s)
    ratio, median_mz, _, why = runner.vampire_final(st, 300.0)
    assert ratio is not None, why
    assert round(ratio, 4) == v["vampire_ratio_at_300K"], name
    assert round(float(np.mean(st.mz_per_seed[:, -1])), 4) == v["mean_mz_final"], name

    ui = dict(ctx.DEFAULTS)                       # d = 4 nm, same cell/moment as the decks
    _, T, m, P, ms, Tc = runner.run_me(ui, [v["rate_deck"]])[0]
    me_ratio = float(m[-1] / ms[-1])
    assert round(me_ratio, 4) == v["me_ratio_at_300K"], name
    assert round(abs(me_ratio - ratio), 4) == v["me_minus_vampire"], name
    assert round(st.rmse_me(T, m), 4) == v["rmse_vs_vampire"], name

    issues = s.validate()
    counts = {sev: sum(1 for i in issues if i.severity == sev)
              for sev in ("pass", "warning", "critical")}
    assert counts == {"pass": v["validation"]["pss"],
                      "warning": v["validation"]["warning"],
                      "critical": v["validation"]["critical"]}, name


def test_sample_data_is_aggregated_only():
    """The bundled sample carries only what a comparison needs: no raw stdout logs."""
    for d in ctx.sample_run_dirs():
        names = {p.name for root, _, fs in os.walk(d) for p in map(Path, fs)}
        assert any(n.startswith("output_seed") for n in names), d
        for bad in ("run_stdout.txt",):
            assert bad not in names, f"{bad} should not ship in a public sample"


# ------------------------------------------------------------- upload safety ----
class _Upload:
    def __init__(self, data: bytes) -> None:
        self._d = data

    def getvalue(self) -> bytes:
        return self._d


def _zip_with(entries) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in entries:
            z.writestr(name, "x")
    return buf.getvalue()


@pytest.mark.parametrize("entry", ["../escape.txt", "a/../../escape.txt", "/abs.txt",
                                   "..\\escape.txt", "C:/escape.txt"])
def test_zip_slip_is_refused(entry):
    import tempfile
    d = tempfile.mkdtemp(prefix="wtest_")
    uploads.track(d)
    with pytest.raises(ValueError):
        uploads.extract_zip(_Upload(_zip_with([entry])), d)
    uploads.cleanup_all()


def test_zip_with_real_run_resolves_to_run_dir(tmp_path):
    src = ctx.sample_run_dirs()[0]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(src):
            for f in files:
                p = Path(root) / f
                z.write(p, p.relative_to(src).as_posix())
    dest = str(tmp_path / "up")
    uploads.track(dest)
    got = uploads.extract_zip(_Upload(buf.getvalue()), dest)
    # zipped from inside rate_*Kns -> the extraction root IS the run folder
    assert any(p.name.startswith("seed_") for p in Path(got).iterdir())
    uploads.cleanup_all()
