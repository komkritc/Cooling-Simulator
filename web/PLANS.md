# Web port — planning package v2 (Streamlit)

Kept as history. The app described here is now **implemented**; see
`README.md` for what exists and how to run it.

v1 of this plan targeted Cloudflare (TypeScript rewrite). **Superseded**: we
target **Streamlit Community Cloud** (`https://share.streamlit.io/`), because the
app is already Python + matplotlib and `studio/core` is Qt-free — so the web
version reuses the **validated physics code as-is** instead of a second
implementation. Consequences (good and bad) are in `H_streamlit_deploy_plan.md`.

| File | Content |
|---|---|
| `F_web_architecture_plan.md` | What is reused untouched, Qt→Streamlit translation layer, module map, LUT/data/performance plan, session-state design, upload strategy |
| `G_web_gui_wireframe.md` | Page layout, exact widget-by-widget parity table (Qt → `st.*`), tabs, plot handling, exports |
| `H_streamlit_deploy_plan.md` | Repo/mirror layout (what gets published), `.streamlit/config.toml`, pinned requirements, limits (RAM/CPU/idle sleep), VAMPIRE data handling, secrets, custom domain, rollback |
| `I_web_roadmap.md` | Phases 0–5, deliverables, acceptance gates, effort estimates |
| `J_web_risks.md` | Risks: public repo, 1 GB RAM, idle cold start, no folder upload, figure size/agg backend, concurrent users, record persistence |
| `K_appendix_cloudflare_option.md` | Why the Cloudflare Workers option was rejected |

Hard rules carried over from the desktop project (unchanged, and honoured by the
implementation):

1. **Physics is reused, not rewritten.** `studio/core/*` is imported by the
   Streamlit app **without modification**. No second implementation, no port.
2. **`tests/test_golden.py` remains the acceptance gate** for the web app too —
   the same six rates must reproduce `baselines/golden.json` line-for-line from
   inside the Streamlit code path (see `web/tests/test_web_parity.py`).
3. **The LUT is data, not code**: same CSV, same SHA-256 registration, no
   extrapolation outside 1–10 nm / 0–1000 K.
4. **Simulation inputs are never modified.** The web app only reads files the
   user uploads or sample data bundled in the repo.
5. The desktop Qt app (`app.py`, `studio/gui/`) stays working and untouched; the
   web entry point is a new file (`web/streamlit_app.py`).
6. `matplotlib==3.11.1` stays pinned so exported PNGs remain the validated,
   byte-identical figures. **This is the main advantage over the Cloudflare plan.**

Scope change made during implementation: the **Psw / m-ms Test tab is not in
the web app** (removed on request; it remains in the desktop app). The wireframe
below still shows it for reference.

The one decision that still blocks deployment: Streamlit Community Cloud deploys
from a **public GitHub repository**, and you asked for local-only git. Options
(public mirror / paid private / self-hosted) are in `README.md` §F and
`H_streamlit_deploy_plan.md` §2.
