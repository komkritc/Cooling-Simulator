# D. Implementation Roadmap

Status: **roadmap for review — nothing started.** Estimates are working days for
one developer; each phase ends in a reviewable, tested state.

## Phase 0 — Freeze & baseline (0.5 d)
- Snapshot validated references: `me_B_roy.py`, the six `plot_<rate>Kns_standalone.py`,
  and all current `mz_*.png` / `numbers_*.txt` (already byte-reproducible).
- Record SHA-256 of RF pickles, decks, mat files; store as the golden baseline file.
- Deliverable: `baselines/golden.json` (expected numbers per rate: e.g. 500 K/ns →
  ME m(300 K) = 0.774, P_rev = 0.005, rmse = 0.0164; VAMPIRE +0.7874 ± 0.0005, 25/0/0 …).

## Phase 1 — Core parsers + extraction engine (4–5 d)
- Deck parser (`directive=value #comment`, `!unit` suffixes), `.mat` parser,
  output-header/log/manifest readers, column-layout reconstruction from `output:`
  directives, DONE-marker seed enumeration.
- `ParameterTable` dataclass (value, declared unit, status, source file+line).
- Tests: parse all 6 rates + archived decks; every extracted value compared against
  the hand-verified table in spec C; malformed/unknown directives must land in the
  "unrecognised" table, never vanish.

## Phase 2 — Mapping + validation (3–4 d)
- `mapping_engine` implementing table C.2, unit register C.4, derived-quantity formulas.
- `consistency_validator` rules G1…D1 with severities; acceptance workflow API.
- Tests: golden comparisons pass 12/12 (M2 amber by design); deliberately corrupted
  decks (wrong field, unit swap Å↔nm, missing cooling-time) must each trigger the
  intended rule — unit-test matrix of ~20 mutations.

## Phase 3 — ME core refactor (2 d, physics frozen)
- Turn `me_B_roy.py` into `core/me_solver.py` taking an explicit `MEConfig`
  (no module-level constants); RF interface to `rf_material.py`.
- **Acceptance: every golden number reproduced to 1e-12** for all 6 rates; no
  formula line changed without a physics-review note.

## Phase 4 — Statistics + plotting engine (3–4 d)
- `statistics.py`: mean/SEM, seed classification, transverse share, rmse —
  same definitions as validated scripts.
- `plotting_engine`: reproduce the four-panel figure; **acceptance: PNG
  byte-identical to current `mz_<rate>.png`** with default settings; then add
  options (seed toggles, multi-rate overlay, multi-diameter, ranges, PDF/SVG, CSV).

## Phase 5 — GUI (PySide6) (6–8 d)
- Main window sections 1–5 per wireframe B; worker QThread for parse/ME/plot with
  progress + cancel; tables with status chips; source viewer; dialogs; results tabs.
- No business logic in widgets; GUI tested by controller-level integration tests.

## Phase 6 — Audit manager + reproducibility (2–3 d)
- `cmp_<timestamp>/` record: JSON (parameters, mapping, validator report, hashes,
  settings), CSV arrays, figures, `checksums.sha256`.
- Re-open record → [Re-run] → **acceptance: byte-identical figure and numbers**.

## Phase 7 — Hardening & usability (3 d)
- Drag-and-drop, recent sessions, error surfacing (no silent exceptions),
  logging, packaging (pyproject + venv, PySide6 pin), user manual, demo session on
  the `vampire_damp0p05_D4nm` dataset.

## Testing strategy (continuous)
1. **Golden regression** (Phases 1–4, 6): numbers and byte-identical PNGs vs Phase-0
   baseline — this is the core fairness guarantee.
2. **Mutation tests** (Phase 2): corrupted decks/units must fire specific rules.
3. **Property tests**: volume cross-check G1 within 2 % on all grains; column-width
   match O1 on every loaded file; ME Γ(T) ≥ 1e-40 and P ∈ [0,1] invariants.
4. **GUI tests**: controller-level headless (pytest-qt) — file pick → tables fill →
   RUN disabled/enabled transitions correct.
5. **Manual acceptance script**: fresh user performs the §B.8 workflow unaided.

## Global acceptance criteria
- A–E of this planning package implemented, or gap explicitly waived in writing.
- All 6 existing rates reproducible from the GUI to byte-identical outputs.
- Zero hard-coded physical parameters inside the app (all Extracted/Derived/
  user-input with provenance).
- Critical inconsistency always blocks RUN until acknowledged; acknowledgment is
  stored in the record.
- An exported record re-executes to identical results on a clean machine (venv + data).
