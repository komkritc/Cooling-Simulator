"""Sidebar: the SimpleWindow parameter panel, control for control.

Qt -> Streamlit mapping (see G_web_gui_wireframe.md for the full table):
  QLineEdit ed_rates      -> st.text_input          + the two +/-100 K/ns buttons
  QDoubleSpinBox sp_d     -> st.number_input (auto re-run)
  QDoubleSpinBox sp_b     -> st.number_input (auto re-run)
  QCheckBox cb_adv        -> st.expander("Show more parameters")
  QComboBox cb_damp       -> st.selectbox
  QCheckBox cb_sg + sp_sgw/sp_sgp -> st.checkbox + two number_inputs (window in K)
  QLineEdit ed_vpath      -> sample selectbox + ZIP / file upload
Every keyed widget gets its default from context.DEFAULTS, seeded into session_state
before the widget is created (no value= argument), exactly like the desktop startup.
"""
from __future__ import annotations

import streamlit as st

from webapp import context as ctx
from webapp import actions

# session_state key -> default, for every widget in the sidebar
WIDGET_DEFAULTS = {
    "set_rates_text": ctx.DEFAULTS["rates_text"],
    "wid_d_nm": ctx.DEFAULTS["d_nm"],
    "wid_t0": ctx.DEFAULTS["t0"],
    "wid_t1": ctx.DEFAULTS["t1"],
    "wid_b_nm": ctx.DEFAULTS["b_T"],
    "wid_damp": ctx.DEFAULTS["damp"],
    "wid_atoms": ctx.DEFAULTS["atoms"],
    "wid_a": ctx.DEFAULTS["a_A"],
    "wid_c": ctx.DEFAULTS["c_A"],
    "wid_mu": ctx.DEFAULTS["mu_mub"],
    "wid_gam": ctx.DEFAULTS["gamma_rel"],
    "wid_dT": ctx.DEFAULTS["dT"],
    "wid_p0": ctx.DEFAULTS["p0"],
    "wid_damp_use": ["λ = α (validated)", "λ = α/(1+α²)"][ctx.DEFAULTS["damp_use"]],
    "wid_dark": ctx.DEFAULTS["dark"],
    "wid_grid": ctx.DEFAULTS["grid"],
    "wid_params_on": ctx.DEFAULTS["params_on"],
    "wid_invert_x": ctx.DEFAULTS["invert_x"],
    "wid_sg_on": ctx.DEFAULTS["sg_on"],
    "wid_sg_win": ctx.DEFAULTS["sg_win"],
    "wid_sg_poly": ctx.DEFAULTS["sg_poly"],
    "wid_import_v": ctx.DEFAULTS["import_vampire"],
    "wid_sample": "(none - upload a run)",
    "wid_up_mode": ".zip of the run folder",
}
DAMP_ITEMS = ["λ = α (validated)", "λ = α/(1+α²)"]


def ensure_seeded() -> None:
    for k, v in WIDGET_DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = v


def collect() -> dict:
    """Current settings read back out of session_state (used by callbacks)."""
    g = st.session_state
    s = {}
    for k, key in [("rates_text", "set_rates_text"), ("d_nm", "wid_d_nm"),
                   ("t0", "wid_t0"), ("t1", "wid_t1"), ("b_T", "wid_b_nm"),
                   ("damp", "wid_damp"), ("atoms", "wid_atoms"), ("a_A", "wid_a"),
                   ("c_A", "wid_c"), ("mu_mub", "wid_mu"), ("gamma_rel", "wid_gam"),
                   ("dT", "wid_dT"), ("p0", "wid_p0"), ("sg_win", "wid_sg_win"),
                   ("sg_poly", "wid_sg_poly"), ("grid", "wid_grid"),
                   ("params_on", "wid_params_on"), ("dark", "wid_dark"),
                   ("invert_x", "wid_invert_x"), ("sg_on", "wid_sg_on"),
                   ("import_vampire", "wid_import_v")]:
        s[k] = g.get(key, ctx.DEFAULTS[k])
    s["damp_use"] = DAMP_ITEMS.index(g.get("wid_damp_use", DAMP_ITEMS[0]))
    return s


def render(pal: dict) -> dict:
    """Draws the sidebar and returns the settings dict for this run."""
    ensure_seeded()

    with st.sidebar:
        st.markdown(f"<div style='color:{pal['BLUE']};letter-spacing:.10em;"
                    f"font-size:11px;font-weight:700'>PARAMETERS</div>",
                    unsafe_allow_html=True)

        # cooling rate(s) + the +/-100 buttons: one aligned row, label style like the
        # Grain diameter / Applied field boxes
        rc = st.columns([3.2, 1, 1], vertical_alignment="bottom")
        rates_text = rc[0].text_input("Cooling rate(s) K/ns", key="set_rates_text",
                         help="one or several rates, comma separated (e.g. 100, 500, 1000)")
        rc[1].button("−100", key="b_rm100", on_click=actions.on_rate_bump,
                     args=(-100.0,), use_container_width=True,
                     help="-100 K/ns on every rate in the box (minimum 1), then re-run")
        rc[2].button("+100", key="b_rp100", on_click=actions.on_rate_bump,
                     args=(100.0,), use_container_width=True,
                     help="+100 K/ns on every rate in the box (minimum 1), then re-run")

        # grain diameter: exact box, re-runs the ME (desktop debounce)
        st.number_input("Grain diameter", 1.0, 10.0, step=0.1, format="%.2f",
                        key="wid_d_nm", on_change=actions.on_d_change, args=("wid_d_nm",),
                        help="nm; every change re-runs the ME, like the desktop app")

        t0 = st.number_input("Start temperature", 1.0, 2000.0, step=50.0, key="wid_t0",
                             format="%.0f", help="K")
        t1 = st.number_input("End temperature", 1.0, 2000.0, step=50.0, key="wid_t1",
                             format="%.0f", help="K - must be below the start temperature")

        st.number_input("Applied field B", 0.0, 50.0, step=0.1, format="%.5f",
                        key="wid_b_nm", on_change=actions.on_b_change, args=("wid_b_nm",),
                        help="tesla; the validated FePt study uses B = 1.00531 T")

        damp = st.number_input("Damping λ", 0.0001, 1.0, step=0.01, format="%.4f",
                               key="wid_damp")

        with st.expander("Show more parameters", expanded=False):
            ac = st.columns([3, 1])
            atoms = ac[0].number_input("Atoms in grain", 1, 10 ** 9, step=1,
                                       key="wid_atoms")
            ac[1].button("from D", key="b_atoms_d", on_click=actions.on_atoms_from_d,
                         use_container_width=True,
                         help="set the atom count from a sphere of the chosen diameter")
            a_A = st.number_input("Cell a", 0.5, 20.0, step=0.01, format="%.3f", key="wid_a",
                                  help="Å")
            c_A = st.number_input("Cell c", 0.5, 20.0, step=0.01, format="%.3f", key="wid_c",
                                  help="Å")
            mu = st.number_input("Atomic moment", 0.01, 20.0, step=0.1, format="%.3f",
                                 key="wid_mu", help="μB")
            gam = st.number_input("γ (relative)", 0.01, 10.0, step=0.1, format="%.3f",
                                  key="wid_gam")
            dT = st.number_input("T step", 0.01, 20.0, step=0.5, format="%.2f", key="wid_dT",
                                 help="K - temperature grid spacing")
            p0 = st.number_input("Initial P₀", 0.0, 1.0, step=0.05, format="%.3f", key="wid_p0")
            damp_use = st.selectbox("Damping use", DAMP_ITEMS, key="wid_damp_use",
                                    help="λ = α is the validated convention; "
                                         "λ = α/(1+α²) converts the LL damping to Gilbert")

        st.divider()
        st.button("Run ME", type="primary", key="b_run", use_container_width=True,
                  on_click=actions.run_me,
                  help="computes the master-equation cooling curves for every rate in the "
                       "box (the desktop Run ME button)")

        st.divider()
        st.markdown(f"<div style='color:{pal['BLUE']};letter-spacing:.10em;"
                    f"font-size:11px;font-weight:700'>PLOT OPTIONS</div>",
                    unsafe_allow_html=True)
        pc = st.columns(2)
        dark = pc[0].checkbox("Dark theme", key="wid_dark")
        grid = pc[1].checkbox("Show grid", key="wid_grid")
        params_on = st.checkbox("Show parameters on plot", key="wid_params_on",
                                help="prints the ME / VAMPIRE parameters under the plot "
                                     "(also in the saved PNG)")
        invert_x = st.checkbox("Invert x-axis (high T on left)", key="wid_invert_x")
        sg_c = st.columns([1.6, 1, 1])
        sg_on = sg_c[0].checkbox("Smooth (SG)", key="wid_sg_on",
                                 help="Savitzky-Golay smoothing of the plotted curves only "
                                      "(CSV export stays raw)")
        sg_win = sg_c[1].number_input("window (K)", 1.0, 200.0, step=5.0, format="%.0f",
                                      key="wid_sg_win", label_visibility="collapsed",
                                      help="smoothing window width in K")
        sg_poly = sg_c[2].number_input("order", 1, 7, step=1, key="wid_sg_poly",
                                       label_visibility="collapsed",
                                       help="Savitzky-Golay polynomial order")

        st.divider()
        st.markdown(f"<div style='color:{pal['BLUE']};letter-spacing:.10em;"
                    f"font-size:11px;font-weight:700'>VAMPIRE DATA (optional)</div>",
                    unsafe_allow_html=True)
        samples = ctx.sample_run_dirs()
        names = ["(none - upload a run)"] + [ctx.sample_label(d) for d in samples]
        sample = st.selectbox("example run bundled with the app", names, key="wid_sample",
                              on_change=actions.on_sample_change,
                              help="these are aggregated VAMPIRE output files, not raw "
                                   "simulation folders; picking one loads it immediately")
        st.caption("browsers cannot pick a folder: zip the run folder, or select its "
                   "*_input.json / .mat / output_seedN.dat files")
        up_mode = st.radio("upload", [".zip of the run folder", "individual files"],
                           key="wid_up_mode")
        if up_mode == ".zip of the run folder":
            st.file_uploader("run folder (.zip)", type="zip", key="up_zip")
        else:
            st.file_uploader("run files", type=None, accept_multiple_files=True,
                             key="up_files")
        lc = st.columns(2)
        lc[0].button("Load selected / uploaded", key="b_load", use_container_width=True,
                     on_click=actions.on_load)
        lc[1].button("Remove", key="b_clear", use_container_width=True,
                     on_click=actions.clear_run)
        import_v = st.checkbox("Import VAMPIRE settings", key="wid_import_v",
                               help="fill diameter, temperatures, field, damping, atoms, "
                                    "cell, moment and γ from the loaded run (the ME rate "
                                    "stays as typed)")
        vinfo = st.session_state.get("vampire_info", "")
        if vinfo:
            st.caption(vinfo)

    return _finish(rates_text, t0, t1, damp, atoms, a_A, c_A, mu, gam, dT, p0, damp_use,
                   dark, grid, params_on, invert_x, sg_on, sg_win, sg_poly, sample,
                   up_mode, import_v)


def _finish(rates_text, t0, t1, damp, atoms, a_A, c_A, mu, gam, dT, p0, damp_use, dark,
            grid, params_on, invert_x, sg_on, sg_win, sg_poly, sample, up_mode, import_v):
    """Assembles the settings dict from the widget return values."""
    s = collect()
    s.update(rates_text=rates_text, t0=float(t0), t1=float(t1), damp=float(damp),
             atoms=int(atoms), a_A=float(a_A), c_A=float(c_A), mu_mub=float(mu),
             gamma_rel=float(gam), dT=float(dT), p0=float(p0),
             damp_use=DAMP_ITEMS.index(damp_use), dark=bool(dark), grid=bool(grid),
             params_on=bool(params_on), invert_x=bool(invert_x), sg_on=bool(sg_on),
             sg_win=float(sg_win), sg_poly=int(sg_poly), import_vampire=bool(import_v))
    st.session_state["ui"] = s
    return s
