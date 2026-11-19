#!/usr/bin/env python3
"""Phase 0: freeze validated references into baselines/golden.json + core registry.

Reads the existing validated outputs (numbers_*.txt produced by the standalone
scripts, byte-reproducible) and the RF pickle hashes.  Run once; outputs are
inputs to the validator (R1) and the golden regression test.
"""
import hashlib
import json
import os
import re
import sys

DATA = "/data/mint_lab/projects/Cooling_Model_Comparison/data/raw/vampire_damp0p05_D4nm"
HERE = os.path.dirname(os.path.abspath(__file__))


def sha256(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def parse_numbers(path):
    """Parse a validated numbers_<rate>.txt into a comparable dict."""
    lines = [l.rstrip("\n") for l in open(path) if l.strip()
             and not l.startswith("plot ->")]
    out = {"raw_lines": lines}
    m = re.search(r"m\(300 K\) = ([\d.]+), P_rev = ([\d.]+); rmse .* = ([\d.]+)", lines[1])
    out["m300"], out["p_rev"], out["rmse"] = map(float, m.groups())
    m = re.search(r"(\d+) seeds: up (\d+), reversed (\d+), partly ordered (\d+); "
                  r"mean final Mz = ([+\-\d.]+) \+- ([\d.]+); mean \|m\| at 300 K = ([\d.]+)",
                  lines[2])
    out["n_seeds"], out["up"], out["down"], out["partial"] = map(int, m.groups()[:4])
    out["mean_final"], out["sem_final"], out["m_300_abs"] = map(float, m.groups()[4:])
    return out


def main():
    model_dir = os.path.join(DATA, "model")
    h_model = sha256(os.path.join(model_dir, "rf_model_all_targets.pkl"))
    h_scaler = sha256(os.path.join(model_dir, "feature_scaler.pkl"))
    registry = {h_model: {"registered": True, "scaler_sha256": h_scaler,
                          "D_nm": 4.0, "Tc_K": 643.0,
                          "trained_on": "VAMPIRE equilibrium data, 4 nm FePt family",
                          "source_dir": model_dir}}
    reg_path = os.path.join(HERE, "studio", "core", "rf_registry.json")
    json.dump(registry, open(reg_path, "w"), indent=1)
    print("wrote", reg_path)

    golden = {"data_root": DATA, "rates": {}}
    specs = [("200", "derived/plots_200/numbers_200.txt"),
             ("500", "derived/plots_500/numbers_500.txt"),
             ("1000", "derived/plots_1000/numbers_1000_v2.txt"),
             ("1500", "derived/plots_1500/numbers_1500.txt"),
             ("2000", "derived/plots_2000/numbers_2000.txt"),
             ("6000", "derived/plots_6000/numbers_6000.txt")]
    for rate, rel in specs:
        p = os.path.join(DATA, rel)
        g = parse_numbers(p)
        g["reference_figures"] = {
            "png": os.path.join(DATA, rel.replace("numbers", "mz").replace(".txt", ".png"))}
        g["run_dir"] = os.path.join(DATA, "cooling_T800", "runs", f"rate_{rate}Kns")
        golden["rates"][rate] = g
    gp = os.path.join(HERE, "baselines", "golden.json")
    json.dump(golden, open(gp, "w"), indent=1)
    print("wrote", gp)


if __name__ == "__main__":
    sys.exit(main())
