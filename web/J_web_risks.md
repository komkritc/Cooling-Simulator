# J — Risk assessment (Streamlit web port)

Severity: **H** could break physics/results trust, **M** degrades usability, **L** annoyance.

| ID | Risk | Sev | Mitigation |
|---|---|---|---|
| R1 | **Everything in the deployed repo is public** (code + LUT + baselines). Conflicts with your "local only" preference | H | Slim mirror repo (H §2a) containing only core + LUT + tests; no raw VAMPIRE data, no planning docs, no `studio/gui`. Alternatives: paid private app, or self-host on the lab server (H §2d) |
| R2 | **1 GB RAM / 1 CPU** on free Community Cloud; a 25-seed folder + 6 rates + matplotlib could approach it | H | LUT loaded from npz float32 (~1.1 MB) not 8.3 MB CSV text; never parse `run_stdout.txt`; per-session result cache; cap rates to 6; phase-4 gate prints peak RSS; if needed, downsample plotted arrays for display only (exports stay full) |
| R3 | **No authentication** — a public URL anyone can hit (compute + sample data) | M | Link discipline (unlisted URL); optional passphrase gate from `st.secrets` (deters, does not protect); rate-limit expensive actions; if real access control is needed → self-host with nginx auth |
| R4 | **No persistent storage**: saved records / audit records cannot live on the server (disk is ephemeral and wiped on redeploy) | M | Records are built in a temp dir and handed to the browser as a ZIP; the "re-run from record" check happens client-side after re-upload — identical guarantee to the desktop app |
| R5 | **Browsers cannot pick a directory**; `st.file_uploader` is per-file/ZIP | M | ZIP upload as the primary path (folder structure preserved → all parsers work unchanged) + multi-file fallback + a "sample run" button so the physics can be demoed without any upload |
| R6 | **Cold start / idle sleep** (free tier): 10–30 s for the first visitor, and your session state is lost when the app restarts | M | Lazy imports, `st.cache_resource` for the LUT npz, tiny module import graph; settings optionally encoded in the URL so a session is restorable; "warm-up" pinger only if it genuinely bothers you |
| R7 | **Vendored copy of `studio/core` in the public mirror can drift** → two physics implementations (exactly what this plan was meant to avoid) | H | `tools/sync_from_local.sh` is the only way the mirror gets core files; `VENDORED.sha256` + `test_vendored_hash.py` fail CI on any manual edit; golden test runs in CI on both sides |
| R8 | **matplotlib version drift** on the server (pip resolving a different matplotlib → PNG/pixel baseline changes) | H | `web/requirements.txt` pins `matplotlib==3.11.1` + `numpy==2.5.5` (same as desktop); CI compares an exported figure PNG against `baselines/` (pixel-exact, metadata-tolerant) |
| R9 | **Streamlit API churn** (minor releases change widget/rerun/`file_uploader` behaviour and can break a deployed app without a code change) | M | Pin `streamlit==<exact>`; Dependabot disabled for it; a scheduled CI job runs the golden+parity suite against the pinned version, and upgrades happen only after that job is green |
| R10 | **Shared venv pollution**: `app/.venv` is a symlink to `Cooling_Model_Comparison/cooling_simulator/.venv`; installing Streamlit there would break the other project's pinned env | M | Separate `web/.venv`; never `pip install` into the shared venv; documented in `web/README.md` |
| R11 | **Figure fidelity in the browser**: `st.pyplot` ships a rasterised PNG at Streamlit's own scale; a reader may download a lower-resolution image than your paper figure | M | The on-screen figure is for interaction; "Download PNG" re-renders with the validated light style and explicit `dpi` through `plotting_engine.save` — same code path as the desktop, so the file is the validated one |
| R12 | **Upload safety / zip-slip**: unzipping a user ZIP could write outside the temp dir | M | Reject absolute paths and `..` entries, resolve and verify the prefix, cap entry count/size, delete the temp dir in a `finally` (uploads never touch the local data tree) |
| R13 | **Public sample data redistribution**: bundling the 25-seed VAMPIRE folders puts raw simulation output on a public repo | M | Default = aggregated sample bundle (arrays + seed summaries, no raw decks/outputs); raw sample only if you confirm distribution rights |
| R14 | **Version reporting breaks on Cloud** (`studio/version.py` shells out to `git tag`, no `.git` there) | L | Ship a `web/VERSION` file or `ME_VERSION` secret; the header prints it next to the core SHA-256 |
| R15 | **Anyone can drive the app into a corner** (huge rate lists, absurd parameters, LUT range errors) | L | Input bounds exactly as the desktop spinboxes (1–10 nm, 0–1000 K, ≤6 rates), `st.error` reusing the core's own `ValueError` messages (no silent extrapolation), max 100 rates |
| R16 | **Reproducibility of a web-produced figure** (a reviewer asks "which code?") | M | Header/About shows app version + `sha256(studio/core)` + LUT SHA-256; every exported PNG is accompanied by the CSV + generated standalone `.py` + record ZIP |
| R17 | **Concurrent users** share one process; a burst of 6-rate sweeps could make the UI lag for everyone | L | Per-session result caching keyed by settings hash; runs are ~50 ms; if it ever matters, that's the signal to move to self-host (H §2d) |

## Things this plan does **not** risk

* The physics (`me_solver.py`, `lut_material.py`, mapping, validators) is not
  touched — no transliteration, no re-implementation, no unit re-derivation.
* The six validated numbers stay the acceptance gate, and now they run in CI on
  every push.
* The desktop Qt app keeps working; the web app is additive (`web/` only).
* Raw simulation data on disk is never read or written by the web app; the only
  inputs are user uploads and the bundled sample.
