# F — Web architecture plan (Streamlit)

## 1. Why Streamlit is a different (and cheaper) problem than the Cloudflare plan

Verified facts about the current code:

* `studio/core/` contains **no Qt imports at all** — it is already a library:
  parsers, extraction, mapping, the frozen Roy ME solver (`me_solver.py`),
  the LUT surrogate (`lut_material.py`), stats, the 13-rule validator,
  `session.py` orchestration, `audit_manager.py` records, `code_export.py`,
  `plotting_engine.py` (matplotlib).
* Everything the desktop app draws is produced by matplotlib figures
  (`Figure` + `FigureCanvasQTAgg`), and the validated baseline requires
  `matplotlib==3.11.1` to be **byte-identical**.
* A full ME run is ~500 scalar iterations per rate → tens of milliseconds.
  No async/server compute needed.
* The LUT is one CSV, 91 × 1001 grid, 8.3 MB text; `np.genfromtxt` on it takes
  ~1–2 s, so it must be parsed once per process, not per interaction.

⇒ On Streamlit we keep **one physics implementation**. The web port is purely a
**UI translation layer**: Qt widgets → `st.*` widgets, `QThread` → Streamlit
re-run, `QSettings` → `st.session_state`, `QFileDialog` → `st.file_uploader`.

## 2. Reuse / change matrix

| Existing file | Web app treatment | Why |
|---|---|---|
| `studio/core/me_solver.py` | **import unchanged** | physics frozen |
| `studio/core/lut_material.py` | import + **small addition**: accept an in-memory path/npz (or just pre-parse with `st.cache_resource`) | the file lookup uses `__file__`-relative dirs; works on Cloud, but the slow CSV parse must be cached |
| `studio/core/mapping_engine.py`, `statistics.py`, `units.py`, `types.py` | unchanged | pure logic |
| `studio/core/vampire_*_parser.py`, `manifest_reader.py`, `extraction_engine.py`, `consistency_validator.py` | unchanged, but the *source* of files changes (uploaded ZIP/dir instead of disk) | they take paths → we stage uploads into a temp dir |
| `studio/core/session.py` | unchanged (it takes `run_dir`; we point it at the staged temp dir) | `run_dir`-based, so no rewrite |
| `studio/core/audit_manager.py` | unchanged → returns a record dir; web zips it for download | record format preserved |
| `studio/core/code_export.py` | unchanged → `st.download_button` of the generated `.py` | reproducibility export keeps working |
| `studio/core/plotting_engine.py` | unchanged + **one new tiny helper** returning the `Figure` (not just saving) so `st.pyplot(fig)` can render it | avoids a second plotting path |
| `studio/gui/*` (PySide6) | **not used** by the web app | desktop only |
| `tests/test_golden.py`, `baselines/golden.json` | unchanged; extended with a web-path test (§6) | acceptance contract |
| `requirements.txt` (PySide6 pinned) | **not used by the web app** → separate `web/requirements.txt` | see H §3 (PySide6 must not be installed on Cloud) |

`plotting_engine.py` currently exposes `create_figure(res, rate, panels=…, …)`,
`overlay_figure(...)`, `style_dark(fig)`, `save(fig, path)`. That is already the
right shape for Streamlit: build the figure, show it, and optionally save it.

## 3. Web app structure (new files only)

```
web/
  streamlit_app.py          entry point (must be at repo root or configured)
  webapp/
    __init__.py
    state.py                session_state schema + defaults + migration
    layout.py               header, tabs, columns, CSS/theme (light+dark)
    controls.py             the parameter form (every Qt control → st widget)
    panels.py               result line, validation accordion, mismatch card
    figures.py              st.pyplot wrappers, grid/params/invert toggles
    uploads.py              VAMPIRE run folder upload (ZIP / multi-file) -> temp dir
    exports.py              PNG / CSV / .py / record .zip download buttons
    data_cache.py           LUT loading (st.cache_resource) + LUT badge + sample data
  .streamlit/config.toml    theme, headless, browser settings
  requirements.txt          streamlit + numpy==2.5.5 + matplotlib==3.11.1  (no PySide6)
  tools/
    make_lut_npz.py         CSV -> npz (~1.1 MB, loaded in ~10 ms)
    make_sample_bundle.py   VAMPIRE tree -> tiny per-rate sample (for the demo)
  tests/
    test_web_golden.py      golden numbers through the Streamlit code path
    test_parity_web_desktop.py  same config -> same numbers.txt in both paths
```

Key rule: **`webapp/` contains no physics** — only widgets, state and glue.
Physics lives only in `studio/core/`, exactly as now.

## 4. State and data flow

```
st.session_state["settings"]   rates[], d_nm, t0, t1, B, damp, advanced{atoms,a,c,mu,gamma,dT,p0,damp_use},
                               sg_on/sg_win/sg_poly, grid, params_on_plot, dark, invert_x,
                               import_vampire, last_upload_name
st.session_state["session"]    AnalysisSession for the uploaded run (cached by upload id)
st.session_state["results"]    [(rate, ComparisonResult|ME-only result)]
st.session_state["plot_key"]   which rates/panels to draw
```

Run flow (identical to the desktop app's `run_me`):

```
settings changed → st.button / auto-rerun (debounce not needed; Streamlit reruns per widget)
  → for each rate: AnalysisSession.run_comparison()  or  MESolver.predict() (no-VAMPIRE path)
  → results cached in session_state keyed by (settings hash)
  → figures rebuilt with plotting_engine.create_figure()
```

Desktop→web behavioural differences to keep intentional (they are features, not bugs):
the 300 ms debounce on diameter/field autorun becomes "Run" on the next rerun
(optionally `on_change` rerun for the same feel); `QThread` background runs are
unnamed because a run is ~50 ms and Streamlit shows a spinner.

## 5. LUT and VAMPIRE data on the web

* **LUT**: keep the CSV as the canonical file, add `data/lut_current_rf.npz`
  (D[], T[], table[3,nD,nT] float64, ~2.2 MB, or float32 ~1.1 MB) generated by
  `tools/make_lut_npz.py` with an assertion that it round-trips to the CSV's
  SHA-256 registration entry. Loaded once with `st.cache_resource` (≈10 ms vs
  1–2 s CSV). The UI shows the same "registered ✓" badge from `lut_info()`.
  Repo weight: 8.3 MB CSV + 1.1 MB npz — acceptable for a public repo (GitHub
  limit is 100 MB/file); the npz is the only new artifact.
* **VAMPIRE data**: `st.file_uploader` cannot pick a directory. Two supported
  paths:
  1. **ZIP upload** (recommended): user zips `runs/rate_500Kns/`; the app
     unzips to `tempdir`, then `AnalysisSession(tempdir/run_dir)` — file layout
     identical to disk, so every parser/validator works unchanged.
  2. **Multi-file upload** (`accept_multiple_files=True`): the app
     reconstructs `input`, `*.mat`, `output_seed*.dat`, `log`, `manifest.tsv`
     from filenames. More clicks, but works when the user can't zip.
* **Sample dataset** so the public app is immediately demo-able: bundle either
  (a) the 6 run folders as a small ZIP (~2–3 MB, 25 seeds each — needs your OK
  on redistribution), or (b) `tools/make_sample_bundle.py` output: per-rate
  aggregated arrays + seed summaries (a few hundred KB, no raw output files).
  Recommended: (b) by default, (a) behind a "raw sample" toggle in the repo.

## 6. Testing / acceptance (what "OK to deploy" means)

1. `tests/test_golden.py` — unchanged desktop gate, must stay PASS (6/6 rates).
2. `web/tests/test_web_golden.py` — builds the same configs through the web
   code path (uploads staging + `AnalysisSession`) and asserts the
   `numbers_lines()` output is **line-identical** to `baselines/golden.json`.
3. `web/tests/test_parity_web_desktop.py` — for a parameter sweep (d = 2…8 nm,
   B = 0…2 T, rates 200–6000), the web path and the desktop path produce the same
   numbers and the same figure arrays (`np.array_equal` on the plotted series).
4. Figure parity: exported PNG from the web path vs desktop path for rate 500 →
   byte-compare (works because both use matplotlib 3.11.1 and the same
   `plotting_engine`), with metadata-chunk tolerance.
5. Headless smoke test: `streamlit run web/streamlit_app.py` under
   `PYTHONHASHSEED=0` + `AppTest` (Streamlit's own headless test runner) →
   assert no exception, LUT badge green, result line non-empty.
6. Memory check: parse a 25-seed rate folder and run 6 rates, peak RSS printed
   (target < 400 MB, Cloud free limit is 1 GB → see risk R2).

## 7. Deployment shape (details in H)

* App is deployed by Streamlit Community Cloud from a **public GitHub repo**,
  branch + entrypoint configured in the dashboard; the entry file must be
  importable as `streamlit_app.py` at the deployed root (or a subfolder chosen in
  the dashboard).
* The repo layout decision (single repo with `app/` + `web/` vs a slim public
  mirror that *vendors* `studio/core`) is the main open decision — H §2.
* Idle free-tier apps **sleep**; first load after sleep takes ~10–30 s
  (interpreter + imports + LUT npz). Mitigations in H §5.

## 8. Appendix: why the Cloudflare/static option was dropped

See `K_appendix_cloudflare_option.md` (kept as a record): a static SPA would need
a TypeScript transliteration of the solver **and** a hand-written chart
replacement for matplotlib, which would break the byte-identical figure baseline
and create a second physics implementation to keep in sync. Streamlit trades
deployment flexibility for exactly the two things you care about: one physics
codebase and identical figures.
