# G — Web UI wireframe and control parity (Streamlit)

## 1. Page layout

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│ ME Cooling Simulator v1.x-web                    LUT: lut_current_rf ✓ registered  │
├──────────────────────────────┬────────────────────────────────────────────────────┤
│ st.sidebar (fixed, 360 px)   │  single page (no tabs)  │
│                              │                                                    │
│ COOLING RATE(S) K/ns         │  ┌── 2x2 figure (A m(T) vs VAMPIRE±2sem,           │
│ [ 500 ] [−100] [+100]        │  │  B ms & chi, C Gamma, D P) ─────────────────┐  │
│ GRAIN DIAMETER  4.00 nm      │  │  A │ B                                      │  │
│  [====|====] [4.00]          │  │  C │ D                                      │  │
│ START T  [800]  END T [300]  │  └─────────────────────────────────────────────┘  │
│ APPLIED FIELD B [1.00531 T]  │  parameter footer (toggle "Show parameters")       │
│ DAMPING λ      [0.05]        │                                                    │
│ ▸ Show more parameters       │  RESULT LINE (st.code, selectable, same wording    │
│    Atoms [4602] [from D]     │   as session.numbers_lines())                     │
│    Cell a / c / μ / γ        │                                                    │
│    T step / P₀               │  VALIDATION  8 pass · 5 warn · 0 critical          │
│    Damping use [λ=α ⌄]       │    (st.expander per rule, same ids/messages)       │
│ [ Run ME ]  (primary)        │  MISMATCH CARD (shown when a run is loaded)        │
│ ☐ Smooth (SG) [15 K] [ord 3] │    ME vs VAMPIRE field-by-field, tol 1e-6          │
│ ☑ Show grid                  │                                                    │
│ ☑ Show parameters on plot    │  EXPORTS  [PNG] [CSV] [Export .py] [Record .zip]   │
│ ☐ Dark theme  ☑ Invert x     │  UPLOAD: VAMPIRE run folder (.zip or multi-file)   │
│ VAMPIRE RUN FOLDER           │  LOG / ACTIVITY (st.expander)                      │
│  [upload .zip] [×]           │                                                    │
│  ☑ Import VAMPIRE settings   │                                                    │
│  loaded: rate_500Kns · 25 seeds │                                                 │
└──────────────────────────────┴────────────────────────────────────────────────────┘
```

Two columns via `st.columns([1, 2.4])`; on narrow screens the sidebar collapses to
Streamlit's drawer, and the 2×2 figure falls back to 1 column (media query is
handled by Streamlit, not by us).

## 2. Widget parity table (Qt → Streamlit)

| Desktop (`studio/gui/simple_window.py`) | Web equivalent | Behaviour preserved |
|---|---|---|
| `ed_rates` + `−100/+100` buttons | `st.text_input("500")` + `st.button("−100")/+100` in a row | comma-separated list, bump every rate then re-run, min 1 |
| `sp_d` (1–10 nm, 0.1, autorun after 300 ms) | `st.slider` + `st.number_input` pair (kept in sync) | autorun on change (`on_change`), same guard rails |
| `sp_t0`, `sp_t1` | `st.number_input` ×2 | no autorun; validated order T_start > T_end |
| `sp_b` (5 dec) | `st.number_input(step=0.1, format="%.5f")` | autorun on change |
| `sp_damp` λ | `st.number_input` | damping-conflict warning kept |
| `cb_adv` "Show more parameters" | `st.expander("Show more parameters")` | atoms + "from D" (atoms = sphere from D), cell a/c, μ, γ, dT, P₀ |
| `cb_damp` "λ = α (validated)" / "λ = α/(1+α²)" | `st.selectbox` | rule M2 guard + warning when switched |
| `bt_run` Run ME | `st.button("Run ME", type="primary")` | spinner during run |
| `cb_sg`, `sp_sgw`, `sp_sgp` | checkbox + 2 number inputs | smoothing affects **plot only**; CSV export stays raw |
| `cb_grid` / `cb_par` / `cb_inv` / `cb_dark` | 4 checkboxes | grid, parameter footer inside figure+PNG, x inversion, theme switch |
| `ed_vpath` + Browse/Load/Remove | `st.file_uploader(type="zip")` (+ multi-file mode) + Remove button | path typing impossible in a browser → replaced by upload chip; last upload remembered in `st.session_state` |
| `cb_vparams` Import VAMPIRE settings | checkbox | fills d, T, B, λ, atoms, cell, moment, γ from the run; ME rate stays as typed |
| `lbl_v` source status | `st.caption` + LUT badge in header | deck/mat provenance, seed count, sampling info, LUT SHA-256 registered ✓/✗ |
| `bt_png` / `bt_csv` / `bt_py` | 3 × `st.download_button` | PNG (validated light style, same dpi), CSV raw arrays, standalone `.py` from `code_export.generate_script` |
| (new, small) Record | `st.download_button("Record (.zip)")` | `audit_manager` record dir (record.json, arrays.csv, numbers.txt, figures, checksums.sha256) zipped in memory |
| `lbl_res` result line | `st.code(...)` (selectable, monospace) | identical text to `numbers_lines()` |
| validation panel (Studio tab) | `st.expander` list + summary counts | identical rule ids, severities, messages |
| mismatch card | `st.container` w/ border, auto-shown | same `num(label, mv, vv, unit, tol=1e-6)` comparison |
| tabs Cooling / Psw-m-ms | — | **dropped**: the Psw / m-ms Test tab is desktop-only |
| `theme.py` light/dark + `QSettings` | `.streamlit/config.toml` theme + CSS vars; `st.session_state` (+ optional `st.query_params` for shareable settings URL) | remembers rates, D, T, B, λ, toggles; **new**: settings can be encoded in the URL so a collaborator opens the same run |
| matplotlib canvas (`FigureCanvasQTAgg`) | `st.pyplot(fig)` on the same `Figure` object | same style helpers (`style_dark`, `_style_axes`), same 2×2 panels |

## 3. Two tabs, same content as desktop

* **Cooling Simulator** — everything above.
* **Psw / m-ms Test** — *not implemented in the web version (removed on request)*. Desktop port of `studio/gui/psw_tab.py`: two cards (ME solver /
  VAMPIRE), the TEST QUANTITIES explainer, results table
  (`m/ms` ME vs VAMPIRE median ratio; `Psw = 1 − P_up` vs empirical seed
  fraction), and its own figure. Uses `MESolver.predict` only — no solver changes.
* **Studio audit** (5-step `main_window.py`) is *phase 5, optional*: the web app
  already reuses its validators; a full 5-step rail is only needed if you want the
  extraction/audit workflow in the browser.

## 4. Things the web app must NOT do (guard rails)

1. No writes anywhere except Python `tempfile` for staged uploads; records are
   produced in a temp dir and handed to the browser as a download (no server-side
   record store on the free tier — see J §R7).
2. No new physics, no re-derived constants: anything numeric comes from
   `studio/core`.
3. No `plt.pyplot()` global-state plotting — always pass the `Figure` object
   (headless-safe, thread-safe).
4. Upload size cap enforced in the app (default 50 MB) with a clear message, plus
   a hard 25-seed-per-rate sanity note (J §R5).
