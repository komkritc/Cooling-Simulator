#!/usr/bin/env python3
"""Deterministic regression test for studio.core.seed_qc (seed QC + representative selection).

Builds a synthetic VAMPIRE-style dataset in tests/_qc_tmp/ (no real data, no global RNG -
every curve comes from a seed-dependent generator), then pins the behaviour the GUI relies on:

* technical validation always runs, in both Auto modes, and rejects exactly the seeds planted
  as corrupt (NaN fraction, |m_z| out of range, too few rows, implausible T, T span too small);
* statistical anomalies are flagged but KEPT (selectable, still counted in the full ensemble):
  the shifted seed of rate_500Kns, and the minority "partial" group of the bimodal rate_2000Kns;
* selection is reproducible across independent scans (fixed RNG seed);
* the selected subset reproduces the full valid ensemble (mean / SD / final window / up-down mix);
* when the target count cannot do that, the count is escalated until it can;
* a rate folder with no completed seeds is reported as skipped with a reason, not dropped;
* every report file is written, with one row per seed and the skip row.

Run:  .venv/bin/python tests/test_seed_qc.py   (also collected by pytest)
"""
import csv
import os
import shutil
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from studio.core import seed_qc                                            # noqa: E402
from studio.core.seed_qc import (REPORTS, TOL_COMP, TOL_FIN, TOL_MEAN, TOL_SD_REL,   # noqa: E402
                                 dataset_dir_of, reselect, scan_dataset, write_reports)

TMP = os.path.join(HERE, "_qc_tmp")
DECK = """# synthetic VAMPIRE deck (seed QC test)
grain:shape=sphere
output:real-time
output:temperature
output:magnetisation
output:magnetisation-length
output:mean-magnetisation-length
output:output-rate=4000
"""
# id -> kind of corruption planted in rate_500Kns (each hits a different technical rule)
CORRUPT = {11: "nan", 12: "big", 13: "short", 14: "cold", 16: "span"}
ANOMALY = 7          # valid but far from the median curve: flagged, kept
INCOMPLETE = 15      # data present, no DONE marker -> not part of the ensemble


def _write_seed(root: str, seed: int, *, tsw: float = 700.0, amp: float = 1.0,
                rows: int = 101, corrupt: str = "") -> None:
    """One seed folder: deck + output_seed<N>.dat, written as VAMPIRE does (T falling)."""
    d = os.path.join(root, f"seed_{seed}")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "input"), "w") as f:
        f.write(DECK)
    rng = np.random.default_rng(7000 + seed)          # local, id-dependent: fully reproducible
    T = np.linspace(800.0, 300.0, rows)
    mlen = amp * np.tanh((tsw - T) / 25.0) + rng.normal(0.0, 0.01, rows)
    if corrupt == "nan":
        mlen[:10] = np.nan                            # 10/101 rows > MAX_NAN_FRACTION
    elif corrupt == "big":
        mlen[40] = 1.5                                # |m_z| > MZ_ABS_MAX
    elif corrupt == "short":
        T, mlen = T[:20], mlen[:20]                   # < MIN_POINTS rows
    elif corrupt == "cold":
        T, mlen = np.linspace(100.0, 2200.0, rows), mlen[:rows]   # T outside T_PLAUSIBLE_K
    elif corrupt == "span":
        T, mlen = np.linspace(780.0, 500.0, rows), mlen[:rows]    # span < MIN_SPAN_K
    mdir = np.sign(mlen)                              # VAMPIRE stores a direction cosine and |m|
    cols = np.column_stack([np.arange(T.size, dtype=float) * 0.001, T,
                            mdir * 0.1, mdir * 0.2, mdir, np.abs(mlen), np.abs(mlen)])
    with open(os.path.join(d, f"output_seed{seed}.dat"), "w") as f:
        f.write("# synthetic output\n")
        np.savetxt(f, cols, fmt="%.6f")
    if corrupt != "incomplete":
        open(os.path.join(d, "DONE"), "w").close()


def build_dataset() -> str:
    """<tmp>/vampire_output/{rate_500Kns, rate_2000Kns, rate_9999Kns}."""
    shutil.rmtree(TMP, ignore_errors=True)
    ds = os.path.join(TMP, "vampire_output")
    fast = os.path.join(ds, "rate_500Kns")            # one switching event per seed, near-identical
    for s in range(1, 45):
        if s in CORRUPT:
            _write_seed(fast, s, corrupt=CORRUPT[s])
        elif s == INCOMPLETE:
            _write_seed(fast, s, corrupt="incomplete")
        elif s == ANOMALY:
            _write_seed(fast, s, tsw=300.0)           # switches ~400 K later than every other seed
        else:
            _write_seed(fast, s, tsw=700.0 + (s % 5))
    mix = os.path.join(ds, "rate_2000Kns")            # bimodal: 12 down, 6 partial, 12 up at 300 K
    for s in range(1, 31):
        if s <= 12:
            _write_seed(mix, s, tsw=150.0)
        elif s <= 18:
            _write_seed(mix, s, amp=0.2)
        else:
            _write_seed(mix, s, tsw=700.0)
    _write_seed(os.path.join(ds, "rate_9999Kns"), 1, corrupt="incomplete")   # nothing completed
    return ds


def main() -> int:
    ds = build_dataset()
    assert dataset_dir_of(os.path.join(ds, "rate_500Kns")) == ds
    fails: list[str] = []

    def check(cond, msg):
        print(("  ok   " if cond else "  FAIL ") + msg)
        if not cond:
            fails.append(msg)

    def faithful(rq) -> bool:
        mean_err, sd_err, fin_err, ok = seed_qc._errors(rq, rq.selected)
        check(ok and mean_err <= TOL_MEAN and sd_err <= TOL_SD_REL and fin_err <= TOL_FIN,
              f"{rq.rate:g} K/ns: selected reproduces full ensemble "
              f"(mean {mean_err:.4f}, sd {sd_err:.3f}, final {fin_err:.4f})")
        check(set(rq.selected) <= set(rq.valid) and len(set(rq.selected)) == len(rq.selected),
              f"{rq.rate:g} K/ns: selection is a duplicate-free subset of the valid seeds")

    dq = scan_dataset(ds, target=30)
    by_rate = {rq.rate: rq for rq in dq.rates}
    check(sorted(by_rate) == [500.0, 2000.0], f"rates scanned: {sorted(by_rate)}")
    check([(r, os.path.basename(p)) for r, p, _ in dq.skipped] == [(9999.0, "rate_9999Kns")],
          f"rate with nothing completed is skipped, not hidden: {dq.skipped}")

    fast, mix = by_rate[500.0], by_rate[2000.0]
    check(len(fast.seeds) == 43 and len(fast.valid) == 38,
          f"500 K/ns: {len(fast.seeds)} completed seeds, {len(fast.valid)} valid "
          f"(37 normal + 1 anomaly, {len(fast.rejected)} corrupt)")
    check([s for s, _ in fast.rejected] == sorted(CORRUPT),
          f"500 K/ns: planted corrupt seeds rejected {[s for s, _ in fast.rejected]}")
    why = " | ".join(w for _, w in fast.rejected)
    check(all(k in why for k in ("NaN", "|m_z|", "rows", "implausible", "span")),
          f"500 K/ns: one reject reason per technical rule: {why}")
    check(fast.incomplete == 1, f"500 K/ns: incomplete seed folders counted ({fast.incomplete})")
    check(fast.flagged == [ANOMALY], f"500 K/ns: planted anomaly flagged, not discarded: {fast.flagged}")
    check(ANOMALY in fast.valid and ANOMALY in fast.selected,
          "500 K/ns: flagged seed is still valid, still selectable")
    check(not fast.escalated and len(fast.selected) == 30,
          f"500 K/ns: target count reached ({len(fast.selected)}), no escalation")
    faithful(fast)

    check(len(mix.valid) == 30 and mix.flagged == [],
          f"2000 K/ns: a genuinely bimodal up/down/partial mix produces no outlier flag "
          f"(robust z spread, not absolute distance): {mix.flagged}")
    check(not mix.escalated and len(mix.selected) == 30,
          "2000 K/ns: 30 seeds available, target 30 met without escalation")
    faithful(mix)

    # A target too small to carry the anomaly's contribution must escalate; a target that
    # already reproduces the ensemble (the bimodal mix) must not.
    small = scan_dataset(ds, target=12)
    s_fast = next(rq for rq in small.rates if rq.rate == 500.0)
    s_mix = next(rq for rq in small.rates if rq.rate == 2000.0)
    check(s_fast.escalated and len(s_fast.selected) > 12,
          f"500 K/ns target 12: count raised to {len(s_fast.selected)} to keep the anomaly's weight")
    check([n for n, *_ in s_fast.attempts] == [12, 18, 27],
          f"500 K/ns escalation ladder {[n for n, *_ in s_fast.attempts]}")
    check(not s_mix.escalated and len(s_mix.selected) == 12,
          f"2000 K/ns target 12: met without escalation ({len(s_mix.selected)})")
    sel_mix = seed_qc._composition(s_mix, s_mix.selected)
    full_mix = seed_qc._composition(s_mix, s_mix.valid)
    check(max(abs(a - b) for a, b in zip(sel_mix, full_mix)) <= TOL_COMP,
          f"2000 K/ns: up/reversed mix reproduced at target 12: selected {sel_mix} vs full {full_mix}")
    faithful(s_fast)
    faithful(s_mix)

    # reproducibility: an independent scan of the same data chooses the same seeds
    again = scan_dataset(ds, target=30)
    check([rq.selected for rq in again.rates] == [rq.selected for rq in dq.rates],
          "selection identical across independent scans (fixed RNG)")
    check([rq.selected for rq in scan_dataset(ds, target=30, rng_seed=seed_qc.RNG_SEED + 1).rates]
          == [rq.selected for rq in dq.rates],
          "stride-based choice is deterministic: a different RNG stream changes nothing "
          "(the RNG only fills collisions)")

    # Auto OFF: no reduction, and validation still rejects the same seeds
    off = scan_dataset(ds, target=30, auto=False)
    check(all(len(rq.selected) == len(rq.valid) for rq in off.rates) and off.auto is False,
          "auto off: every valid seed stays in the analysis")
    check([s for s, _ in next(rq for rq in off.rates if rq.rate == 500.0).rejected] == sorted(CORRUPT),
          "auto off: technical validation still rejects the same seeds")
    reselect(off, 12)
    check(all(len(rq.selected) == len(rq.valid) for rq in off.rates),
          "auto off: reselect does not reduce anything")

    # changing the target re-applies the selection (and may still escalate to stay faithful)
    reselect(dq, 12)
    check(len(fast.selected) > 12 and fast.escalated,
          f"reselect(12) on 500 K/ns raised the count to {len(fast.selected)}")
    check(len(mix.selected) >= 12, f"reselect(12) on 2000 K/ns -> {len(mix.selected)}")
    faithful(fast)
    faithful(mix)
    reselect(dq, 30)

    paths = write_reports(dq)
    check(sorted(paths) == sorted(REPORTS), f"all {len(REPORTS)} report files written")
    check(all(os.path.getsize(p) > 0 for p in paths.values()), "report files non-empty")
    check({os.path.dirname(p) for p in paths.values()} == {os.path.join(ds, "qc")},
          f"reports land in <dataset>/qc: {paths[REPORTS[0]]}")
    with open(paths["seed_quality_report.csv"]) as f:
        rows = list(csv.DictReader(f))
    n_valid = sum(len(rq.valid) for rq in dq.rates)
    n_rej = sum(len(rq.rejected) for rq in dq.rates)
    check(len(rows) == n_valid + n_rej, f"quality report: one row per valid + rejected seed ({len(rows)})")
    check(sum(r["status"] == "rejected" for r in rows) == n_rej
          and all(r["reason"] for r in rows if r["status"] == "rejected"),
          "quality report carries a reason for every reject")
    check(sum(r["flagged"] == "yes" for r in rows) == sum(len(rq.flagged) for rq in dq.rates),
          "quality report marks every flagged seed")
    check(sum(r["selected"] == "yes" for r in rows)
          == sum(len(rq.selected) for rq in dq.rates), "quality report marks every selected seed")
    with open(paths["rejected_seeds.csv"]) as f:
        check(sum(1 for _ in f) - 1 == n_rej, "rejected_seeds.csv lists exactly the rejects")
    with open(paths["selected_seeds.csv"]) as f:
        check(sum(1 for _ in f) - 1 == sum(len(rq.selected) for rq in dq.rates),
              "selected_seeds.csv lists exactly the selected seeds")
    with open(paths["seed_selection_summary.csv"]) as f:
        summ = list(csv.DictReader(f))
    check(len(summ) == 3 and summ[-1]["rate_K_per_ns"] == "9999" and summ[-1]["note"],
          f"summary lists both scanned rates plus the skipped one: {[s['rate_K_per_ns'] for s in summ]}")
    for name in ("ensemble_statistics_full.csv", "ensemble_statistics_selected.csv"):
        with open(paths[name]) as f:
            r = list(csv.DictReader(f))
        check({int(x["n_seeds"]) for x in r} and len({x["rate_K_per_ns"] for x in r}) == 2,
              f"{name}: per-rate gridded ensemble stats")
    check(len({int(x["n_seeds"]) for x in csv.DictReader(open(paths["ensemble_statistics_full.csv"]))})
          == len({len(rq.valid) for rq in dq.rates}),
          "full stats CSV n_seeds is the full valid count, not the selected one")

    print(f"\nSUMMARY: {'PASS' if not fails else 'FAIL'}"
          + (f" ({len(fails)}): " + "; ".join(fails) if fails else ""))
    return 0 if not fails else 1


def test_seed_qc():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
