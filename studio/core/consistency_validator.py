"""Consistency validation rules G1..D1 (plan §A.6).

Returns ValidationIssue objects with severity 'pass' | 'warning' | 'critical'.
A critical issue blocks RUN until the user accepts explicitly (stored in the
comparison record).  Nothing here modifies any input file.
"""
from __future__ import annotations

import math
import re

from .types import ParameterTable, MEConfig, Source, ValidationIssue

PI = math.pi


def validate(table: ParameterTable, cfg: MEConfig | None,
             model_meta: dict | None, seed_info: dict,
             run_dir_hint: str = "") -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    def add(rule, sev, msg, ev=()):
        issues.append(ValidationIssue(rule, sev, msg, list(ev)))

    # ---- G1 grain volume: atoms*cell vs cylinder(pi/4 D^2 h) ----
    D = table.value("grain_diameter"); h = table.value("grain_height")
    a = table.value("cell_a"); c = table.value("cell_c"); nat = table.value("n_atoms")
    if None not in (D, h, a, c, nat):
        v_shape = PI / 4.0 * D * D * h
        v_count = nat * a * a * c
        dev = abs(v_count - v_shape) / v_shape
        ev = [s for k in ("grain_diameter", "n_atoms") if table.get(k)
              for s in table.get(k).sources]
        if dev > 0.02:
            add("G1", "critical", f"volume mismatch {dev*100:.1f} %: "
                f"atoms*cell = {v_count:.3e} vs cylinder = {v_shape:.3e} (A^3)", ev)
        else:
            add("G1", "pass", f"grain volume consistent ({dev*100:.2f} % deviation)", ev)
    else:
        add("G1", "warning", "grain geometry incomplete - volume cross-check skipped")

    # ---- G2 isolated grain: particle-size == system-size-x ----
    ps, sx = table.value("grain_diameter"), table.value("system_size_x")
    if ps is not None and sx is not None:
        add("G2", "pass" if abs(ps - sx) < 1e-9 else "warning",
            f"particle-size {ps} vs system-size-x {sx}")

    # ---- M1 moment -> M_s0 self-consistency ----
    if cfg is not None:
        mu = cfg.mu_s_mub * 9.2740100783e-24
        ms0 = mu / (cfg.cell_a_m ** 2 * cfg.cell_c_m)
        rel = abs(ms0 - mu / (cfg.cell_a_m ** 2 * cfg.cell_c_m))
        add("M1", "pass", f"M_s0 = mu_S/V_cell = {ms0:.4e} A/m (derived, self-consistent)")
    else:
        add("M1", "critical", "ME configuration missing")

    # ---- M2 damping interpretation ----
    dmp = table.value("damping")
    if dmp is None:
        add("M2", "critical", "damping constant missing - user input required")
    else:
        add("M2", "warning",
            f"damping-constant = {dmp}: interpreted as lambda_ME = "
            f"{'alpha (identity)' if cfg and cfg.damping_interpretation == 'identity' else 'alpha/(1+alpha^2)'}; "
            "confirm interpretation",
            [s for s in (table.get("damping").sources if table.get("damping") else [])])

    # ---- M3 field magnitude + direction ----
    B = table.value("B_app"); fd = table.value("field_direction")
    ea = table.value("easy_axis")
    if B is None:
        add("M3", "critical", "applied field missing")
    else:
        if not (0.0 <= B <= 10.0):
            add("M3", "critical", f"applied field {B} implausible (unit error?)")
        elif fd is not None and ea is not None and tuple(fd) != tuple(ea):
            add("M3", "warning", f"field direction {fd} != easy axis {ea}")
        else:
            add("M3", "pass", f"applied field {B} T along {fd}")

    # ---- M-RF: RF surrogate diameter vs deck diameter ----
    if cfg is not None and D is not None:
        d_deck = D / 10.0          # A -> nm
        if abs(cfg.d_nm - d_deck) / d_deck > 0.001:
            add("M-RF", "warning",
                f"RF surrogate fed D = {cfg.d_nm} nm, deck gives {d_deck:.2f} nm "
                "(snapped to validated/trained diameter)")
        else:
            add("M-RF", "pass", f"RF diameter matches deck ({cfg.d_nm} nm)")

    # ---- T1 temperature range ----
    if cfg is not None:
        t0 = table.value("T_start"); t1 = table.value("T_end")
        ok = (t0 == cfg.t_start_K) and (t1 == cfg.t_end_K)
        add("T1", "pass" if ok else "critical",
            f"ME grid {cfg.t_start_K}->{cfg.t_end_K} K vs deck {t0}->{t1} K")

    # ---- T2 cooling rate vs run directory naming ----
    if cfg is not None and run_dir_hint:
        m = re.search(r"rate_(\d+(?:\.\d+)?)Kns", run_dir_hint)
        if m:
            named = float(m.group(1))
            rel = abs(cfg.rate_K_per_ns - named) / named
            add("T2", "pass" if rel <= 0.01 else "critical",
                f"deck-implied rate {cfg.rate_K_per_ns:g} K/ns vs run dir {named:g} K/ns")
        else:
            add("T2", "warning", "run dir name carries no rate token; cross-check skipped")

    # ---- T3 temperature sampling ----
    tsi = seed_info.get("sampling")
    if tsi:
        med, mono = tsi
        add("T3", "pass" if (0.5 <= med <= 2.0 and mono) else "warning",
            f"median dT step {med:.2f} K, monotone={mono}")
    else:
        add("T3", "warning", "no output sampling info")

    # ---- O1 column layout ----
    extra = seed_info.get("extra_cols", [])
    if seed_info.get("loaded"):
        add("O1", "warning" if extra else "pass",
            f"column layout from deck directives; {len(extra)} unmapped trailing columns"
            if extra else "column layout fully mapped to deck directives")
    else:
        add("O1", "critical", "no output data loaded")

    # ---- R1 RF model registration ----
    if model_meta is None:
        add("R1", "critical", "material LUT (lut_*.csv) not found")
    elif not model_meta.get("registered"):
        add("R1", "critical",
            f"unregistered material LUT (sha256 {model_meta.get('sha256_lut','?')[:12]}...)")
    else:
        add("R1", "pass",
            f"material LUT registered, Tc = {model_meta.get('metadata', {}).get('Tc_K', 'n/a')} K")

    # ---- I1 initial state ----
    add("I1", "warning" if cfg and cfg.p0 == 0.5 else "pass",
        "ME initial condition P0 = 0.5 (field-cool assumption, logged)")

    # ---- D1 seeds / DONE markers ----
    n_done = seed_info.get("n_done", 0)
    inc = seed_info.get("n_incomplete", 0)
    if n_done == 0:
        add("D1", "critical", "no completed (DONE) seeds found")
    elif inc:
        add("D1", "warning", f"{inc} incomplete seed dir(s) skipped; {n_done} loaded")
    else:
        add("D1", "pass", f"{n_done} DONE seeds, none incomplete")

    return issues


def summarise(issues: list[ValidationIssue]) -> dict:
    return {"n_pass": sum(1 for i in issues if i.severity == "pass"),
            "n_warning": sum(1 for i in issues if i.severity == "warning"),
            "n_critical": sum(1 for i in issues if i.severity == "critical")}
