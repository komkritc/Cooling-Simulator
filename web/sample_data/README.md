# Bundled VAMPIRE sample runs

Output of VAMPIRE (`vampire-2025-08-06`) finite-temperature simulations of the
same grain the ME model simulates: an L1₀ FePt-style grain (FePt_L10_sc_6350.mat
decks), damping α = 0.05, diameter 4.0 nm, field-cooled 800 K → 300 K. Each
`rate_*Kns/` folder holds 25 independent seeds.

| folder | cooling rate | seeds |
|---|---|---|
| `vampire_damp0p05_D4nm/cooling_T800/runs/rate_200Kns/` | 200 K/ns | 25 |
| `vampire_damp0p05_D4nm/cooling_T800/runs/rate_500Kns/` | 500 K/ns | 25 |

Per seed folder (`seed_1`, `seed_2`, …):

* `output_seedN.dat` — the time/temperature series actually used. Its column
  layout is **not assumed**: the header of each file is parsed, and the
  directives are cross-read from the deck file `input` and the `.mat` material
  file (`studio/core/vampire_output_reader.py`).
* `input` (the VAMPIRE deck script), `FePt_L10_sc_6350.mat`, `log`, `DONE` — the
  deck that produced it,
  so the comparison can check the *conditions* (damping, field, temperature
  range, grain size) instead of trusting a label.

Deliberately **not** copied: `run_stdout.txt` (build noise, no numbers we use,
and it embeds server paths), and no raw spin-texture dumps. This is a small
slice of the simulation output, not the VAMPIRE working tree — keep the rest of
that tree private if the app is ever published.

The web app reads these with the same code as the desktop app, so the comparison
numbers are the ones frozen in `web/baselines/web_golden.json`
(m/ms 0.9895 vs 0.9978 at 300 K, RMSE 0.0164, consistency validation
 8 pass / 5 warning / 0 critical at 500 K/ns).

## Adding more runs

Drop another `rate_*Kns/` folder (with `seed_*` subfolders) next to the existing
ones, or place a new `<material>/…/runs/` tree next to
`vampire_damp0p05_D4nm/`. The "example run" dropdown re-scans `sample_data/` on
each page load — no code change needed. Keep the folder names `rate_<number>Kns`:
the cooling rate is read from the name and compared with the rate set in the
sidebar, and a mismatch is reported rather than silently comparing different
conditions.

Users who do not want the bundled data can upload their own ZIP of a run folder
(or select the `*_input.json` / `.mat` / `output_seedN.dat` files) in the sidebar.
