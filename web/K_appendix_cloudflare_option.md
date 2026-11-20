# K — Appendix: the rejected option (static site on Cloudflare)

Record of the v1 plan, kept so the reasoning is not lost. **Not chosen** in
favour of Streamlit (`share.streamlit.io`).

## What it was

A static SPA (Vite + TypeScript, ~no backend) hosted on Cloudflare Pages, with
the physics **rewritten in TypeScript** running in a Web Worker:

* LUT shipped as a binary Float32 blob: 91 × 1001 × 3 values = **1.09 MB**
  (vs 8.3 MB CSV text), brotli-compressed to ~0.3–0.5 MB, immutable static asset,
  SHA-256 verified in the browser against `lut_registry.json`.
* VAMPIRE folder ingest by drag-and-drop (`webkitGetAsEntry`) or ZIP in-browser.
* Charts via uPlot/Chart.js; PNG export from canvas; records zipped client-side.
* Optional thin Pages Function + R2 for shareable record links.
* Alternatives considered: Cloudflare Python Worker (numpy yes, **matplotlib no**),
  Cloudflare Containers/VMs with FastAPI + matplotlib (cost + ops + auth).

## Why it was rejected

1. **Two physics implementations.** ~1 200 lines of numpy/dict code would have to
   be transliterated and kept in sync forever; the JS side has no `erfc`
   (needed by the `r > 1` branch of `_escape_rate`) and libm differences in
   `exp/tanh`, so the "physics frozen" guarantee becomes a parity-test problem
   instead of a structural one.
2. **Figure fidelity.** The validated baseline is a **byte-identical matplotlib
   3.11.1 PNG**. A JS chart library cannot reproduce it; keeping that guarantee
   would have forced a matplotlib server (Option C), i.e. the cost/ops the
   static plan was supposed to avoid.
3. Streamlit keeps `studio/core`, `tests/test_golden.py`,
   `plotting_engine.py`, `audit_manager.py` and `code_export.py` **as they are**.

## What is still worth stealing from it

* **LUT → binary/npz, with a checksum and an "immutable" cache header.** The
  1–2 s CSV parse and the 8.3 MB asset are the same problem on both stacks; the
  npz twin (`tools/make_lut_npz.py`) is in the Streamlit plan because of this.
* **Aggregated sample bundle instead of the raw tree** (few hundred KB) — also in
  the Streamlit plan.
* **A pure-static build remains the fallback** if you ever need the app offline
  on a lab laptop with no GitHub/Streamlit account: `studio/core` is already
  Qt-free, so a FastAPI/Flask + static frontend can be added later without
  touching physics. Not scheduled.
* **Settings-in-URL** sharing idea was carried over.
