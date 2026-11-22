# Master-Equation Magnetisation Simulator — web version (implemented)

Streamlit port of the desktop app. It reuses the **same physics code**
(`studio/core/`) with **zero changes**, so its numbers are identical to the
desktop app by construction — and the exported figure is **byte-identical**.

Physics of this app (and of the desktop app): the **Prof. Roy W. Chantrell Master
Equation** — Pallas-Yateson coupled heat and magnetisation equations, with the Lindhard-Kohlert damping tensor `A` evaluated
from the validated **1–10 nm LUT** (`lut_current_rf_1-10nm_dD0p1.csv`, registered
by SHA-256). The solver uses adaptive Runge-Kutta steps. This is a phenomenological
two-temperature style model — it does not resolve electron or phonon populations
explicitly.

Last update: 2026-11-20.

## A. Quick start (works right now, locally)

```bash
cd .../app
bash web/run_web.sh              # creates web/.venv on first run, serves :8590
bash web/run_web.sh --open       # same, open a browser
bash web/run_web.sh 8600         # custom port
bash web/run_web.sh --tests      # the acceptance suite instead of the server
```

Open `http://127.0.0.1:8590`. Nothing leaves your machine except the browser
page itself. The desktop app is not affected: the web venv is
`web/.venv` (a real directory), while `app/.venv` is the shared desktop venv
and is never touched.

First load takes a few seconds (LUT parse + interpolation grid); after that a
run takes well under a second.

## B. Tests (the acceptance gate)

```bash
cd .../app/web
.venv/bin/python -m pytest tests -q      # 34 tests, ~20 s
```

| file | checks |
|---|---|
| `tests/test_web_parity.py` | all six rates match `app/baselines/golden.json`; three figure variants (dark, light, light+smoothed) are each byte-identical to a figure the desktop app saved; numpy/matplotlib pins; **all three bundled runs** (100, 200, 500 K/ns) reproduce the desktop comparison contract (seeds, m/ms both sides, Δ, RMSE, mean m_z, up/down/reversed seeds, validation counts); ZIP upload resolves and zip-slip attempts are rejected |
| `tests/test_web_ui.py` | driven through streamlit's `AppTest`: default inputs match the desktop values; Run ME produces a figure and the 1.3977 ratio; rate −/+ buttons drive the rate box; D and field stay in sync; atoms-from-D; sample load, import settings, clear; the Psw / m-ms tab is absent |

`web/baselines/capture_from_desktop.py` (run it with the desktop venv, `.venv/bin/python`) regenerates every hash and comparison number straight from the
desktop app, so the contract can be refreshed when the desktop app changes.

**If a test fails, the web app is not trustworthy** — the numbers or the figure
drifted away from the validated desktop output. `context.check_pins()` also
prints a warning in the sidebar whenever the installed numpy/matplotlib differs
from the pins in `requirements.txt`, because the figure hash depends on them.

## C. Layout

```
web/streamlit_app.py        entry point (sidebar + tabs)
web/webapp/
  context.py      default inputs, colours, paths, version block, pin check
  runner.py       ME solve, VAMPIRE load, golden cross-check
  plot_simple.py  the simplified Main-plot figure (a fresh Figure per run)
  sidebar.py      all controls, incl. the +/- rate buttons
  main_tab.py     figure, ratio card, VAMPIRE cards, export buttons
  actions.py      callbacks (run, sample load, import settings)
  exports.py      PNG / CSV / standalone .py / audit record
  uploads.py      sample data + ZIP/file uploads, temp folders
web/tests/          parity tests (physics) + UI tests (AppTest)
web/baselines/      figure hashes + comparison numbers (the acceptance contract)
                      capture_from_desktop.py regenerates them from the desktop app
web/data/           optional local LUT copy (git-ignored; not present — the
                      app uses ../lut_current_rf_1-10nm_dD0p1.csv)
web/sample_data/    bundled aggregated VAMPIRE runs - see sample_data/README.md
web/requirements.txt     pinned: streamlit 1.67.0, numpy 2.5.5,
                         matplotlib 3.11.1, pillow 12.3.0
web/requirements-dev.txt pytest (not installed on Streamlit Cloud)
web/.streamlit/config.toml
web/run_web.sh
web/F..K_*.md              planning documents (v2, Streamlit); kept as history
```

## D. Widget parity with the desktop app

One page, no tabs: sidebar with all controls, then the figure, the ratio card, the
VAMPIRE comparison card, the validation card and the export buttons.

| desktop (`simple_window`) | web | notes |
|---|---|---|
| `sb_rate` spinbox + `rate_deck` combo | `st.slider` 50–6000 + `st.number_input` + **−/+** buttons | deck → `st.selectbox` "example run" (the VAMPIRE dropdown) drives the rate |
| `sb_rate_minus` / `sb_rate_plus` (new) | `st.button` −/+ (`−10/+10` at 200 K/ns, `−50/+50` at 500) | callback writes the rate box |
| D slider + box (linked, re-run) | `st.slider` 1–10 (LUT range) + `st.number_input` | out-of-range D is clamped and labelled "outside the LUT" |
| T0, T1 | `st.number_input` | web rejects T1 ≥ T0, matching the solver |
| Field slider + box (linked, re-run) | `st.slider` 0–3 (0.0001 step) + `st.number_input` 0–50 | |
| damping slider + box | `st.slider` 0–1 + box | always visible (replaces import-settings block) |
| atoms, cell a/c, moment, γ, dT, P0, damp_use | `st.expander("Material & solver (more)")` + **atoms from D** button | cell shown in Å |
| dark, grid, params, invert-x, Savitzky-Golay + window/poly | checkboxes + number inputs | same controls; the web app opens **light** (as the desktop does) and with **smoothing on** |
| folder input + Load/Clear | `st.selectbox` of bundled runs + Load / Clear buttons | no folder picker in a browser |
| ZIP / files upload | `st.file_uploader` (a .zip of the run folder, or the `*_input.json` / `.mat` / `output_seedN.dat` files) | temp dir per session, cleaned at exit |
| import settings buttons | two checkboxes (auto-load / auto-clear) | same effect |
| Run ME / Run Queue / Batch Scan / Reference Test | **Run ME** only | queue and scans are not in v1 |
| Export buttons (5) | PNG, arrays CSV, standalone .py, audit record ZIP | `st.download_button` |
| status bar + progress bar | `st.toast` + `st.status` | no per-step progress bar |
| Psw / m-ms Test tab | **not in the web version** | desktop only, by your decision |

Not in the web app: the **Psw / m-ms Test tab** (removed on request — it stays
in the desktop app), Run Queue, Batch Scan, Reference Test, LUT builder, Settings
dialog.
There is no Pext input and no separate thickness input (D is the thickness).

## E. Physics constants that must not drift

| quantity | value | where it comes from |
|---|---|---|
| D (particle diameter) | 1–10 nm LUT range, default 4.0 nm; **loading a VAMPIRE run sets D from the deck's `particle-size` (e.g. 40.8 Å = 4.08 nm) and the LUT interpolates to it** (no snap to 4.00 nm) | LUT CSV header, `lut_material.py`, deck |
| damping tensor A | interpolated from the 1–10 nm LUT by SHA-256 | `lut_material.py`, `mapping_engine.py` |
| γ (gyro) | 1 | `MEConfig`, desktop default |
| dT (solver temperature step) | 1 K | `MEConfig`, desktop default |
| P0 (initial up-population) | 0.50 | `MEConfig`, desktop default |
| atoms N | 4602 at D = 4 nm | `atoms_from_d(D, a, c)` |
| T0 → T1 | 800 → 300 K | `MEConfig` |
| B | 1.00531 T | `MEConfig` (≈ μ0H, μ = 3.23 μB) |
| damping α (α_G) | 0.05 | `MEConfig` |
| moment μ | 3.23 μB | `MEConfig` |
| cell a / c | 2.72 / 3.85 Å | `MEConfig` |
| numpy / matplotlib | 2.5.5 / 3.11.1 | `requirements.txt` + the desktop golden baseline |
| plotted curve smoothing | on by default on the web (window 15 K, order 3) — plot only, the solver, the ratio and the CSV stay raw | user decision; desktop default is off |
| theme | light (the desktop also starts light: `app.py` reads `theme=light`) | sidebar can switch to dark |
| figure hash, dark + no smoothing | `1967cb52d12914…` | `web/baselines/web_golden.json` |
| figure hash, light + no smoothing | `4dc75cff008089…` | same file, `figure_light` |
| figure hash, **web default** = light + smoothing | `b9b58da5047dc6…` | same file, `figure_default` |

The solver itself is **adaptive Runge-Kutta** (`scipy`-free, inside
`me_solver.py`), not a fixed-step scheme — `dT` only sets the temperature
sampling of the output.

## H. Bundled VAMPIRE sample runs (sidebar ▸ "example run")

| run | cooling rate | seeds | ME m/ms @300 K | VAMPIRE m/ms @300 K | Δ | RMSE | up / down / reversed |
|---|---|---|---|---|---|---|---|
| `rate_100Kns` | 100 K/ns | 25 | 0.9996 | 0.9960 | 0.0035 | 0.0120 | 25 / 0 / 0 |
| `rate_200Kns` | 200 K/ns | 25 | 0.9989 | 0.9966 | 0.0023 | 0.0118 | 25 / 0 / 0 |
| `rate_500Kns` | 500 K/ns | 25 | 0.9895 | 0.9978 | 0.0083 | 0.0164 | 25 / 0 / 0 |

All three come from the same grain (α = 0.05, D = 4.0 nm, 800 → 300 K) and use the
same seed ensemble (`seed_1 … seed_25`), so the columns are comparable between
runs. The source folder for 100 K/ns actually holds 26 completed seeds; the 26th
was left out on purpose so that all bundled runs use the identical 25-seed
ensemble. These numbers are the contract in `baselines/web_golden.json`
(`vampire_samples`) and each one was captured from the **desktop** code path, so a
web run that drifts fails the test suite.

`sample_data/README.md` explains what ships per seed and how to add more runs.

## F. Deploying on share.streamlit.io (not done — one decision needed)

Streamlit Community Cloud deploys **from a public GitHub repository**. You asked
for local-only git, so choose one:

1. **public mirror repo** (free, what the plan assumes): a minimal repo built by
   a script — `streamlit_app.py`, `webapp/`, `web/tests/`, `web/baselines/`,
   `web/sample_data/` (aggregated seed text files only), pinned
   `requirements.txt`, `.streamlit/config.toml`, plus **vendored copies** of
   `studio/core/*.py` and `studio/gui/theme.py` and the LUT CSV, with a
   `VENDORED.sha256` manifest and a README stating that the code is generated
   from the private repo and must not be edited there. **No VAMPIRE raw tree, no
   `run_stdout.txt`, no git metadata.**
2. **private Streamlit app** (paid) — deploys from a private repo.
3. **self-hosted Streamlit** on the lab server — no GitHub at all; the full LUT
   and full sample data can be mounted from outside the repo. `run_web.sh`
   already does this locally; put it behind nginx with websocket support.

Until you choose, everything stays local and this repo keeps no remote.

## G. Status (what is done)

1. ✅ solve + golden cross-check (6/6 rates, 0 mismatches)
2. ✅ figure parity — PNG byte-identical to the desktop export
3. ✅ sidebar + live run
4. ✅ result cards + exports (PNG, arrays CSV, standalone script, record ZIP)
5. ✅ VAMPIRE input: bundled sample dropdown + ZIP/file upload + zip-slip guard
6. ⬜ ~~Psw / m-ms Test tab~~ — removed from the web version on request; the
   desktop app keeps it (`studio/gui/psw_tab.py` untouched). The Streamlit prototype that
   was removed is parked outside the tree at `../_attic_web_psw/psw_tab.py.removed`
   (git-ignored) in case it is ever wanted again
7. ✅ hardening: pin check, D clamp to LUT range, upload size cap, temp cleanup
8. ✅ docs + 34 tests (3 bundled runs, 3 figure variants)
9. ⬜ deployment (blocked on the decision in F)
