# B. GUI Wireframe — VAMPIRE–ME Comparison Studio

Status: **design for review — no code written.** Toolkit: PySide6, desktop.
One main window + modal dialogs. Left: stacked workflow sections. Right dock:
status/audit summary, always visible.

## B.1 Main window (overall)

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│ ⚗ VAMPIRE – MASTER EQUATION COMPARISON STUDIO            [Open record…] [Settings] │
│   Atomistic simulation vs Two-state Master Equation                                │
├──────────────────────────────────────────────────────┬─────────────────────────────┤
│  WORKFLOW (scrollable sections 1→5)                  │  STATUS DOCK (always shown) │
│                                                      │                             │
│  ▼ 1 INPUT FILES                                     │  Session: 4 nm FePt, α0.05 │
│  ▼ 2 EXTRACTED VAMPIRE PARAMETERS                    │  Validation: ● PASS (11/12) │
│  ▼ 3 MASTER EQUATION CONFIGURATION                   │             ▲ 1 warning (M2)│
│  ▼ 4 COMPARISON SETTINGS                             │  Seeds loaded: 25/25 DONE   │
│  ▶ 5 RESULTS (disabled until RUN)                    │  ME runtime: 0.4 s          │
│                                                      │  Record: cmp_2026-11-19_01  │
│                                                      │  [Export record…]           │
└──────────────────────────────────────────────────────┴─────────────────────────────┘
Legend for status chips everywhere:
  ● green = Extracted (read from file, source shown)     ⚙ blue = Derived (formula shown)
  ▲ amber = Conflict / assumed unit / needs confirmation  ✕ red = Missing (blocks RUN)
```

## B.2 Section 1 — Input files

```
▼ 1. INPUT FILES
  VAMPIRE configuration (deck)      [ …/rate_500Kns/seed_1/input            ] [Browse…]
      ↳ deck detected: auto-generated field-cool deck, case D4nm_500Kns_T800   ●
  Material file                     [ …/seed_1/FePt_L10_sc_6350.mat          ] ● auto-found
      ↳ referenced by deck: material:file=FePt_L10_sc_6350.mat; md5 61fe0682…  ●
  VAMPIRE results directory         [ …/cooling_T800/runs/rate_500Kns        ] [Browse…]
      ↳ 25 seed dirs, 25 DONE markers, 0 incomplete                          ●
  Run log / stdout                  [ log            ] [ run_stdout.txt     ] ● (version 7.0.0)
  manifest.tsv                      [ auto-detected at data root             ] ● (provenance join)
  RF material model                 [ model/rf_model_all_targets.pkl         ] ● SHA-256 registered
      ↳ surrogate m_s(T), χ∥(T), χ⊥(T), T_c = 643 K (trained on VAMPIRE equilibrium data)
  [ Re-scan ]                        Overall file status: ● COMPLETE
```

Rules: changing any input file invalidates sections 2–5 (greyed + "stale" badge).
A "Use archived deck from decks/" suggestion appears if the seed-dir deck and
archived deck md5 differ.

## B.3 Section 2 — Extracted VAMPIRE parameters (table, sortable, source-traceable)

```
▼ 2. EXTRACTED VAMPIRE PARAMETERS                     [Verify extracted parameters]
┌────────────────────────┬──────────────┬─────────┬──────────────┬───────────────────┐
│ Parameter              │ Value        │ Status  │ Unit         │ Source            │
├────────────────────────┼──────────────┼─────────┼──────────────┼───────────────────┤
│ Grain shape/size       │ cylinder     │ ●       │ –            │ deck: create:cyl… │
│ Diameter D             │ 40.8 Å       │ ●       │ Å (declared) │ deck: particle-s… │
│ Height h               │ 100.1 Å      │ ●       │ Å (declared) │ deck: system-siz… │
│ Unit cell a, c         │ 2.72/3.85 Å  │ ●       │ Å (declared) │ deck: unit-cell…  │
│ Crystal structure      │ simple cubic │ ●       │ –            │ deck+mat          │
│ Number of atoms        │ 4602         │ ●       │ –            │ log ("4602 atoms")│
│ Atomic moment          │ 3.23 μB      │ ●       │ μB (declared)│ mat: atomic-spin… │
│ Anisotropy K_u         │ 2.63e-22 J   │ ●       │ J (assumed)  │ mat: uniaxial-an… │
│ Easy axis              │ (0,0,1)      │ ●       │ –            │ mat               │
│ Exchange J_ex          │ 6.35e-21 J   │ ●       │ J (assumed)  │ mat: exchange-m…  │
│ Damping                │ 0.05         │ ▲ M2    │ dimensionless│ mat: damping-con… │
│ Applied field B        │ 1.00531 T    │ ●       │ T (declared) │ deck: applied-fi… │
│ Field direction        │ (0,0,1)      │ ●       │ –            │ deck              │
│ T_start / T_end        │ 800 / 300 K  │ ●       │ K            │ deck: maximum/…   │
│ Cooling time           │ 1.0 ns       │ ●       │ s (declared) │ deck: cooling-t…  │
│ Cooling rate           │ 500 K/ns     │ ⚙       │ K/ns         │ derived from time │
│ Integrator / steps     │ llg-heun, 1e-16 s dt, 200 000 equil, 1e7 total ● │ s │ deck │
│ RNG seed               │ 1 (per seed dir) │ ●   │ –            │ deck / dir name   │
│ Output columns         │ 14 cols, layout reconstructed from deck output:* │ ● │ deck │
│ Vampire version/hash   │ 7.0.0 / 525bc27 │ ●    │ –            │ log header        │
└────────────────────────┴──────────────┴─────────┴──────────────┴───────────────────┘
 [Verify extracted parameters] → runs rules G1,G2,O1,T3; issues appear inline as row badges
 Unrecognised VAMPIRE directives (kept, not used):  [expandable table — never hidden]
```

Clicking any row opens a **source viewer**: exact file path + line (e.g. deck line 34
`sim:cooling-time=1e-09 !s`) so nothing is a black box.

## B.4 Section 3 — ME configuration (auto-mapped, editable-with-audit)

```
▼ 3. MASTER EQUATION CONFIGURATION
  ME formulation: [Roy two-state ME ▼]     ω₁(T)=γ/χ⊥(T), (1−H/H_K)² barrier, both r-branches
  Source of implementation: derived/me_B_roy.py  (validated, refactored unchanged)  ●

┌──────────────────────────┬─────────────────┬──────┬────────────────────────────────┐
│ ME variable              │ Value           │ St.  │ Mapping rule (click = show)    │
├──────────────────────────┼─────────────────┼──────┼────────────────────────────────┤
│ V_grain                  │ 1.462e-25 m³    │ ⚙    │ atoms × a²c (deck cell sizes)  │
│ M_s0 scale (μ0)          │ μ_S/V_cell      │ ⚙    │ 3.23 μB / (2.72²·3.85 Å³)      │
│ m_s(T), χ∥(T), χ⊥(T)     │ RF surrogate    │ ●    │ rf_model_all_targets.pkl       │
│ T_c                      │ 643 K           │ ⚙    │ argmax χ∥(T) from RF           │
│ λ (ME damping)           │ 0.05            │ ▲ M2 │ from mat damping-constant —    │
│                          │                 │      │ α vs λ interpretation confirm? │
│ B_app / H_app            │ 1.00531 T /     │ ⚙    │ deck field; H = B/μ0           │
│                          │ 8.00e5 A/m      │      │                                │
│ R (cooling rate)         │ 500 K/ns        │ ⚙    │ deck cooling-time              │
│ ΔT grid / Δt             │ 1 K / 2.0 ps    │ ⚙    │ Δt = ΔT/R                      │
│ P₀ initial               │ 0.5             │ ⚙    │ I1: field-cool assumption      │
│ γ                        │ 1.76086e11      │ ●    │ γ_e; mat relative-gamma = 1.0  │
└──────────────────────────┴─────────────────┴──────┴────────────────────────────────┘
 [View ME equations] → modal with the exact formula set (σ, r, α₂, ω₁, Γ branches,
                       P recursion, M_ME) + where each input comes from
 [Validate parameter consistency] → rules M1–M3, T1–T2, R1, I1 → report panel:
      ✓ 11 pass   ▲ M2 damping interpretation (confirm below)   ✕ 0 blocking
      [ ] I have reviewed and accept the 1 warning   (must tick to enable RUN)
```

Edit policy: any editable field, when changed, turns ● → ✎ "user override" and is
logged in the audit with old→new and reason. The original VAMPIRE value is never
touched.

## B.5 Section 4 — Comparison settings

```
▼ 4. COMPARISON SETTINGS
  Cooling rate:        (●) 500 K/ns   ( ) 200   ( ) 1000   ( ) 1500   ( ) 2000   ( ) 6000
      ↳ rates auto-listed from results dir (and any extra dir added in §1)
  Seed selection:      [25/25 DONE selected]  [Select seeds…] (checkbox tree)
  Overlay:             [ ] add second rate (picker)   [ ] add grain-diameter series
  Display:             [✓] VAMPIRE ensemble mean  [✓] ±2 SEM band  [✓] ME curve
                       [✓] final-state histogram  [✓] transverse/|m| panel  [✓] panel D
                       [ ] individual seed traces (thin, α-blended)
  Bins/thresholds:     final window 300–310 K | up > +0.7 | reversed < −0.7  (defaults, editable)
  Plot ranges:         x [300, 800] K   y(Mz) [−0.1, 1.0]   [auto]
┌───────────────────────────┐
│ │      RUN COMPARISON     │ │   (disabled ✕ until validation pass/accepted)
└───────────────────────────┘   progress: parsing ▸ ME solve ▸ stats ▸ plot (worker thread)
```

## B.6 Section 5 — Results (tabbed)

```
▶ 5. RESULTS      tabs:  [ Plots ] [ Numerical ] [ Parameter audit ] [ Export ]

Plots tab:      toolbar: [panel A|B|C|D toggles] [zoom] [log-y Γ overlay?] [ colours ]
                2×2 grid identical to validated mz_500.png; click panel = enlarge;
                hover tooltips show (T, Mz̄, ±2SEM, ME M) and per-seed values.
Numerical tab:  table = numbers_<rate>.txt content (m(300K), P_rev, rmse, seed counts,
                T-row table) + CSV download; per-seed final Mz table sortable.
Parameter audit tab: full §7 record preview — sources, conversions, validator output,
                file hashes, ME/plot settings; button [Re-run exactly this comparison].
Export tab:     figure: PNG / PDF / SVG (dpi, size); data: CSV; record: JSON folder
                cmp_<timestamp>/ with checksums.sha256.
```

## B.7 Key dialogs

- **Seed selector**: checkbox tree rate→seeds, "DONE only" pre-ticked, shows n.
- **Consistency confirmation** (modal, blocking on critical): rule list, red/amber rows,
  evidence (file+line), accept checkbox tied to session + stored in record.
- **Source viewer**: read-only file text with the evidence line highlighted.
- **Open comparison record**: pick a saved `cmp_*` folder → restores every section
  exactly (reproducible re-run button).

## B.8 User workflow summary

1. Browse deck (or results dir — deck auto-detected) → sections fill automatically.
2. Review amber/red rows in §2 (source viewer on click) → confirm or fix interpretation.
3. Verify + Validate → consistency report; tick acceptance if warnings.
4. Choose rate/seeds/overlays → RUN COMPARISON (worker thread, progress shown).
5. Inspect plots/numbers → export figures/CSV → record auto-saved with hashes.
6. Later: open record → [Re-run] reproduces the comparison bit-for-bit.
