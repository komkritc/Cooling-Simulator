# ME Cooling Simulator (cooling_simulator/)

Desktop PySide6 app plus a browser (Streamlit) port in `web/`.
Physics solver is shared unchanged between the two.

Run: `./run.sh` (simple GUI) · old full GUI: `.venv/bin/python app_full.py`

---

# VAMPIRE–ME Comparison Studio — Planning Package (for review, NOT approved for implementation)

Status: **PLANNING ONLY.** No implementation code has been written.
This folder contains the deliverables requested for review:

| File | Deliverable | Content |
|---|---|---|
| `A_technical_development_plan.md` | A | Architecture, modules, data flow, file formats, extraction & validation strategy |
| `B_gui_wireframe.md` | B | Full GUI layout, controls, parameter tables, status indicators, plot interface, workflow |
| `C_parameter_mapping_spec.md` | C | Exact VAMPIRE source fields → ME variables, unit conversions, missing-parameter handling |
| `D_implementation_roadmap.md` | D | Phases, testing strategy, acceptance criteria |
| `E_risk_assessment.md` | E | Risks: extraction ambiguity, missing material data, unit inconsistencies, atomistic-vs-ME physics gaps |

Ground truth used to write this plan (inspected, not modified):

```
/data/mint_lab/projects/Cooling_Model_Comparison/data/raw/vampire_damp0p05_D4nm/
├── README.md                          # shareable-package description, column conventions, key results table
├── manifest.tsv                       # per-run provenance: deck md5, mat md5, status, origin path
├── cooling_T800/runs/rate_{200,500,1000,1500,2000,6000}Kns/seed_*/
│   ├── input                          # full VAMPIRE deck (auto-generated, fully commented)
│   ├── FePt_L10_sc_6350.mat           # material file (damping, moment, anisotropy, exchange)
│   ├── output_seed*.dat               # 14-column time series, commented header
│   ├── log, run_stdout.txt            # VAMPIRE 7.0.0 run log (version, githash, atom counts)
│   └── DONE                           # completion marker
├── decks/fc_D4nm_*Kns_T800.input      # archived canonical decks per rate
├── model/rf_model_all_targets.pkl + feature_scaler.pkl   # RF surrogates m_s, chi_par, chi_perp
├── derived/me_B_roy.py                # validated Roy ME implementation (physics reference)
└── derived/plots_*/plot_<rate>Kns_standalone.py          # validated plotting pipeline (all 6 rates,
                                                          #   outputs currently reproduce byte-identically)
```

Key design constraint agreed with the user: **the ME physics is reused, not rewritten**
(`me_B_roy.py` is refactored into a GUI-independent core module; its validated
numbers are the regression-test baseline).

---

## Implementation status (updated after build)

Status: **BUILT & REGRESSION-VERIFIED** — Phases 0–5 complete.

### Run the app

```bash
./run.sh                       # opens the GUI (uses pinned .venv)
./run.sh /path/to/rate_500Kns  # open a run directory directly
bash web/run_web.sh            # browser version (Streamlit, own venv) - web/README.md
```

GUI follows the approved mockup `ui.png`: left 5-step rail, tabs
(Configuration / Plots / Numerical Results / Parameter Audit / Log),
numbered cards, Roy two-state ME equation viewer (mathtext), guarded
damping-interpretation switch (rule M2), 2x2 results figure (dark on
screen; exports use the validated light style), export PNG / CSV / PDF
report, and reproducible comparison records
(`record.json + arrays.csv + numbers.txt + figures + checksums.sha256`)
written to `<data_root>/records/cmp_<utc>/` — simulation inputs are never
modified.

### Regression evidence

```bash
.venv/bin/python tests/test_golden.py
# -> SUMMARY: {'200': 'PASS', '500': 'PASS', '1000': 'PASS',
#              '1500': 'PASS', '2000': 'PASS', '6000': 'PASS'}
```

* All six rates reproduce `derived/plots_*/numbers_*.txt` line-identically.
* Exported `mz_500.png` from the GUI is **byte-identical** to the validated
  baseline PNG (requires `matplotlib==3.11.1`, pinned in `requirements.txt` —
  3.11.2 changes only the PNG metadata chunk, not pixels).
* Each saved record re-runs to identical numbers (`rerun_from_record`).
* Validation panels report 8 pass / 5 warning / 0 critical per rate
  (warnings: unit-assumed deck fields, RF D 4.0 vs deck 4.08 nm snapped,
  log `dampconstant=0.1` vs mat 0.05 — validated code used 0.05, kept).

### Seed QC and representative seed selection (`fdf14bc`)

`studio/core/seed_qc.py` (Qt-free, shared by both apps) validates every
`output_seed*.dat` in each `rate_*Kns` folder of a loaded dataset and then reduces the
ensemble to a representative subset:

* **Technical validation always runs**, in both modes — a corrupt seed (missing
  time/`m_z` columns, < 50 usable rows, NaN fraction > 5 %, non-monotone temperature,
  < 300 K cooling span, T outside 200–2000 K, |m_z| > 1.155) never enters the analysis.
* **Statistical outliers are flagged, kept, and stay eligible** — discarding them would
  understate the ensemble spread the subset has to reproduce.
* Selection is quantile sampling over the final-`m_z` distribution with a **fixed
  `RNG_SEED`** (same folder + target ⇒ same seeds), accepted only if it reproduces the
  full valid ensemble within: mean curve 0.05, SD 25 % relative, 300–310 K final-window
  mean 0.10, up/reversed fractions 0.05. A target too small to pass is raised
  automatically (`+max(5, n//2)`) until it passes or every valid seed is used.

Sidebar: `cb_auto` "Auto Seed Selection" (default on) + `sp_nseed` "N seeds/rate"
(default 50), a Valid / Selected / Rejected table per rate, and a label stating
"Auto Seed Selection: N of M valid seeds used". The legend says
`n=N selected of M valid seeds`, the figure annotation `VAMPIRE(median of N seeds)` —
never a bare `n=` when a subset is in play. Plot-only display toggles
`cb_traces_all`, `cb_traces_sel`, `cb_sem` (±2 SEM band), `cb_sd` (±SD band) are
remembered in `QSettings` (`traces_all`, `traces_sel`, `sem_band`, `sd_band`).
Gate: `tests/test_seed_qc.py`; the web equivalent is `web/tests/test_web_ui.py`.

### Layout

```
app.py                 entry point (PySide6)
requirements.txt       pinned: numpy 2.5.5, matplotlib 3.11.1, sklearn 1.9.1, PySide6 6.12.0
studio/core/           Qt-free engine: parsers, extraction, mapping, frozen ME solver
                       (me_B_roy refactor), stats, validator, audit, plotting
studio/gui/            theme.py, widgets.py, main_window.py (mockup-faithful)
baselines/golden.json  parsed numbers_*.txt for all 6 rates
tests/test_golden.py   regression gate (numbers + validation + record re-run)
```
