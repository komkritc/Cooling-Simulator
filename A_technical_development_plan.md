# A. Technical Development Plan — VAMPIRE–ME Comparison Studio

Status: **plan for review — no code written.**

## A.1 Goals and non-goals

Goals
- Reproducible, physically consistent apple-to-apple comparison of VAMPIRE
  atomistic field-cooling runs vs the Roy two-state Master Equation (ME).
- Automatic extraction of every available simulation parameter from the actual
  VAMPIRE files (deck `input`, `*.mat`, `log`, `run_stdout.txt`,
  `output_seed*.dat` header, `manifest.tsv`), each tagged
  **Extracted / Derived / Missing** — never silently hard-coded.
- Consistency audit before any comparison is allowed (critical mismatch ⇒ warning + explicit user confirmation).
- Full audit trail: one *comparison record* per run, capable of exact re-execution.
- Publication-quality plots reproducing (and extending) the validated
  `plot_<rate>Kns_standalone.py` four-panel figure.

Non-goals (v1)
- No modification of any VAMPIRE input; the app is read-only w.r.t. simulation data.
- No new ME physics; the existing Roy formulation in `derived/me_B_roy.py` is the
  reference implementation, refactored but not re-derived.
- No job submission / running VAMPIRE itself.

## A.2 High-level architecture

Three layers with strict one-way dependencies: **GUI → Core services → Physics/Data**
(the GUI can never import the physics layer directly, and physics never imports the GUI).

```
┌─────────────────────────────────────────────────────────────────┐
│ GUI (PySide6)  — widgets only; talks to core via controller API │
├─────────────────────────────────────────────────────────────────┤
│ Application controller (orchestration, worker threads, signals) │
├─────────────────────────────────────────────────────────────────┐
│ Core services (pure python, importable & testable without Qt)   │
│   parser_dk   parser_mat   parser_output   manifest_reader      │
│   extraction_engine   mapping_engine   units                    │
│   consistency_validator                                          │
│   rf_material_interface   me_solver   statistics                 │
│   plotting_engine   audit_manager                                │
└─────────────────────────────────────────────────────────────────┘
        depends only on: numpy, scipy/scikit-learn(pickle), matplotlib
```

## A.3 Module responsibilities

| # | Module | Responsibility | Reuse |
|---|---|---|---|
| 1 | `gui/` (PySide6) | Main window, 5 sections (wireframe B), tables, plot canvas (QtGraph or matplotlib-Qt), dialogs, worker-thread progress | — |
| 2 | `core/vampire_input_parser.py` | Parse deck files (`input`, `*.input`): `create:*`, `dimensions:*`, `sim:*`, `material:file`, `output:*`/`screen:*` directive lists, comment metadata blocks | — |
| 3 | `core/vampire_mat_parser.py` | Parse `.mat`: `material[N]:damping-constant`, `atomic-spin-moment=3.23 !muB`, `uniaxial-anisotropy-constant`, anisotropy direction, `exchange-matrix`, crystal structure, gamma | — |
| 4 | `core/vampire_output_reader.py` | Read `output_seed*.dat`: header provenance (version, githash, path, date), **column layout reconstructed from the deck's `output:` directive order** (block sizes per Table C.3), DONE-marker filtering, seed enumeration | same column conventions as validated scripts |
| 5 | `core/manifest_reader.py` | Optional `manifest.tsv` join (deck md5, mat md5, status, origin path) for provenance | — |
| 6 | `core/extraction_engine.py` | Merge sources per parameter, resolve conflicts (precedence rules §A.5), assign Extracted/Derived/Missing + source citation per value | — |
| 7 | `core/mapping_engine.py` | VAMPIRE → ME parameter map (Table C.2) incl. unit conversions and derived quantities (V_grain, M_s0, H_app, Δt) | — |
| 8 | `core/consistency_validator.py` | Rule set §A.6; severity levels; user-confirmation workflow | — |
| 9 | `core/rf_material.py` | Load `rf_model_all_targets.pkl` + `feature_scaler.pkl`; identify model by SHA-256 + training metadata; expose m_s(T), χ∥(T), χ⊥(T), T_c | `FePtML` class, unchanged |
| 10 | `core/me_solver.py` | Roy ME: σ(T), r(T), α₂(T), ω₁(T)=γ/χ⊥, Γ(T) both branches, P-evolution, M_ME(T) | **direct refactor of validated `me_B_roy.py`** — physics untouched |
| 11 | `core/statistics.py` | Seed ensemble mean, SEM, final-state classification (up/reversed/partly-ordered, ±0.7 thresholds, 300–310 K window), P_rev, transverse share, rmse ME-vs-VAMPIRE | identical definitions to validated scripts |
| 12 | `core/plotting_engine.py` | Figures as data-driven objects (rate/seed selection, multi-rate overlay, multi-diameter overlay, axis ranges, PNG/PDF/SVG export, CSV) | reproduces four-panel figure exactly |
| 13 | `core/audit_manager.py` | Comparison record (JSON + CSV + figures + hashes), re-load and re-execute bit-for-bit | checksums pattern from `checksums.sha256` |

## A.4 Data flow (one comparison)

```
user picks deck/input file + results dir
   → parsers (deck, mat, logs, output header, manifest)
   → extraction_engine  → ParameterTable (value, unit, source, status)
   → mapping_engine     → MEConfig (all ME inputs + derived values + conversions log)
   → consistency_validator → ConsistencyReport (pass / warn / critical)
   → [user confirms if warnings]
   → output_reader loads seeds (DONE only)      ┐  in a QThread worker
   → me_solver.run(MEConfig)                    ┘  (GUI stays responsive)
   → statistics → ComparisonResult (arrays + scalars)
   → plotting_engine (display + export) and audit_manager (record saved)
```

All intermediate objects are immutable dataclasses with a `to_dict()` — that is
what makes a comparison re-executable and diff-able.

## A.5 Parameter extraction strategy

1. **Source precedence** (highest first):
   `run-level deck (seed dir)` > `archived deck (decks/)` > `manifest.tsv` >
   `log / run_stdout.txt` > `output header comments` > user manual entry.
   Any conflict between two sources is never resolved silently: it is shown as
   an amber *conflict* row listing both values and sources.
2. **Unit tags travel with values.** Every parsed number keeps its comment
   suffix (`!A`, `!s`, `!muB`, `!T`) as the declared unit; values without a unit
   comment are flagged `unit:assumed` and reviewed by the validator.
3. **Derived values are computed, never parsed** (grain volume, M_s0, H_app, Δt),
   and the formula + inputs are recorded in the audit.
4. **Unknown directives are kept**, not dropped: an "unrecognised parameters"
   table so nothing is silently lost.
5. **Provenance hash**: deck md5 + mat md5 recorded per comparison (matches the
   existing `manifest.tsv` / `checksums.sha256` convention).

## A.6 Validation rules (run before comparison is enabled)

| Rule | Check | Severity if violated |
|---|---|---|
| G1 | atoms × cell volume vs π/4·D²·h cylinder volume from `dimensions:` | Critical (>2 %) |
| G2 | `particle-size` == `system-size-x` (isolated grain assumption) | Warning |
| M1 | `.mat` moment × mu_B / cell volume == ME `MS_0` derivation | Critical |
| M2 | damping: value read from `.mat` vs ME damping input; flag α-vs-λ interpretation (§E R4) | Critical (confirmation) |
| M3 | `applied-field-strength` (T) == ME B_app; direction along easy axis (0,0,1) | Critical |
| T1 | deck `maximum/minimum-temperature` == T range used for ME grid | Critical |
| T2 | cooling rate from `cooling-time` vs (T_max−T_min) consistent to 1 % | Critical |
| T3 | output T sampling: ΔT ≈ 1 K, monotone during cooling; equilibration rows (T ≥ 799.5) excluded consistently | Warning |
| O1 | column layout from deck `output:` list matches actual data width | Critical |
| R1 | RF model file hash matches the registered surrogate for this material | Critical |
| I1 | initial state: field-cool deck ⇒ ME P₀ = 0.5 assumption recorded | Warning |
| D1 | seeds: all loaded seeds have DONE markers; count reported | Warning |

A *Critical* failure disables `RUN COMPARISON` until the user ticks an explicit
"I accept these deviations" checkbox, which is stored in the audit record.

## A.7 File formats supported (v1)

- Input: VAMPIRE deck `input`/`*.input` (text, `directive=value` + `!unit` comments),
  `*.mat` (`material[N]:key=value`), `manifest.tsv`, `log`, `run_stdout.txt`.
- Results: `output_seed*.dat` (tab-separated, `#` header), `DONE` markers,
  `numbers_*.txt` (legacy comparisons, importable).
- Material surrogates: the two RF pickles + SHA-256 registration.
- Export: PNG/PDF/SVG figures; CSV arrays; JSON comparison records.
