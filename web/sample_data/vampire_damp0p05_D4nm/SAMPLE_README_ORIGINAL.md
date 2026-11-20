# Shareable analysis package — vampire_damp0p05_D4nm

Self-contained: VAMPIRE field-cooling data + Roy-model ME + plotting scripts.
Requires Python 3 with numpy + scikit-learn (for the RF material model).

## Layout
- `cooling_T800/runs/rate_{200,500,1000,1500,2000,6000}Kns/seed_*/`
  - `output_seed*.dat` — columns: 0 step, 1 T(K), 6 mean |m|, 7 m_z direction
    (signed cos θ). Final M_z = col7 × col6 averaged over the 300–310 K window.
  - `DONE` marker = run complete; only DONE seeds are loaded.
- `decks/` — exact VAMPIRE input decks used for every rate (protocol: 4 nm FePt
  L10 cylinder, α = 0.05, B = 1.00531 T, equilibration 800 K × 200 000 steps,
  then linear cooling 800→300 K at the listed rate).
- `model/rf_model_all_targets.pkl` + `feature_scaler.pkl` — RF material model
  (m_s(T), χ∥(T), χ⊥(T), Tc) trained on VAMPIRE equilibrium data; used by the
  ME module.

## Scripts (run from this directory)
```bash
python3 me_B_roy.py [RATE ...]        # ME only: m(300K), P_rev, rmse vs VAMPIRE
python3 plot_one_rate.py RATE [TAG]   # 4-panel VAMPIRE+ME figure, e.g. `plot_one_rate.py 1500`
                                      # -> plots_RATE/mz_RATE.png + numbers_RATE.txt
python3 plot_500_vs_1000.py           # head-to-head 500 vs 1000 K/ns comparison
```
Output figures/numbers land in `plots_<rate>/` next to the scripts.
Scripts also work when placed in `derived/` (path resolution checks both).

## Key results (m_z at 300 K, 50 seeds unless noted)
| rate K/ns | mean M_z | P_rev | partly ordered | Roy-ME P_rev | Roy-ME rmse |
|---:|---:|---:|---:|---:|---:|
| 200 (25 seeds)  | +0.788 | 0    | 0 | 0.001 | 0.012 |
| 500 (25 seeds)  | +0.787 | 0    | 0 | 0.005 | 0.016 |
| 1000 | +0.757 | 0.020 | 0 | 0.020 | 0.020 |
| 1500 | +0.693 | 0.060 | 0 | 0.035 | 0.038 |
| 2000 | +0.689 | 0.060 | 1/50 | 0.048 | 0.049 |
| 6000 | +0.591 | 0.080 | 11/50 | 0.116 | 0.074 |

ME = Roy-report two-level master equation (ω₁ = γ/χ⊥(T), barrier ×(1−H/H_K)²);
module docstring in `me_B_roy.py` has the full physics.

`derived/` keeps the development history (older variants, extra comparisons).
