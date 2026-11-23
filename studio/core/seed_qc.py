"""VAMPIRE seed QC + representative-seed selection (Qt-free).

Two rules the GUI depends on:

* Technical validation ALWAYS runs.  A seed that fails a technical check never
  enters the analysis, whether or not representative selection is switched on.
* Statistical anomalies are FLAGGED, never discarded.  A flagged seed stays in the
  full valid ensemble (it still counts towards full-ensemble statistics) and stays
  eligible for representative selection; the flag is diagnostic (report + overlay).

Selection is reproducible: even-stride quantile sampling of the final-m_z
distribution with ties broken by a fixed RNG seed (RNG_SEED), so the same dataset
plus the same target count always gives the same seed list.  If the selected
ensemble does not reproduce the full valid ensemble within tolerance the count is
escalated and every attempt is recorded (RateQC.attempts).

Definitions match studio/core/statistics.py: signed m_z = |m|*cos(theta_z),
cooling rows T < 799.5 K, final window 300-310 K, up > +0.7, reversed < -0.7.
The technical limits come from the validated NAM pipeline
(NAM_FePt_Cooling/vampire_output/select_representative_seeds.py); the one deliberate
change is that its absolute m_z range is applied as |m_z| <= MZ_ABS_MAX, because the
prototype read the unsigned magnetisation-length column while this app uses the
signed m_z, where a reversed grain is legitimately negative.
"""
from __future__ import annotations

import csv
import glob
import os
import re
from dataclasses import dataclass, field

import numpy as np

RNG_SEED = 20260425              # fixed: same dataset + target -> same selection
COOL_MAX_K = 799.5              # same equilibration cut as vampire_output_reader
FINAL_WINDOW_K = (300.0, 310.0)
UP_THRESH, DOWN_THRESH = 0.7, -0.7

MIN_POINTS = 50                 # usable rows after NaN removal
MAX_NAN_FRACTION = 0.05
MIN_SPAN_K = 300.0
T_PLAUSIBLE_K = (200.0, 2000.0)
MZ_ABS_MAX = 1.155              # prototype's m_z upper bound * 1.1, as an abs bound
MAD_Z_FLAG = 5.0                # dev/MAD above this -> anomalous (flag, keep)

GRID_POINTS = 500               # common resampled T axis per rate (reporting + QC only)
TOL_MEAN = 0.05                 # max |mean_selected - mean_full| on that axis
TOL_SD_REL = 0.25               # max relative SD error
TOL_FIN = 0.10                  # max error of the final-window mean m_z
TOL_COMP = 0.05                 # max change of the up / reversed fractions

QC_DIRNAME = "qc"
REPORTS = ("seed_quality_report.csv", "rejected_seeds.csv", "selected_seeds.csv",
           "ensemble_statistics_full.csv", "ensemble_statistics_selected.csv",
           "seed_selection_summary.csv", "outlier_diagnostic_plot.png")


def rate_of_dir(name: str) -> float | None:
    m = re.fullmatch(r"rate_(\d+(?:\.\d+)?)Kns", name)
    return float(m.group(1)) if m else None


def dataset_dir_of(path: str) -> str:
    """Dataset folder that holds the rate_* dirs, seen from a run dir or a rate dir."""
    p = os.path.abspath(path)
    if rate_of_dir(os.path.basename(p)) is not None:
        return os.path.dirname(p)
    if os.path.isdir(os.path.join(p, "seed_1")) or glob.glob(os.path.join(p, "seed_*")):
        return os.path.dirname(p)
    for _ in range(4):                                  # dataset chosen directly
        if any(rate_of_dir(n) is not None for n in os.listdir(p) if os.path.isdir(os.path.join(p, n))):
            return p
        p = os.path.dirname(p)
    return os.path.dirname(os.path.abspath(path))


def rate_dirs(dataset_dir: str) -> list[tuple[float, str]]:
    """(rate, run_dir) for every rate_* folder holding seeds, rate ascending."""
    out = []
    for name in sorted(os.listdir(dataset_dir)):
        p = os.path.join(dataset_dir, name)
        r = rate_of_dir(name)
        if r is not None and os.path.isdir(p) and glob.glob(os.path.join(p, "seed_*")):
            out.append((r, p))
    return out


# ---------------------------------------------------------------- loading

@dataclass
class Curve:
    seed: int
    dir: str
    T: np.ndarray
    mz: np.ndarray
    reason: str = ""                                  # "" -> technically valid


def _layout_for(run_dir: str):
    """Column layout from the first seed's deck (one deck per rate in a run family)."""
    from .vampire_input_parser import DECK_KEYS, parse_deck
    from .vampire_output_reader import layout_from_deck
    for d in sorted(glob.glob(os.path.join(run_dir, "seed_*")),
                    key=lambda p: int(re.search(r"seed_(\d+)", p).group(1)) if re.search(r"seed_(\d+)", p) else -1):
        if os.path.isfile(os.path.join(d, "input")):
            return layout_from_deck(parse_deck(os.path.join(d, "input"), DECK_KEYS))
    return None


def _col_index(lay, directive: str, offset: int = 0) -> int | None:
    i = lay.index_of(directive)
    return None if i is None else i + offset


def load_curve(run_dir: str, seed_dir: str, lay) -> Curve:
    """One seed's (T, signed m_z) on its raw rows; failure comes back as a reason."""
    seed = int(re.search(r"seed_(\d+)", seed_dir).group(1)) if re.search(r"seed_(\d+)", seed_dir) else -1
    dat = next(iter(sorted(glob.glob(os.path.join(seed_dir, "output_seed*.dat")))), None)
    if dat is None:
        return Curve(seed, seed_dir, np.zeros(0), np.zeros(0), "no output_seed*.dat")
    t_col = _col_index(lay, "output:temperature")
    mdir_col = _col_index(lay, "output:magnetisation", 2)
    mlen_col = _col_index(lay, "output:magnetisation-length")
    if None in (t_col, mdir_col, mlen_col):
        return Curve(seed, seed_dir, np.zeros(0), np.zeros(0), "deck output columns unusable")
    try:
        arr = np.loadtxt(dat, comments="#", usecols=(t_col, mdir_col, mlen_col), dtype=np.float64)
    except Exception as e:
        return Curve(seed, seed_dir, np.zeros(0), np.zeros(0), f"unreadable: {type(e).__name__}")
    if arr.ndim != 2 or arr.shape[0] < MIN_POINTS:
        return Curve(seed, seed_dir, np.zeros(0), np.zeros(0), f"fewer than {MIN_POINTS} rows")
    T, mz = arr[:, 0], arr[:, 2] * arr[:, 1]
    bad = ~np.isfinite(T) | ~np.isfinite(mz)
    if bad.mean() > MAX_NAN_FRACTION:
        return Curve(seed, seed_dir, T, mz, f"NaN/Inf fraction {bad.mean():.2f}")
    T, mz = T[~bad], mz[~bad]
    if T.size < MIN_POINTS:
        return Curve(seed, seed_dir, T, mz, f"fewer than {MIN_POINTS} usable rows")
    if not (T_PLAUSIBLE_K[0] <= T.min() and T.max() <= T_PLAUSIBLE_K[1]):
        return Curve(seed, seed_dir, T, mz, f"T range {T.min():g}..{T.max():g} K implausible")
    if T.max() - T.min() < MIN_SPAN_K:
        return Curve(seed, seed_dir, T, mz, f"T span {T.max() - T.min():g} K < {MIN_SPAN_K:g} K")
    if np.abs(mz).max() > MZ_ABS_MAX:
        return Curve(seed, seed_dir, T, mz, f"|m_z| {np.abs(mz).max():.2f} > {MZ_ABS_MAX:g}")
    cool = T < COOL_MAX_K
    if cool.sum() < MIN_POINTS:
        return Curve(seed, seed_dir, T, mz, f"fewer than {MIN_POINTS} cooling rows")
    o = np.argsort(T[cool])                       # ascending: VAMPIRE writes cooling rows as T falls
    return Curve(seed, seed_dir, T[cool][o], mz[cool][o])


# ---------------------------------------------------------------- per-rate QC

@dataclass
class RateQC:
    rate: float
    run_dir: str
    T: np.ndarray                                     # ascending common grid
    curves: np.ndarray                                # (n_seeds, n_T) on T, NaN = rejected
    seeds: list[int] = field(default_factory=list)    # every DONE seed, id order
    valid: list[int] = field(default_factory=list)    # passed technical checks (incl. flagged)
    flagged: list[int] = field(default_factory=list)  # anomalous but kept
    rejected: list[tuple[int, str]] = field(default_factory=list)
    incomplete: int = 0                               # seed dirs without DONE
    dev: dict[int, float] = field(default_factory=dict)
    z: dict[int, float] = field(default_factory=dict)
    fin: dict[int, float] = field(default_factory=dict)
    mad: float = 0.0
    med_dev: float = 0.0
    target: int = 0
    selected: list[int] = field(default_factory=list)
    escalated: bool = False
    attempts: list[tuple[int, float, float, float, bool]] = field(default_factory=list)
    err: tuple[float, float, float] = (0.0, 0.0, 0.0)  # mean / SD(rel) / final-window error

    # row helpers -------------------------------------------------------
    def row(self, seed: int) -> int:
        return self.seeds.index(seed)

    def grid(self, seed: int) -> np.ndarray:
        return self.curves[self.row(seed)]

    @property
    def full(self) -> np.ndarray:
        return self.curves[[self.row(s) for s in self.valid]]

    @property
    def sel(self) -> np.ndarray:
        return self.curves[[self.row(s) for s in self.selected]]


def scan_rate(rate: float, run_dir: str) -> RateQC:
    """Enumerate DONE seeds, run technical checks, resample, flag MAD anomalies."""
    from .vampire_output_reader import find_seeds, incomplete_seeds
    lay = _layout_for(run_dir)
    if lay is None:
        raise FileNotFoundError(f"no seed deck (input) under {run_dir}")
    dirs = find_seeds(run_dir)
    if not dirs:
        raise FileNotFoundError(f"no DONE seeds under {run_dir}")
    curves = [load_curve(run_dir, d, lay) for d in dirs]
    ok = [c for c in curves if not c.reason]
    if not ok:
        raise ValueError(f"all {len(curves)} seeds failed technical checks in {run_dir}")

    # common axis from the median cooling range of the valid seeds (their own axes differ in length)
    T = np.linspace(float(np.median([c.T.min() for c in ok])),
                    float(np.median([c.T.max() for c in ok])), GRID_POINTS)
    arr = np.full((len(curves), T.size), np.nan)
    qc = RateQC(rate=rate, run_dir=run_dir, T=T, curves=arr,
                seeds=[c.seed for c in curves],
                rejected=[(c.seed, c.reason) for c in curves if c.reason],
                incomplete=len(incomplete_seeds(run_dir)))
    for i, c in enumerate(curves):
        if c.reason:
            continue
        arr[i] = np.interp(T, c.T, c.mz)
        qc.valid.append(c.seed)
        qc.fin[c.seed] = float(c.mz[(c.T >= FINAL_WINDOW_K[0]) & (c.T < FINAL_WINDOW_K[1])].mean()) \
            if ((c.T >= FINAL_WINDOW_K[0]) & (c.T < FINAL_WINDOW_K[1])).any() else float(c.mz[-1])

    med = np.nanmedian(arr[[qc.row(s) for s in qc.valid]], axis=0)
    for s in qc.valid:
        qc.dev[s] = float(np.nanmean(np.abs(qc.grid(s) - med)))
    devs = np.array([qc.dev[s] for s in qc.valid])
    med_dev = float(np.median(devs))
    # robust z of the trajectory distance to the median curve; dev itself is not centred,
    # so the prototype's raw dev/MAD ratio flagged the whole ensemble - centre and scale it.
    mad = 1.4826 * float(np.median(np.abs(devs - med_dev)))
    qc.mad, qc.med_dev = mad, med_dev
    for s, d in qc.dev.items():
        z = (d - med_dev) / mad if mad > 0 else 0.0
        qc.z[s] = z
        if mad > 0 and z > MAD_Z_FLAG:
            qc.flagged.append(s)
    qc.selected = list(qc.valid)                     # default: every valid seed is used
    return qc


# ---------------------------------------------------------------- selection

def _ens_stats(mat: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = mat.shape[0]
    mean = mat.mean(axis=0)
    sd = mat.std(axis=0, ddof=1) if n > 1 else np.zeros_like(mean)
    return mean, sd, sd / np.sqrt(max(n, 1))


def _composition(qc: RateQC, seeds: list[int]) -> tuple[float, float]:
    up = sum(1 for s in seeds if qc.fin[s] > UP_THRESH) / len(seeds)
    dn = sum(1 for s in seeds if qc.fin[s] < DOWN_THRESH) / len(seeds)
    return up, dn


def _errors(qc: RateQC, chosen: list[int]) -> tuple[float, float, float, bool]:
    mf, sf, _ = _ens_stats(qc.full)
    ms, ss, _ = _ens_stats(qc.curves[[qc.row(s) for s in chosen]])
    mean_err = float(np.max(np.abs(ms - mf)))
    sd_err = float(np.max(np.abs(ss - sf)) / max(float(sf.max()), 0.05))
    fin_err = abs(float(np.mean([qc.fin[s] for s in chosen])) - float(np.mean([qc.fin[s] for s in qc.valid])))
    up_f, dn_f = _composition(qc, qc.valid)
    up_s, dn_s = _composition(qc, chosen)
    comp_err = max(abs(up_s - up_f), abs(dn_s - dn_f))
    ok = mean_err <= TOL_MEAN and sd_err <= TOL_SD_REL and fin_err <= TOL_FIN and comp_err <= TOL_COMP
    return mean_err, sd_err, fin_err, ok


def _quantile_pick(order: list[int], n: int, rng: np.random.Generator) -> list[int]:
    """n evenly spaced picks over the final-m_z-sorted pool; collisions filled by the fixed RNG."""
    if n >= len(order):
        return list(order)
    if n <= 1:
        return [order[len(order) // 2]]
    idx = [int(round(k * (len(order) - 1) / (n - 1))) for k in range(n)]
    seen, chosen = set(), []
    for i in idx:
        if i not in seen:
            seen.add(i)
            chosen.append(order[i])
    rest = [order[i] for i in range(len(order)) if i not in seen]
    if len(chosen) < n and rest:
        rng.shuffle(rest)
        chosen.extend(rest[:n - len(chosen)])
    return sorted(chosen)


def select_rate(qc: RateQC, target: int, rng_seed: int = RNG_SEED) -> RateQC:
    """Pick up to `target` representative valid seeds; escalate the count until faithful.

    The pool is every technically valid seed - flagged seeds stay eligible, because
    dropping them would understate the ensemble spread the selection has to reproduce.
    """
    target = max(1, int(target))
    # quantile sampling over the final-m_z distribution reproduces the up / partial / down mix;
    # dev and id break ties deterministically so the fixed RNG only resolves genuine collisions.
    order = sorted(qc.valid, key=lambda s: (qc.fin[s], qc.dev.get(s, 0.0), s))
    qc.attempts = []
    n = min(target, len(order))
    best: tuple[int, list[int], tuple[float, float, float]] | None = None
    while True:
        rng = np.random.default_rng(rng_seed)
        chosen = _quantile_pick(order, n, rng)
        mean_err, sd_err, fin_err, ok = _errors(qc, chosen)
        qc.attempts.append((n, mean_err, sd_err, fin_err, ok))
        if best is None or mean_err + sd_err < best[2][0] + best[2][1]:
            best = (n, chosen, (mean_err, sd_err, fin_err))
        if ok or n >= len(order):
            break
        n = min(len(order), n + max(5, n // 2))
    qc.target, qc.selected = target, sorted(best[1])
    qc.escalated = len(qc.selected) > min(target, len(qc.valid))
    qc.err = best[2]
    return qc


# ---------------------------------------------------------------- dataset

@dataclass
class DatasetQC:
    dataset_dir: str
    rates: list[RateQC] = field(default_factory=list)
    skipped: list[tuple[float, str, str]] = field(default_factory=list)   # (rate, dir, why)
    rng_seed: int = RNG_SEED
    auto: bool = True
    target: int = 50

    def for_rate(self, rate: float | None) -> RateQC | None:
        """The row for `rate` (float noise from folder vs deck names allowed).

        No near-neighbour fallback: when a rate folder had no usable seeds there is
        no selection for it, and borrowing another rate's row would be wrong.
        """
        if not self.rates or rate is None:
            return None
        tol = 1e-6 * max(1.0, abs(float(rate)))
        return next((r for r in self.rates if abs(r.rate - float(rate)) <= tol), None)

    def report_dir(self) -> str:
        return os.path.join(self.dataset_dir, QC_DIRNAME)


def scan_dataset(dataset_dir: str, target: int = 50, auto: bool = True,
                 rng_seed: int = RNG_SEED) -> DatasetQC:
    """Scan every rate_* folder: technical QC always, representative selection when auto."""
    dq = DatasetQC(dataset_dir=os.path.abspath(dataset_dir), rng_seed=rng_seed,
                   auto=bool(auto), target=max(1, int(target)))
    for rate, run_dir in rate_dirs(dq.dataset_dir):
        try:
            rq = scan_rate(rate, run_dir)
        except (FileNotFoundError, ValueError) as e:
            dq.skipped.append((rate, run_dir, str(e)))   # a row is still shown, with the reason
            continue
        if auto:
            select_rate(rq, target, rng_seed)
        dq.rates.append(rq)
    if not dq.rates:
        raise FileNotFoundError(f"no rate_* folder with usable seeds under {dataset_dir}")
    return dq


def reselect(dq: DatasetQC, target: int, auto: bool | None = None) -> DatasetQC:
    """Re-run selection on cached curves (no disk reload) after a target/switch change."""
    dq.target = max(1, int(target))
    if auto is not None:
        dq.auto = bool(auto)
    for rq in dq.rates:
        if dq.auto:
            select_rate(rq, dq.target, dq.rng_seed)
        else:
            rq.selected, rq.escalated, rq.attempts = list(rq.valid), False, []
            rq.err = (0.0, 0.0, 0.0)
    return dq


# ---------------------------------------------------------------- reports

def write_reports(dq: DatasetQC, out_dir: str | None = None) -> dict[str, str]:
    """QC CSVs + the outlier/selection diagnostic PNG.  Inputs are never touched."""
    out = out_dir or dq.report_dir()
    os.makedirs(out, exist_ok=True)
    paths: dict[str, str] = {}

    def w(name: str, header: list[str], rows) -> None:
        p = os.path.join(out, name)
        with open(p, "w", newline="") as f:
            cw = csv.writer(f)
            cw.writerow(header)
            for r in rows:
                cw.writerow(r)
        paths[name] = p

    w("seed_quality_report.csv",
      ["rate_K_per_ns", "seed", "seed_dir", "status", "reason", "n_points", "T_min_K", "T_max_K",
       "final_mz_300_310K", "mean_abs_dev", "dev_over_MAD", "flagged", "selected"],
      [[f"{rq.rate:g}", s, os.path.basename(rq.run_dir),
        "valid", "", int(np.sum(np.isfinite(rq.grid(s)))), float(rq.T[0]), float(rq.T[-1]),
        f"{rq.fin[s]:.4f}", f"{rq.dev[s]:.4f}", f"{rq.z[s]:.2f}",
        "yes" if s in rq.flagged else "no", "yes" if s in rq.selected else "no"]
       for rq in dq.rates for s in rq.valid]
      + [["", s, "", "rejected", reason, "", "", "", "", "", "", "no", "no"]
         for rq in dq.rates for s, reason in rq.rejected])

    w("rejected_seeds.csv", ["rate_K_per_ns", "seed", "seed_dir", "reason"],
      [[f"{rq.rate:g}", s, os.path.basename(rq.run_dir), reason]
       for rq in dq.rates for s, reason in rq.rejected])

    w("selected_seeds.csv", ["rate_K_per_ns", "seed", "final_mz_300_310K", "mean_abs_dev", "dev_over_MAD"],
      [[f"{rq.rate:g}", s, f"{rq.fin[s]:.4f}", f"{rq.dev[s]:.4f}", f"{rq.z[s]:.2f}"]
       for rq in dq.rates for s in rq.selected])

    def stats_rows(use_sel: bool) -> list[list]:
        rows = []
        for rq in dq.rates:
            mat = rq.sel if use_sel else rq.full
            mean, sd, sem = _ens_stats(mat)
            for T, mu, s_, e_ in zip(rq.T, mean, sd, sem):
                rows.append([f"{rq.rate:g}", f"{T:g}", f"{mu:.5f}", f"{s_:.5f}", f"{e_:.5f}", mat.shape[0]])
        return rows

    header = ["rate_K_per_ns", "T_K", "mean_mz", "sd_mz", "sem_mz", "n_seeds"]
    w("ensemble_statistics_full.csv", header, stats_rows(False))
    w("ensemble_statistics_selected.csv", header, stats_rows(True))

    w("seed_selection_summary.csv",
      ["rate_K_per_ns", "run_dir", "seeds_done", "incomplete", "valid", "flagged", "rejected",
       "target", "selected", "escalated", "mean_err", "sd_err_rel", "final_err", "attempts", "note"],
      [[f"{rq.rate:g}", rq.run_dir, len(rq.seeds), rq.incomplete, len(rq.valid), len(rq.flagged),
        len(rq.rejected), rq.target, len(rq.selected), "yes" if rq.escalated else "no",
        f"{rq.err[0]:.4f}", f"{rq.err[1]:.3f}", f"{rq.err[2]:.4f}",
        ";".join(f"{n}:{mean:.3f}/{sd:.2f}/{fin:.3f}{'' if ok else '*'}"
                 for n, mean, sd, fin, ok in rq.attempts), ""]
       for rq in dq.rates]
      + [[f"{rate:g}", run_dir, "", "", "", "", "", "", "", "", "", "", "", "", why]
         for rate, run_dir, why in dq.skipped])

    paths["outlier_diagnostic_plot.png"] = _diagnostic_png(dq, os.path.join(out, "outlier_diagnostic_plot.png"))
    return paths


def _diagnostic_png(dq: DatasetQC, path: str) -> str:
    """Per rate: ensemble curves (full vs selected) and the dev/MAD anomaly bars."""
    from matplotlib.figure import Figure
    n = len(dq.rates)
    fig = Figure(figsize=(12.5, 2.7 * n), dpi=110, facecolor="white")
    gs = fig.add_gridspec(n, 2, width_ratios=[2.0, 1.0], wspace=0.18, hspace=0.42)
    for i, rq in enumerate(dq.rates):
        ax = fig.add_subplot(gs[i, 0])
        full = rq.full
        ax.plot(rq.T, full.T, color="0.75", lw=0.5, alpha=0.6)
        mf, sf, ff = _ens_stats(full)
        ms, ss, fs = _ens_stats(rq.sel)
        ax.fill_between(rq.T, mf - 2 * ff, mf + 2 * ff, color="0.35", alpha=0.25, lw=0)
        ax.fill_between(rq.T, ms - 2 * fs, ms + 2 * fs, color="#0072B2", alpha=0.30, lw=0)
        ax.plot(rq.T, mf, color="0.15", lw=2.0, label=f"full valid ({full.shape[0]})")
        ax.plot(rq.T, ms, color="#0072B2", lw=2.0, ls="--", label=f"selected ({len(rq.selected)})")
        for s in rq.flagged:
            ax.plot(rq.T, rq.grid(s), color="#D55E00", lw=1.0, alpha=0.8)
        ax.set_xlim(rq.T.max(), rq.T.min())
        ax.set_ylim(-1.05, 1.15)
        ax.set_xlabel("T (K)")
        ax.set_ylabel(r"$m_z$")
        ax.set_title(f"{rq.rate:g} K/ns  valid {len(rq.valid)}  selected {len(rq.selected)}  "
                     f"rejected {len(rq.rejected)}  flagged {len(rq.flagged)}", fontsize=9)
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.3)
        if i == 0:
            ax.legend(fontsize=7, loc="lower left")
        bx = fig.add_subplot(gs[i, 1])
        zs = [rq.z[s] for s in rq.valid]
        bx.bar(range(len(zs)), zs, color=["#D55E00" if s in rq.flagged else "#009E73" for s in rq.valid])
        bx.axhline(MAD_Z_FLAG, color="#D55E00", lw=1.0, ls=":")
        bx.set_xlabel("valid seed (index)", fontsize=7)
        bx.tick_params(labelsize=7)
        bx.set_title(r"mean $|m_z-\mathrm{med}|$ / MAD", fontsize=8)
    fig.suptitle(f"Seed QC and representative selection - {len(dq.rates)} rates "
                 f"(target {dq.target}, rng {dq.rng_seed})", fontsize=10)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    return path
