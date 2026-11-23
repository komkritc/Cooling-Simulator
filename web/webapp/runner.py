"""Run engine: builds MEConfig from UI settings and calls the frozen solver.

Everything numeric is delegated to studio.core (MESolver / LutMaterial /
mapping_engine).  This module only assembles parameters, mirroring
SimpleWindow._config / run_me / _vampire_final / _mismatches so the web app and
the desktop app produce identical numbers and identical messages.
"""
from __future__ import annotations

import math
import os

import numpy as np

from studio.core.mapping_engine import me_inputs_for_solver
from studio.core.me_solver import MESolver
from studio.core.lut_material import LutMaterial, find_lut
from studio.core.types import MEConfig

from . import context as ctx


# ------------------------------------------------------------------ model ----
_MODEL: LutMaterial | None = None


def get_model() -> LutMaterial:
    """Load the LUT surrogate once per process (same file as the desktop app)."""
    global _MODEL
    if _MODEL is None:
        path = find_lut()
        if path is None:
            raise FileNotFoundError(
                "material lookup table (lut_current_rf_1-10nm_dD0p1.csv) not found; "
                "set ME_LUT_FILE or keep it in ../data")
        _MODEL = LutMaterial(path)
        _MODEL.load()
    return _MODEL


# --------------------------------------------------------------- settings ----
def build_config(s: dict, rate: float) -> MEConfig:
    """SimpleWindow._config(): UI units -> MEConfig."""
    if s["t0"] <= s["t1"]:
        raise ValueError("Start temperature must be above the end temperature")
    return MEConfig(
        d_nm=s["d_nm"], n_atoms=int(s["atoms"]),
        cell_a_m=s["a_A"] * 1e-10, cell_c_m=s["c_A"] * 1e-10,
        mu_s_mub=s["mu_mub"], gamma_rel=s["gamma_rel"],
        b_app_T=s["b_T"], damping_value=s["damp"],
        damping_interpretation="identity" if s["damp_use"] == 0 else "ll_to_gilbert",
        t_start_K=s["t0"], t_end_K=s["t1"],
        rate_K_per_ns=rate, dT_grid_K=s["dT"], p0=s["p0"])


def run_params(s: dict) -> dict:
    """The parameter block attached to a run (used by the mismatch card and .py export)."""
    c0 = build_config(s, 0.0)
    return dict(d_nm=c0.d_nm, t_start_K=c0.t_start_K, t_end_K=c0.t_end_K,
                b_app_T=c0.b_app_T, damping_value=c0.damping_value,
                damping_interpretation=c0.damping_interpretation,
                n_atoms=c0.n_atoms, cell_a_m=c0.cell_a_m, cell_c_m=c0.cell_c_m,
                mu_s_mub=c0.mu_s_mub, gamma_rel=c0.gamma_rel,
                dT_grid_K=c0.dT_grid_K, p0=c0.p0)


def atoms_from_d(s: dict) -> int:
    """SimpleWindow._atoms_from_d(): sphere of diameter D / unit-cell volume."""
    v_cell = (s["a_A"] * 1e-10) ** 2 * (s["c_A"] * 1e-10)
    v = math.pi / 6 * (s["d_nm"] * 1e-9) ** 3
    return max(1, int(round(v / v_cell)))


# -------------------------------------------------------------------- run ----
def run_me(s: dict, rates: list[float]) -> list[tuple]:
    """[(rate, T, m, P, ms, Tc)] — identical arithmetic to the desktop run_me job()."""
    ml = get_model()
    out = []
    for rate in rates:
        cfg = build_config(s, rate)
        solver = MESolver(ml, me_inputs_for_solver(cfg))
        solver.configure(cfg)
        T, m, P, ms, cl, ct, Tc, Gam = solver.predict(
            cfg.rate_K_per_ns, cfg.t_start_K, cfg.t_end_K, cfg.dT_grid_K)
        out.append((cfg.rate_K_per_ns, T, m, P, ms, Tc))
    return out


def compare_vampire(session, s: dict, rate: float):
    """Full ME-vs-VAMPIRE comparison for one rate (used by the record export)."""
    from studio.core.session import ComparisonResult
    if session is None:
        return None
    session.apply_settings(d_nm=s["d_nm"], rate_K_per_ns=rate)
    if not session.seeds:
        session.load_seeds()
    return session.run_comparison()


# ---------------------------------------------------------------- VAMPIRE ----
# Representative seed selection, mirroring SimpleWindow._qc_rate/_active_seeds:
# technical validation always runs (a corrupt seed never enters the analysis), and
# Auto Seed Selection reduces the valid pool to a subset that reproduces it.
_QC: dict[str, tuple[tuple, object]] = {}        # run_dir -> (folder stamp, RateQC)
_STATS: dict[tuple, object] = {}                 # (run_dir, seed ids) -> compute_stats()


def _folder_stamp(run_dir: str) -> tuple:
    """(seed folder, DONE mtime) for every seed: the identity of the run's contents."""
    try:
        names = sorted(n for n in os.listdir(run_dir) if n.startswith("seed_"))
    except OSError:
        return ()
    out = []
    for n in names:
        done = os.path.join(run_dir, n, "DONE")
        try:
            out.append((n, os.path.getmtime(done)))
        except OSError:
            out.append((n, None))
    return tuple(out)


def qc_for(session, target: int):
    """seed_qc.RateQC for the loaded run, or None when no rate/seed folder is usable.

    The web app loads a single rate folder rather than a dataset, so this calls
    scan_rate/select_rate directly - the same functions, fixed RNG seed and tolerance
    logic the desktop scan runs, so the same folder and target give the same seeds.
    The scan (and its curves) are cached per folder contents; changing the target only
    re-runs the selection, never the disk read.
    """
    from studio.core import seed_qc

    run_dir = session.run_dir
    rate = session.rate_deck or seed_qc.rate_of_dir(os.path.basename(run_dir.rstrip("/\\")))
    if not rate:
        return None
    stamp = _folder_stamp(run_dir)
    hit = _QC.get(run_dir)
    rq = hit[1] if hit and hit[0] == stamp else None
    if rq is None:
        try:
            rq = seed_qc.scan_rate(rate, run_dir)
        except (FileNotFoundError, ValueError, IndexError):
            return None
        if len(_QC) > 8:
            _QC.clear()
        _QC[run_dir] = (stamp, rq)
    target = max(1, int(target))
    if rq.target != target:
        seed_qc.select_rate(rq, target)
    return rq


def active_seeds(session, s: dict):
    """Seeds the analysis uses: every valid one, or the representative subset when Auto is on."""
    if session is None or not getattr(session, "seeds", None):
        return []
    if not s.get("seed_auto", ctx.DEFAULTS["seed_auto"]):
        return list(session.seeds)
    rq = qc_for(session, s.get("seed_target", ctx.DEFAULTS["seed_target"]))
    if rq is None or not rq.selected:
        return list(session.seeds)
    chosen = set(rq.selected)
    subset = [x for x in session.seeds if x.seed in chosen]
    return subset or list(session.seeds)


def vampire_stats(session, s: dict | None = None):
    """compute_stats() over the active seeds; without `s`, over every seed loaded.

    The `s`-less form is the un-reduced ensemble, used for the grey trajectory overlay.
    """
    seeds = active_seeds(session, s) if s is not None else (
        list(session.seeds) if session is not None and getattr(session, "seeds", None) else [])
    if not seeds:
        return None
    key = (session.run_dir, tuple(x.seed for x in seeds))
    stt = _STATS.get(key)
    if stt is None:
        from studio.core.statistics import compute_stats
        if len(_STATS) > 16:
            _STATS.clear()
        stt = compute_stats(seeds)
        _STATS[key] = stt
    return stt


def vampire_final(vs, T_end):
    """SimpleWindow._vampire_final(): -> (ratio, median_mz, ms_vampire, reason)."""
    i = int(np.argmin(np.abs(vs.T - T_end)))
    if abs(vs.T[i] - T_end) > 0.5:
        return None, None, None, f"VAMPIRE has no row at {T_end:g} K (nearest {vs.T[i]:g} K)"
    mz = float(np.median(vs.mz_per_seed[:, i]))
    msv = float(np.median(vs.mlen[:, i]))
    if msv <= 0:
        return None, None, None, "VAMPIRE magnetisation length is zero"
    return mz / msv, mz, msv, ""


def mismatches(session, rate: float, run_params: dict | None) -> list[str]:
    """Why the displayed ME run at `rate` is NOT directly comparable to the VAMPIRE run."""
    if session is None or not getattr(session, "seeds", None):
        return ["no VAMPIRE data loaded"]
    out: list[str] = []
    vr = session.rate_deck
    if not vr or abs(vr - rate) > 1e-6 * max(1.0, rate):
        out.append(f"cooling rate (ME {rate:g} vs VAMPIRE {vr:g} K/ns)" if vr
                   else "VAMPIRE rate unknown")
    c, p = session.cfg, run_params
    if c is None:
        out.append("VAMPIRE parameters could not be read")
        return out
    if p is None:
        out.append("ME parameters unknown")
        return out

    def num(label, mv, vv, unit="", tol=1e-6):
        if abs(mv - vv) > tol * max(abs(vv), 1e-30):
            out.append(f"{label} (ME {mv:g} vs VAMPIRE {vv:g}{unit})")

    num("grain diameter", p["d_nm"], c.d_nm, " nm")
    num("start T", p["t_start_K"], c.t_start_K, " K")
    num("end T", p["t_end_K"], c.t_end_K, " K")
    num("field B", p["b_app_T"], c.b_app_T, " T", 1e-4)
    num("damping", p["damping_value"], c.damping_value)
    if p["damping_interpretation"] != c.damping_interpretation:
        out.append("damping interpretation")
    num("atoms", p["n_atoms"], c.n_atoms)
    num("cell a", p["cell_a_m"], c.cell_a_m)
    num("cell c", p["cell_c_m"], c.cell_c_m)
    num("atomic moment", p["mu_s_mub"], c.mu_s_mub)
    num("\u03b3", p["gamma_rel"], c.gamma_rel)
    return out


# ------------------------------------------------------- smoothing (plot only)
def smooth(s: dict, T, y):
    """SimpleWindow._smooth(): Savitzky-Golay on the plotted curve only."""
    if not s["sg_on"]:
        return y
    from scipy.signal import savgol_filter
    T = np.asarray(T, float)
    y = np.asarray(y, float)
    dT = float(np.median(np.abs(np.diff(T)))) if len(T) > 1 else 0.0
    if dT <= 0:
        return y
    poly = int(s["sg_poly"])
    w = int(round(s["sg_win"] / dT))
    w += (w % 2 == 0)
    w = max(w, poly + 2 + ((poly + 2) % 2 == 0))
    if w > len(y):
        w = len(y) - (len(y) % 2 == 0)
    if w <= poly:
        return y
    return savgol_filter(y, w, poly, mode="interp")
