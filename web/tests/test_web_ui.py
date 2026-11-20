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


def _sample(at, rate: str) -> AppTest:
    sel = next(s for s in at.sidebar.selectbox if s.label.startswith("example run"))
    sel.select(rate).run()
    at.sidebar.button(key="b_load").click().run()
    assert not at.exception, at.exception
    return at


def test_starts_like_the_desktop(at):
    """Every parameter opens at the desktop SimpleWindow default.

    The web app deliberately differs in one way only: Savitzky-Golay smoothing of the
    *plotted* curve starts switched on (the numbers, the CSV export and the solver are
    untouched). The theme starts light, as on the desktop (app.py reads theme=light).
    """
    ss = at.session_state
    for key, want in [("set_rates_text", "500"), ("wid_d_nm", 4.0), ("wid_t0", 800.0),
                      ("wid_t1", 300.0), ("wid_b_nm", 1.00531), ("wid_damp", 0.05),
                      ("wid_atoms", 4602), ("wid_p0", 0.5), ("wid_grid", True),
                      ("wid_params_on", True), ("wid_invert_x", True),
                      ("wid_dark", False), ("wid_sg_on", True),
                      ("wid_sg_win", 15.0), ("wid_sg_poly", 3)]:
        assert ss[key] == want, key
    assert ss["me_results"] == []                       # nothing computed until Run ME


def test_run_me_produces_curves_and_a_figure(at):
    at.sidebar.button(key="b_run").click().run()
    res = at.session_state["me_results"]
    assert [round(float(r[0]), 3) for r in res] == [500.0]
    assert round(float(res[0][2][-1]), 6) == 0.774476   # == desktop/golden m(300 K)
    assert at.session_state["fig_obj"] is not None
    assert at.session_state["notice"] == ""
    assert at.session_state["run_params"]["d_nm"] == 4.0


def test_bad_rate_shows_the_desktop_message(at):
    at.sidebar.text_input(key="set_rates_text").set_value("abc").run()
    at.sidebar.button(key="b_run").click().run()
    assert at.session_state["notice"] == ctx.RATE_MSG


def test_temperature_order_is_checked(at):
    at.sidebar.number_input(key="wid_t0").set_value(200.0).run()
    at.sidebar.button(key="b_run").click().run()
    assert at.session_state["notice"] == ctx.T_MSG


def test_diameter_pair_stays_in_sync_and_reruns(at):
    """Editing the slider moves the exact box and re-runs the ME, like the desktop."""
    at.sidebar.button(key="b_run").click().run()
    before = at.session_state["me_results"][0][2][-1]
    at.sidebar.slider(key="wid_d_slider").set_value(5.0).run()
    assert at.session_state["wid_d_nm"] == 5.0
    after = at.session_state["me_results"][0][2][-1]
    assert float(after) != float(before)
    assert at.session_state["run_params"]["d_nm"] == 5.0


def test_field_pair_stays_in_sync_and_reruns(at):
    at.sidebar.button(key="b_run").click().run()
    at.sidebar.number_input(key="wid_b_nm").set_value(0.5).run()
    assert at.session_state["wid_b_slider"] == 0.5
    assert at.session_state["run_params"]["b_app_T"] == 0.5


def test_rate_bump_buttons_edit_and_rerun(at):
    at.sidebar.button(key="b_rp100").click().run()
    assert at.session_state["set_rates_text"] == "600"
    assert [round(float(r[0]), 3) for r in at.session_state["me_results"]] == [600.0]
    at.sidebar.button(key="b_rm100").click().run()
    assert at.session_state["set_rates_text"] == "500"


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
    at.sidebar.button(key="b_load").click().run()
    assert "Pick a bundled example" in at.session_state["notice"]


def test_no_psw_tab(at):
    """The Psw / m-ms Test tab is deliberately not part of the web app."""
    at = _sample(at, "500 K/ns  (25 seeds)")
    texts = " ".join([m.body for m in at.markdown if isinstance(m.body, str)]
                     + [c.value for c in at.caption] + [b.label for b in at.button])
    assert "Psw" not in texts and "m/ms Test" not in texts
    assert not at.get("table"), "the web app has no comparison table widget"
