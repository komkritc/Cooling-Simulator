# I — Roadmap (phases, acceptance gates, effort)

Effort is in "focused hours" of my work; each phase ends with something you can
open and click, and **nothing is deployed until phase 4 is green**.

| Phase | Deliverable | Acceptance gate | Est. |
|---|---|---|---|
| **0. Decisions + skeleton** | your answers to §8 (public-mirror vs private vs self-host, feature scope, sample data); `web/` folder with `streamlit_app.py`, `requirements.txt`, `config.toml`, separate `web/.venv` | `streamlit run web/streamlit_app.py` opens locally, shows header + LUT badge "registered ✓" + empty 2×2 figure | 2 h |
| **1. Physics path (no VAMPIRE)** | sidebar form with every control from G §2; ME-only run for one or many rates; `st.pyplot` of `plotting_engine.create_figure`; result line; PNG/CSV/`.py` downloads | `web/tests/test_parity_web_desktop.py`: same config → identical `numbers.txt` and identical plotted arrays vs the desktop path, for a 40-point parameter sweep | 6 h |
| **2. VAMPIRE path** | ZIP/multi-file upload → temp dir → `AnalysisSession`; seed count/sampling caption; validation accordion (8 pass/5 warn/0 critical); mismatch card; overlay of multiple rates | upload of the 6 golden run folders reproduces `baselines/golden.json` **line-for-line** through the web path (`test_web_golden.py`); 0 critical | 8 h |
| **3. Records** | ~~Psw / m-ms test tab~~ (dropped from the web app on request; desktop only); "Record (.zip)" download (`audit_manager` record: record.json, arrays.csv, numbers.txt, figures, checksums.sha256); "re-open a record and re-run gives identical numbers" in-browser | record round-trip: download → re-upload → identical numbers + checksums verified | 5 h |
| **4. Deploy (after your OK on H §2)** | mirror repo + `tools/sync_from_local.sh` + `VENDORED.sha256`; `make_lut_npz.py` + `make_sample_bundle.py`; GitHub Actions CI (pytest); share.streamlit.io app | CI green (golden + vendored hash + parity); public URL loads in < 30 s cold, < 3 s warm; RAM peak printed < 400 MB | 5 h |
| **5. Optional extras** | Studio 5-step audit UI; settings-in-URL sharing (`?cfg=...`); dark theme figure parity; PDF report; per-rate table view; unit tests for parsers with fixtures | each behind its own test; none may touch `studio/core` | 4 h each |

Sequence note: phase 2 is where an actual bug can appear (file staging on a
read-only filesystem, temp dir cleanup, zip-slip safety when unzipping user
uploads — we resolve paths and refuse entries containing `..` or absolute
paths). Phases 0–1 carry essentially zero physics risk because they call
`MESolver` directly.

Total to a working public demo (phases 0–4): **≈26 focused hours**, of which
phase 4's external steps (GitHub repo creation, Streamlit dashboard sign-in)
need you for ~10 minutes.

## Suggested commit/branch plan (local git stays local)

```
branch web-port
  commit 1  web/: skeleton + requirements + config (phase 0)
  commit 2  web/: controls + ME-only path (phase 1)
  commit 3  web/: uploads + validation + mismatch (phase 2)
  commit 4  web/: records (phase 3; psw tab dropped)
  commit 5  web/: mirror tooling + CI (phase 4)
```
No file under `studio/` or `tests/` is modified, so `git diff master -- studio/`
stays empty and the desktop golden test remains meaningful.
