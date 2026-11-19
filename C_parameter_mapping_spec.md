# C. Parameter Mapping Specification

Status: **spec for review.** All "source" examples are verbatim from the real files of
`vampire_damp0p05_D4nm` (deck `input`, `FePt_L10_sc_6350.mat`, `log`, output header).

## C.1 Status taxonomy (applied to every row)

- **Extracted (●)** — read directly from a VAMPIRE file; source = file + line.
- **Derived (⚙)** — computed by the app from extracted values; source = formula + inputs.
- **Missing (✕)** — not present anywhere; user must supply (typed + tagged "user input")
  or accept a *declared default* which is then logged as user override. No silent defaults.

## C.2 VAMPIRE → ME mapping table

| ME variable | VAMPIRE source (directive / key) | Example value | Conversion to ME | Status |
|---|---|---|---|---|
| Grain shape | `create:cylinder`, `create:crystal-structure=sc` | cylinder, SC | shape id → volume formula | ● |
| Grain diameter D | `dimensions:particle-size = 40.8 !A` | 40.8 Å | ×1e-10 m; /1e-9 nm = 4.08 nm | ● |
| Grain height h | `dimensions:system-size-z = 100.1 !A` | 100.1 Å | ×1e-10 m | ● |
| Cell a, c | `dimensions:unit-cell-size-x/y/z (!A)` | 2.72 / 3.85 Å | ×1e-10 m; V_cell = a²c | ●→⚙ |
| N atoms | `log`: "Material 1 FePt makes up 100 % of all atoms ( 4602 atoms )" | 4602 | – | ● |
| V (grain volume) | – | – | **derived**: N_atoms × V_cell (primary); cross-check π/4·D²·h (rule G1) | ⚙ |
| Atomic moment μ_S | `material[1]:atomic-spin-moment=3.23 !muB` | 3.23 μ_B | ×μ_B → A·m² | ● |
| M_s0 (sat. scale) | – | – | **derived**: μ_S / V_cell = 1.544e6 A/m | ⚙ |
| Anisotropy K_u | `material[1]:uniaxial-anisotropy-constant=2.63e-22` (no unit comment ⇒ J/atom assumed) | 2.63e-22 J | consistency-check only: K_u vs σ(T)·k_BT barrier — ME does not use K_u directly (χ-based) | ●, check M-AN |
| Easy axis | `material[1]:uniaxial-anisotropy-direction=0,0,1` | z | must match field direction (rule M3b) | ● |
| γ (gyro) | `material[1]:relative-gamma=1.0` | 1.0 | γ = relative × γ_e = 1.76086e11 rad/(s·T) | ●→⚙ |
| Damping | `material[1]:damping-constant=0.05` | 0.05 | λ_ME = f(α): identity if LL damping; λ = α/(1+α²) if Gilbert — **interpretation must be confirmed (rule M2, risk R4)** | ● + ▲ |
| Exchange J_ex | `material[1]:exchange-matrix[1]=6.350e-21` | 6.35e-21 J | not used by ME; recorded (defines T_c of the atomistic system → compare with RF T_c = 643 K, rule M-EX) | ● |
| Applied field B | `sim:applied-field-strength=1.00531 !T` | 1.00531 T | H_app = B/μ0 = 8.003e5 A/m | ●→⚙ |
| Field direction | `sim:applied-field-unit-vector=0,0,1` | z | m_z axis of output columns | ● |
| T_start | `sim:maximum-temperature=800` (K implicit) | 800 K | ME grid top | ● |
| T_end | `sim:minimum-temperature=300` | 300 K | ME grid bottom | ● |
| Cooling law | `sim:cooling-function=linear`, `sim:program=field-cool` | linear | ME dt from linear ramp | ● |
| Cooling time | `sim:cooling-time=1e-09 !s` | 1 ns | R = (T_max−T_min)/t_cool = 500 K/ns (rule T2 cross-check vs dir name `rate_500Kns`) | ●→⚙ |
| ME Δt | – | – | **derived**: Δt = ΔT_grid / R (ΔT_grid = 1 K app default, logged) | ⚙ |
| Time step / equilibration | `sim:time-step=1e-16 !s`, `equilibration-time-steps=200000`, `total-time-steps=1e7`, `time-steps-increment=20000` | – | not ME inputs; used by rule T3 (ΔT sampling = increment × dt ⇒ 2 ps ⇒ ~1 K rows) and output row count check | ● |
| RNG seed | `sim:integrator-random-seed=N`, `seed_N/` dir name | 1 | ensemble bookkeeping only | ● |
| m_s(T), χ∥(T), χ⊥(T) | `model/rf_model_all_targets.pkl` + `feature_scaler.pkl` (RF surrogate trained on VAMPIRE equilibrium data at D = 4 nm) | – | features: (D_nm, T) → (m_s, χ∥, χ⊥); **D fed to RF must equal particle-size/10 (4.08 vs assumed 4.0 — rule M-RF warns if ΔD > 1 %)** | ● (model) |
| T_c | – | 643 K | derived: argmax_T χ∥(T) from RF | ⚙ |
| Ensemble mean/SEM | `output_seed*.dat` of all DONE seeds | 25/50 seeds | mean ± 2·SEM over seeds at each T | ●(files)→⚙ |
| P_rev (VAMPIRE) | final M_z per seed in 300–310 K window | – | fraction with final M_z < −0.7 (defaults; editable, logged) | ⚙ |

## C.3 `output_seed*.dat` column layout (must be reconstructed, never assumed)

Columns follow the **order of the deck's `output:` directives**, with fixed block sizes:

| Directive | Block width | Indices (this deck) | Meaning |
|---|---|---|---|
| `output:real-time` | 1 | 0 | time (s) |
| `output:temperature` | 1 | 1 | T (K) |
| `output:applied-field-strength` | 1 | 2 | B (T) |
| `output:total-energy` | 1 | 3 | E (J) |
| `output:magnetisation` | 3 | 4,5,6 | unit-vector components (x,y,z); signed cosθ_z = col 6 |
| `output:magnetisation-length` | 1 | 7 | normalized mean \|m\| |
| `output:mean-magnetisation-length` | 1 | 8 | mean \|m\| per atom |
| `output:mean-susceptibility` | 1 | 9–13 (extra trailing cols verified against width) | χ |

→ validated convention (README + scripts): **M_z = col7 × col6, T = col1** — the
parser computes the layout from the directives and *refuses to load* unless total
width matches (rule O1). Rows with T ≥ 799.5 K (equilibration) are excluded
(`cool = T < 799.5`), matching the validated scripts; the cutoff is shown in the audit.

## C.4 Unit conversion register (every conversion logged in the audit)

| From | To | Factor | Note |
|---|---|---|---|
| Å (`!A`) | m | 1e-10 | declared via `!A` comment |
| μ_B (`!muB`) | A·m² | 9.2740100783e-24 | |
| T (B) | A/m (H) | 1/μ0, μ0 = 4π×1e-7 | only for H-based formulas |
| K/ns cooling | s⁻¹ step Δt | Δt = ΔT/(R×1e9) | R kept in K/ns in UI, SI in solver |
| ns (`!s` sci-notation) | s | 1e-9 | parsed with SI prefix aware reader |
| anisotropy (no unit) | J/atom assumed | – | flagged `unit:assumed` |

VAMPIRE comment-suffixes (`!A`, `!s`, `!muB`, `!T`) are treated as the authoritative
declared unit; absence of a suffix ⇒ `unit:assumed` ⇒ validator reviews plausibility
(e.g. field must lie in 0–10 T, cell in 1–10 Å).

## C.5 Conflict & missing-parameter handling

- **Conflict** (same parameter, two sources, different values): both listed with
  file+line; higher-precedence source pre-selected but the row stays amber until the
  user picks one; decision stored in the record. Example: deck md5 ≠ decks/ archive ⇒
  "seed deck differs from archived deck — using seed deck".
- **Missing critical** (no field / no damping / no cooling time / RF model absent):
  the field renders as an editable ✕ row; RUN stays disabled until filled; typed
  values are tagged "user input" everywhere (UI + audit + export).
- **Missing optional** (e.g. manifest.tsv absent, log truncated): app proceeds with a
  note; atom count then falls back to counting rows in the simulation's `atom`
  output or to user input.
- **Interpretation-required** (damping α vs λ, RF-D vs deck-D): a dedicated
  confirmation dialog with the physics implication quantified (e.g. recompute ME with
  λ = α/(1+α²): m(300 K) changes by X) before proceeding.
