"""Callbacks: everything that changes state or runs physics.

Streamlit runs on_click / on_change callbacks BEFORE the script body, which is the only
legal place to write another widget's session_state key - this is the web equivalent of
the desktop's blockSignals + valueChanged wiring.  Nothing here does physics: it calls
webapp.runner, which calls the frozen studio.core solver.
"""
from __future__ import annotations

import os
import tempfile

import streamlit as st

from webapp import context as c
from webapp import runner, sidebar, uploads


# --------------------------------------------------------------- helpers ----
def _set_pair(slider_key: str, number_key: str, value: float) -> None:
    st.session_state[slider_key] = value
    st.session_state[number_key] = value


def notice(msg: str) -> None:
    st.session_state["notice"] = msg


# ------------------------------------------------------------------ run ----
def run_me(s: dict | None = None) -> None:
    """SimpleWindow.run_me(): validate, run every rate, keep the parameter block."""
    s = s or sidebar.collect()
    rates = c.rates_from_text(s["rates_text"])
    if not rates:
        notice(c.RATE_MSG)
        return
    try:
        params = runner.run_params(s)          # raises if t0 <= t1
    except ValueError as e:
        notice(str(e))
        return
    try:
        st.session_state["me_results"] = runner.run_me(s, rates)
    except Exception as e:                     # solver / LUT failure
        notice(f"Run failed: {e}")
        return
    st.session_state["run_params"] = params
    notice("")


def on_rate_bump(delta: float) -> None:
    """SimpleWindow._bump_rates(): +/-100 K/ns on every rate, then re-run."""
    cur = st.session_state.get("set_rates_text", c.DEFAULTS["rates_text"])
    vals = c.rates_from_text(cur)
    if not vals:
        notice(c.RATE_MSG)
        return
    new = [max(1.0, r + delta) for r in vals]
    text = ", ".join(f"{r:g}" for r in new)
    st.session_state["set_rates_text"] = text
    s = sidebar.collect()
    s["rates_text"] = text
    notice("")
    run_me(s)


def on_d_change(src: str) -> None:
    """Grain diameter changed (either member of the pair): sync + re-run ME."""
    val = float(st.session_state[src])
    _set_pair("wid_d_slider", "wid_d_nm", val)
    run_me()


def on_b_change(src: str) -> None:
    """Applied field B changed (either member of the pair): sync + re-run ME."""
    val = float(st.session_state[src])
    _set_pair("wid_b_slider", "wid_b_nm", val)
    run_me()


def on_atoms_from_d() -> None:
    st.session_state["wid_atoms"] = runner.atoms_from_d(sidebar.collect())


# -------------------------------------------------------------- VAMPIRE ----
def apply_vampire_settings(cfg) -> None:
    """SimpleWindow._apply_vampire_settings(): copy everything except the ME rate."""
    _set_pair("wid_d_slider", "wid_d_nm", cfg.d_nm)
    st.session_state["wid_t0"] = float(cfg.t_start_K)
    st.session_state["wid_t1"] = float(cfg.t_end_K)
    _set_pair("wid_b_slider", "wid_b_nm", float(cfg.b_app_T))
    st.session_state["wid_damp"] = float(cfg.damping_value)
    st.session_state["wid_atoms"] = int(cfg.n_atoms)
    st.session_state["wid_a"] = cfg.cell_a_m * 1e10
    st.session_state["wid_c"] = cfg.cell_c_m * 1e10
    st.session_state["wid_mu"] = float(cfg.mu_s_mub)
    st.session_state["wid_gam"] = float(cfg.gamma_rel)
    st.session_state["wid_damp_use"] = (sidebar.DAMP_ITEMS[0]
                                        if cfg.damping_interpretation == "identity"
                                        else sidebar.DAMP_ITEMS[1])


def load_run(path: str) -> None:
    """SimpleWindow.open_path(): resolve, load seeds, import settings, sync the rate."""
    from studio.core.session import AnalysisSession

    def resolve(d):
        # a single seed folder (seed_N with DONE) was picked: use its parent rate folder
        if (os.path.basename(os.path.normpath(d)).startswith("seed_")
                and os.path.isfile(os.path.join(d, "DONE"))):
            return os.path.dirname(os.path.abspath(d))
        try:
            if not any(n.startswith("seed_") for n in os.listdir(d)):
                for root, dirs, _ in os.walk(d):
                    if any(n.startswith("rate_") for n in dirs):
                        return os.path.join(root, sorted(n for n in dirs
                                                         if n.startswith("rate_"))[0])
        except OSError:
            pass
        return d

    if not path or not os.path.isdir(path):
        notice(f"Folder not found: {path}")
        return
    try:
        s = AnalysisSession(resolve(path), snap_diameter=False)   # use the deck's real diameter (no 4.00 nm snap)
        s.load_seeds()
    except Exception as e:
        st.session_state["session"] = None
        notice(f"Could not load VAMPIRE run: {e}")
        return

    st.session_state["session"] = s
    st.session_state["vpath"] = s.run_dir
    rate_txt = f"{s.rate_deck:g} K/ns" if s.rate_deck else "rate unknown"
    note = ""
    if s.cfg is None:
        note = f"  ME parameters could not be read from it: {s.mapping_error}"
    elif st.session_state.get("wid_import_v", True):
        apply_vampire_settings(s.cfg)
    synced = False
    if s.rate_deck:
        st.session_state["set_rates_text"] = f"{s.rate_deck:g}"
        synced = True
    if s.cfg is not None:
        note = (f"\nGrain D = {s.rf_d:g} nm from the deck (LUT interpolated), "
                f"N = {s.cfg.n_atoms} atoms") + note
    st.session_state["vampire_info"] = (
        f"{s.run_dir}\n{len(s.seeds)} seeds, {rate_txt}. "
        + ("ME rate set to match (you can change it freely)." if synced
           else "ME rate is set separately above.") + note)
    notice("")
    if synced or not st.session_state.get("me_results"):
        run_me()


def on_load() -> None:
    """Loads whatever is chosen: the bundled example, an uploaded zip, or files."""
    pick = st.session_state.get("wid_sample", "")
    samples = c.sample_run_dirs()
    names = ["(none - upload a run)"] + [c.sample_label(d) for d in samples]
    if pick in names and pick != names[0]:
        load_run(samples[names.index(pick) - 1])
        return
    up_zip = st.session_state.get("up_zip")
    if up_zip is not None:
        d = tempfile.mkdtemp(prefix="mecool_zip_")
        uploads.track(d)
        try:
            load_run(uploads.extract_zip(up_zip, d))
        except Exception as e:
            notice(f"Upload failed: {e}")
        return
    files = st.session_state.get("up_files") or []
    if files:
        d = tempfile.mkdtemp(prefix="mecool_files_")
        uploads.track(d)
        try:
            load_run(uploads.write_files(files, d))
        except Exception as e:
            notice(f"Upload failed: {e}")
        return
    notice("Pick a bundled example run or upload a run folder (.zip).")


def clear_run() -> None:
    """SimpleWindow.clear_vampire()."""
    st.session_state["session"] = None
    st.session_state["vampire_info"] = ""
    st.session_state["vpath"] = ""
    notice("")
