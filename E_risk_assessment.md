# E. Risk Assessment

Status: **risk register for review.** Likelihood × Impact: H/M/L. Mitigations map to
rules in plan A (§A.6) and mechanisms in spec C (§C.5).

## R1 — Ambiguous parameter extraction — **H × H**
Multiple sources give the same parameter with different meanings or values
(deck vs archived deck vs manifest vs log; `particle-size` vs `system-size-x` vs
"4 nm" in file names — note the real deck says D = 40.8 Å = **4.08 nm** while the
dataset and ME use **4.0 nm**).
*Mitigation*: never silent — precedence table + conflict rows (amber) + source viewer;
rule M-RF warns when RF input D differs from deck-derived D by > 1 %; every number
carries file+line provenance. Accepted residual risk: user picks wrong value —
audit makes it traceable after the fact.

## R2 — Missing material information — **M × H**
Decks/materials not archived for some runs (real example: `cooling_T1000_rate10000Kns`
rows in `manifest.tsv` show `MISSING` deck/mat, "alpha=0.05 from output header path").
Inference from paths/names is exactly the silent assumption this app must avoid.
*Mitigation*: such parameters are ✕ Missing with an explicit "inferred" candidate
shown but not applied until confirmed; RUN blocked; record marks provenance as
"inferred, user-confirmed".

## R3 — Unit inconsistencies — **M × H**
VAMPIRE relies on `!unit` comment suffixes; keys without suffixes (anisotropy
constant, susceptibility) can be J vs J/atom, SI vs reduced. A silent Å↔nm error
shifts σ(T) by 10⁶ — catastrophic and non-obvious.
*Mitigation*: unit register C.4; `unit:assumed` flags; plausibility ranges in the
validator; derived cross-checks (M1: moment/cell vs M_s0; G1: atoms×cell vs shape
volume; T3: sampling inferred from time-step × increment). Golden regression catches
regressions of the *validated* pipeline but cannot catch a genuinely new deck with
wrong units — hence hard plausibility checks are mandatory, not optional.

## R4 — Damping interpretation (VAMPIRE `damping-constant` vs ME λ) — **H × M**
The ME uses λ = 0.05 in α₂(T) (Paper 1 Eq. 3). VAMPIRE's damping-constant is a
dimensionless LL/Gilbert-type parameter; depending on convention λ_eff = α or
α/(1+α²). For α = 0.05 the difference is ≈5 % in α₂ — small here, but it grows with α
and matters for other datasets.
*Mitigation*: mandatory interpretation confirmation (rule M2, dialog quantifies the
effect by re-running ME both ways); default kept identical to the validated
`me_B_roy.py` so golden comparisons stay fair.

## R5 — Atomistic vs ME physics mismatch (fairness limits) — **H × M**
Even with identical nominal parameters the models differ physically: ME is a
two-level axial model with RF-fit constitutive functions (themselves fitted at
D = 4.0 nm), ignores transverse/fanned states (panel-D partly-ordered grains at
6000 K/ns are outside ME's state space), treats the field via equilibrium
tanh term, and assumes P₀ = 0.5. The atomistic grain has shape (cylinder h ≠ D),
exchange-defined T_c ≈ but not exactly 643 K, and stochastic transient behaviour.
*Mitigation*: these are **reported, not hidden**: consistency report includes an
"expected model discrepancy" note; plots always show both ensembles with SEM so
rmse is interpreted statistically; UI wording distinguishes "parameter fairness"
(what the app guarantees) from "model adequacy" (what the comparison measures).

## R6 — Column-layout misinterpretation of output files — **M × H**
Different decks emit different `output:` sets; fixed hard-coded indices (col6/col7)
would silently misread a differently configured run (README's old convention says
"col 0 = step" while these decks write time).
*Mitigation*: layout reconstructed from directives + width check (rule O1); loader
refuses on mismatch; chosen mapping printed in audit.

## R7 — RF surrogate validity range — **M × M**
RF pickles trained on VAMPIRE equilibrium data for this alloy/size family.
Applying them to other diameters, materials, or T outside ~300–1000 K is
extrapolation.
*Mitigation*: model registration by SHA-256 + metadata (material, D range, T range);
validator R1 blocks unregistered models; extrapolation warning when deck D or T
leaves the registered range.

## R8 — Reproducibility drift (matplotlib/numpy/sklearn versions) — **M × M**
Byte-identical figure acceptance can fail after environment changes; silent pickle
incompatibility is possible.
*Mitigation*: pinned venv, environment capture inside each comparison record
(library versions + interpreter), acceptance criterion relaxed to "identical numbers"
with figure-diff report if the environment differs.

## R9 — GUI blocking on large datasets — **L × M**
50 seeds × 6 rates is fine, but future datasets (10⁴ seeds) could freeze the UI.
*Mitigation*: all IO/solve in worker threads from Phase 5; lazy per-seed loading;
counts and progress always displayed.

## R10 — Scope creep (multi-diameter, multi-material ME) — **M × L**
v1 accepts only what the validated ME supports (single-grain, axial, FePt RF model).
*Mitigation*: roadmap defers multi-material; UI shows "not supported by current ME
model" rather than half-supported mappings.
