#!/usr/bin/env python3
"""Golden regression test (Phase acceptance): the Studio core must reproduce
every validated numbers_<rate>.txt line-for-line, for all six rates.

Run with a python that has numpy (GUI venv not required).
Also exercises: validation rules, audit record save -> re-run -> identical.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from studio.core.session import AnalysisSession          # noqa: E402
from studio.core import audit_manager                    # noqa: E402

GOLDEN = json.load(open(os.path.join(os.path.dirname(HERE), "baselines", "golden.json")))


def run_rate(rate: str, tmp_records: str):
    g = GOLDEN["rates"][rate]
    sess = AnalysisSession(g["run_dir"])
    sess.load_seeds()
    res = sess.run_comparison()
    got = sess.numbers_lines(res)
    want = g["raw_lines"]
    ok = got == want
    issues = sess.validate()
    crit = [i for i in issues if i.severity == "critical"]
    print(f"[{rate} K/ns] numbers {'IDENTICAL' if ok else 'DIFF'}   "
          f"validation: {sum(1 for i in issues if i.severity=='pass')} pass / "
          f"{sum(1 for i in issues if i.severity=='warning')} warn / "
          f"{len(crit)} critical")
    if not ok:
        for a, b in zip(want, got):
            mark = " " if a == b else "X"
            print(f"  {mark} want: {a}\n  {mark} got : {b}")
    if crit:
        for i in crit:
            print("   CRITICAL:", i.rule, i.message)
    # record save + exact re-run
    rec = audit_manager.save_record(sess, res, issues, out_root=tmp_records)
    loaded = audit_manager.load_record(rec)
    sess2 = audit_manager.rerun_from_record(loaded)
    sess2.load_seeds()
    again = sess2.numbers_lines(sess2.run_comparison())
    assert again == got, "re-run from record differs!"
    print(f"          record {os.path.basename(rec)}: re-run identical")
    return ok and not crit


def main():
    tmp = os.path.join(HERE, "_records_tmp")
    os.makedirs(tmp, exist_ok=True)
    results = {r: run_rate(r, tmp) for r in ("200", "500", "1000", "1500", "2000", "6000")}
    print("\nSUMMARY:", {k: ("PASS" if v else "FAIL") for k, v in results.items()})
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
