"""Main results area: figure, result line, ratio card, VAMPIRE status, exports."""
from __future__ import annotations

import html

import streamlit as st

from . import runner, plot_simple, exports


def render(pal: dict, s: dict) -> None:
    session = st.session_state.get("session")
    results = st.session_state.get("me_results", [])
    run_params = st.session_state.get("run_params")

    fig, lines = plot_simple.draw(s, results, session, pal)
    st.session_state["fig_obj"] = fig
    st.pyplot(fig, clear_figure=False)
    if lines:
        st.code("\n".join(lines), language=None)

    ratio_card(pal, s, results, session, run_params)

    if session is not None:
        vcard(pal, session, s, results, run_params)
        validation_card(pal, session)

    exports.render(pal, s, results, session, run_params)


# ------------------------------------------------------------------ ratio ----
def ratio_card(pal, s, results, session, run_params) -> None:
    T_end = results[0][1][-1] if results else s["t1"]
    st.markdown(f"#### Final Magnetisation Ratio ({T_end:g} K)")
    me_col, v_col, st_col = st.columns([1, 1, 1.4])
    vs = runner.vampire_stats(session, s)

    with me_col:
        st.markdown(f"<span style='color:{pal['BLUE']}'><b>\u25a0 ME</b></span> "
                    f"<span style='color:{pal['FG_DIM']}'>m/ms</span>",
                    unsafe_allow_html=True)
        if results:
            for r, T, m, P, ms, Tc in results:
                st.markdown(f"{r:g} K/ns &nbsp; **{m[-1] / ms[-1]:.4f}**")
        else:
            st.markdown(f"<span style='color:{pal['FG_DIM']}'>run ME to see values</span>",
                        unsafe_allow_html=True)

    with v_col:
        st.markdown(f"<span style='color:{pal['AMBER']}'><b>\u25a0 VAMPIRE</b></span> "
                    f"<span style='color:{pal['FG_DIM']}'>median m / ms</span>",
                    unsafe_allow_html=True)
        vres = runner.vampire_final(vs, T_end) if vs is not None else None
        if vs is None:
            st.markdown(f"<span style='color:{pal['FG_DIM']}'>no VAMPIRE data loaded</span>",
                        unsafe_allow_html=True)
        elif vres[0] is None:
            st.markdown(f"<span style='color:{pal['FG_DIM']}'>{html.escape(vres[3])}</span>",
                        unsafe_allow_html=True)
        else:
            n_valid = len(session.seeds)
            n_txt = (f"{vs.n} of {n_valid} valid seeds" if vs.n != n_valid
                     else f"{vs.n} seeds")
            st.markdown(f"{session.rate_deck:g} K/ns &nbsp; **{vres[0]:.4f}** "
                        f"<span style='color:{pal['FG_DIM']}'>{n_txt}</span>",
                        unsafe_allow_html=True)

    with st_col:
        if not results or vs is None:
            st.markdown(f"<span style='color:{pal['FG_DIM']}'>Load VAMPIRE data and run ME "
                        f"to compare.</span>", unsafe_allow_html=True)
        elif vres[0] is None:
            st.markdown(f"<span style='color:{pal['AMBER']}'>\u26a0 Cannot compare: "
                        f"{html.escape(vres[3])}</span>", unsafe_allow_html=True)
        else:
            ok = [(r, m[-1] / ms[-1]) for r, T, m, P, ms, Tc in results
                  if not runner.mismatches(session, r, run_params)]
            if ok:
                r, rme = ok[0]
                st.markdown(
                    f"<span style='color:{pal['GREEN']}'>\u2713 Comparable at {r:g} K/ns"
                    f"</span> &nbsp; \u0394R = |{rme:.4f} \u2212 {vres[0]:.4f}| = "
                    f"<b>{abs(rme - vres[0]):.4f}</b>", unsafe_allow_html=True)
            else:
                best = results[0]
                reasons = runner.mismatches(session, best[0], run_params)
                for rr in results[1:]:
                    if abs(rr[0] - session.rate_deck) < abs(best[0] - session.rate_deck):
                        best = rr
                        reasons = runner.mismatches(session, rr[0], run_params)
                st.markdown(
                    f"<b>Not directly comparable</b><br>"
                    f"<span style='color:{pal['FG_DIM']}'>differs: "
                    f"{html.escape('; '.join(reasons))}</span>", unsafe_allow_html=True)


# ------------------------------------------------------------- VAMPIRE info ----
def vcard(pal, session, s, results, run_params) -> None:
    info = session.seed_info()
    rate = f"{session.rate_deck:g} K/ns" if session.rate_deck else "rate unknown"
    used = len(runner.active_seeds(session, s))
    seeds_txt = (f"{info['n_loaded']} seeds" if used == info["n_loaded"]
                 else f"{used} of {info['n_loaded']} seeds used")
    head = (f"**VAMPIRE run:** `{session.run_dir.split('/')[-1]}` \u00b7 {seeds_txt} "
            f"\u00b7 {rate}" + (" \u00b7 rate snapped to the registered model diameter"
                                if session.rf_d_snapped else ""))
    st.markdown(head)
    if session.cfg is None:
        st.error("ME parameters could not be read from the run: "
                 f"{session.mapping_error}")
        return
    bad = runner.mismatches(session, results[0][0], run_params) if results else ["no ME run yet"]
    if bad:
        st.warning("ME run differs from the VAMPIRE conditions: " + "; ".join(bad))
    else:
        st.success("ME run matches the VAMPIRE conditions \u2014 direct comparison valid")


def validation_card(pal, session) -> None:
    try:
        issues = session.validate()
    except Exception as e:                                     # never let audit break the UI
        st.warning(f"validation unavailable: {type(e).__name__}: {e}")
        return
    npass = sum(1 for i in issues if i.severity == "pass")
    nwarn = sum(1 for i in issues if i.severity == "warning")
    crit = [i for i in issues if i.severity == "critical"]
    st.markdown(f"**Validation:** {npass} pass \u00b7 {nwarn} warn \u00b7 "
                f"<span style='color:{pal['RED']}'>{len(crit)} critical</span>",
                unsafe_allow_html=True)
    with st.expander(f"validation rules ({len(issues)})", expanded=False):
        for i in issues:
            mark = {"pass": "\u2713", "warning": "\u26a0", "critical": "\u2717"}[i.severity]
            st.markdown(f"{mark} **{i.rule}** \u2014 {i.message}")
