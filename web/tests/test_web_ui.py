"""Headless UI tests with Streamlit's AppTest: widgets, callbacks, state flow.

Run: web/.venv/bin/python -m pytest web/tests -q
AppTest executes the real script (web/streamlit_app.py), clicks the real buttons and
runs the real callbacks - it is the closest thing to clicking through the page.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEB))
sys.path.insert(0, str(WEB.parent))

from streamlit.testing.v1 import AppTest                      # noqa: E402

from webapp import context as ctx                             # noqa: E402

APP = str(WEB / "streamlit_app.py")


@pytest.fixture()
def at() -> AppTest:
    a = AppTest.from_file(APP, default_timeout=300)
    a.run()
    assert not a.exception, a.exception
    return a


@pytest.fixture()
def at_noboot() -> AppTest:
    """Fresh app with the boot auto-load suppressed: pristine desktop defaults."""
    a = AppTest.from_file(APP, default_timeout=300)
    a.session_state["boot_done"] = True
    a.run()
    assert not a.exception, a.exception
    return a


def _sample(at, rate: str) -> AppTest:
    sel = next(s for s in at.sidebar.selectbox if s.label.startswith("example run"))
    sel.select(rate).run()
    at.sidebar.button(key="b_load").click().run()
    assert not at.exception, at.exception
    return at


def test_starts_like_the_desktop(at_noboot):
    """Every parameter opens at the desktop SimpleWindow default.

    The web app deliberately differs in one way only: Savitzky-Golay smoothing of the
    *plotted* curve starts switched on (the numbers, the CSV export and the solver are
    untouched). The theme starts light, as on the desktop (app.py reads theme=light).
    """
    ss = at_noboot.session_state
    for key, want in [("set_rates_text", "500"), ("wid_d_nm", 4.0), ("wid_t0", 800.0),
                      ("wid_t1", 300.0), ("wid_b_nm", 1.00531), ("wid_damp", 0.05),
                      ("wid_atoms", 4602), ("wid_p0", 0.5), ("wid_grid", True),
                      ("wid_params_on", True), ("wid_invert_x", True),
                      ("wid_dark", False), ("wid_sg_on", True),
                      ("wid_sg_win", 15.0), ("wid_sg_poly", 3)]:
        assert ss[key] == want, key
    assert ss["me_results"] == []                       # nothing computed until Run ME


def test_run_me_produces_curves_and_a_figure(at_noboot):
    at_noboot.sidebar.button(key="b_run").click().run()
    res = at_noboot.session_state["me_results"]
    assert [round(float(r[0]), 3) for r in res] == [500.0]
    assert round(float(res[0][2][-1]), 6) == 0.774476   # == desktop/golden m(300 K)
    assert at_noboot.session_state["fig_obj"] is not None
    assert at_noboot.session_state["notice"] == ""
    assert at_noboot.session_state["run_params"]["d_nm"] == 4.0


def test_bad_rate_shows_the_desktop_message(at):
    at.sidebar.text_input(key="set_rates_text").set_value("abc").run()
    at.sidebar.button(key="b_run").click().run()
    assert at.session_state["notice"] == ctx.RATE_MSG


def test_boot_opens_on_200Kns(at):
    """First visit: the 200 K/ns sample is selected, loaded and the ME already ran."""
    names = [ctx.sample_label(d) for d in ctx.sample_run_dirs()]
    if not names:
        pytest.skip("no bundled sample data")
    assert at.session_state["wid_sample"] == ctx.default_sample_label()
    assert "200" in at.session_state["wid_sample"]
    assert at.session_state["session"] is not None
    assert at.session_state["me_results"]
    assert not at.session_state["notice"]


def test_sample_dropdown_autoloads(at):
    """Picking a bundled sample in the dropdown loads it without pressing Load."""
    names = [ctx.sample_label(d) for d in ctx.sample_run_dirs()]
    if not names:
        pytest.skip("no bundled sample data")
    at.sidebar.selectbox(key="wid_sample").set_value(names[0]).run()
    assert at.session_state["session"] is not None
    assert names[0].split()[0] in at.session_state["vampire_info"]


def test_temperature_order_is_checked(at):
    at.sidebar.number_input(key="wid_t0").set_value(200.0).run()
    at.sidebar.button(key="b_run").click().run()
    assert at.session_state["notice"] == ctx.T_MSG


def test_diameter_change_reruns(at):
    """Editing the diameter box re-runs the ME, like the desktop."""
    at.sidebar.button(key="b_run").click().run()
    before = at.session_state["me_results"][0][2][-1]
    at.sidebar.number_input(key="wid_d_nm").set_value(5.0).run()
    assert at.session_state["wid_d_nm"] == 5.0
    after = at.session_state["me_results"][0][2][-1]
    assert float(after) != float(before)
    assert at.session_state["run_params"]["d_nm"] == 5.0


def test_field_change_reruns(at):
    at.sidebar.button(key="b_run").click().run()
    at.sidebar.number_input(key="wid_b_nm").set_value(0.5).run()
    assert at.session_state["run_params"]["b_app_T"] == 0.5


def test_rate_bump_buttons_edit_and_rerun(at):
    at.sidebar.button(key="b_rp100").click().run()
    assert at.session_state["set_rates_text"] == "300"
    assert [round(float(r[0]), 3) for r in at.session_state["me_results"]] == [300.0]
    at.sidebar.button(key="b_rm100").click().run()
    assert at.session_state["set_rates_text"] == "200"


def test_atoms_from_d_button(at):
    from webapp import runner
    at.sidebar.button(key="b_atoms_d").click().run()
    assert at.session_state["wid_atoms"] == runner.atoms_from_d(
        {**ctx.DEFAULTS, "d_nm": at.session_state["wid_d_nm"]})


def test_sample_load_imports_settings_and_syncs_rate(at):
    at = _sample(at, "500 K/ns  (25 seeds)")
    s = at.session_state["session"]
    assert s is not None and len(s.seeds) == 25
    assert at.session_state["set_rates_text"] == "500"
    # the VAMPIRE run's own conditions were copied into the form
    assert at.session_state["wid_d_nm"] == s.cfg.d_nm
    assert at.session_state["wid_b_nm"] == pytest.approx(s.cfg.b_app_T)
    assert "25 seeds, 500 K/ns" in at.session_state["vampire_info"]
    # a matching ME run was performed automatically, so the comparison is valid
    assert at.session_state["run_params"]["d_nm"] == s.cfg.d_nm


def test_clear_removes_vampire_data(at):
    at = _sample(at, "200 K/ns  (25 seeds)")
    at.sidebar.button(key="b_clear").click().run()
    assert at.session_state["session"] is None
    assert at.session_state["vampire_info"] == ""


def test_load_without_anything_selected(at):
    at.sidebar.selectbox(key="wid_sample").set_value("(none - upload a run)").run()
    at.sidebar.button(key="b_load").click().run()
    assert "Pick a bundled example" in at.session_state["notice"]


def test_no_psw_tab(at):
    """The Psw / m-ms Test tab is deliberately not part of the web app."""
    at = _sample(at, "500 K/ns  (25 seeds)")
    texts = " ".join([m.body for m in at.markdown if isinstance(m.body, str)]
                     + [c.value for c in at.caption] + [b.label for b in at.button])
    assert "Psw" not in texts and "m/ms Test" not in texts
    assert not at.get("table"), "the web app has no comparison table widget"


# ------------------------------------------------- plot options / seed selection ----
def _vamp_label(at) -> str:
    """Legend text of the VAMPIRE mean line in the current figure."""
    return next(l.get_label() for l in at.session_state["fig_obj"].axes[0].get_lines()
                if l.get_label().startswith("VAMPIRE"))


def test_new_control_defaults_match_the_desktop(at_noboot):
    """cb_traces_all / cb_sem / cb_auto start as on the desktop; the web target is 25."""
    ss = at_noboot.session_state
    assert ss["wid_traces_all"] is False and ss["wid_sem_band"] is True
    assert ss["wid_seed_auto"] is True and ss["wid_seed_target"] == 25


def test_sem_band_checkbox_adds_and_removes_the_band(at):
    assert len(at.session_state["fig_obj"].axes[0].collections) == 1   # the ±2 s.e.m. band
    at.sidebar.checkbox(key="wid_sem_band").set_value(False).run()
    assert len(at.session_state["fig_obj"].axes[0].collections) == 0
    assert _vamp_label(at).startswith("VAMPIRE")                       # mean line stays


def test_traces_checkbox_draws_one_line_per_seed(at):
    ax = at.session_state["fig_obj"].axes[0]
    before, n_seeds = len(ax.get_lines()), len(at.session_state["session"].seeds)
    at.sidebar.checkbox(key="wid_traces_all").set_value(True).run()
    assert len(at.session_state["fig_obj"].axes[0].get_lines()) == before + n_seeds


def test_auto_seed_target_reduces_and_says_so(at):
    """A smaller target re-runs the fixed-RNG selection; 10 of 25 is not faithful, so the
    count escalates to 15 (same rule and numbers as the desktop)."""
    from webapp import runner
    at = _sample(at, "500 K/ns  (25 seeds)")
    at.sidebar.number_input(key="wid_seed_target").set_value(10).run()
    s = at.session_state["session"]
    assert runner.vampire_stats(s).n == 25                             # every valid seed
    assert runner.vampire_stats(s, {**ctx.DEFAULTS, "seed_target": 10}).n == 15
    assert "n=15 selected of 25 valid seeds" in _vamp_label(at)
    assert "15 of 25 seeds used" in " ".join(m.body for m in at.markdown
                                             if isinstance(m.body, str))


def test_auto_seed_selection_off_uses_every_valid_seed(at):
    from webapp import runner
    at = _sample(at, "500 K/ns  (25 seeds)")
    at.sidebar.number_input(key="wid_seed_target").set_value(10).run()
    at.sidebar.checkbox(key="wid_seed_auto").set_value(False).run()
    s = at.session_state["session"]
    assert runner.vampire_stats(s, {**ctx.DEFAULTS, "seed_auto": False}).n == 25
    assert "n=25 seeds" in _vamp_label(at)


def test_seed_qc_reported_on_load(at):
    """The sidebar caption names the valid pool and the outliers, without a table."""
    at = _sample(at, "200 K/ns  (25 seeds)")
    info = at.session_state["vampire_info"]
    assert "Seed QC: 25 valid of 25" in info and "1 outlier kept" in info
    assert not at.get("table"), "the web app stays table-free"
