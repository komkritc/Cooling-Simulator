"""Mapping engine: ParameterTable -> MEConfig (spec C.2) with unit register C.4.

Every derived quantity records its formula + inputs as a Conversion for the
audit.  Missing required parameters raise MappingError listing exactly what the
user must supply — no silent defaults except the two *declared* app defaults
(ME grid step dT = 1 K, initial P0 = 0.5), which are logged as such.
"""
from __future__ import annotations

from .types import Conversion, MEConfig, ParameterTable, Source, Status
from .units import b_to_h, to_si, MU_B, GAMMA_E


class MappingError(Exception):
    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__("missing required parameters: " + ", ".join(missing))


def map_to_me(table: ParameterTable, *,
              dT_grid_K: float = 1.0,
              damping_interpretation: str = "identity",
              rf_d_nm: float | None = None) -> MEConfig:
    """Build the ME configuration from extracted parameters.

    rf_d_nm: diameter fed to the RF surrogate.  None => derive from deck
    (particle-size); rule M-RF in the validator warns if that differs from the
    validated 4.0 nm convention by >1 %.
    """
    missing, provs = [], {}

    def need(key: str):
        r = table.get(key)
        if r is None or r.value is None:
            missing.append(key)
            return None
        provs[key] = r.sources[0] if r.sources else Source("<none>")
        return r

    conv: list[Conversion] = []

    r_d = need("grain_diameter")
    r_atoms = need("n_atoms")
    r_a = need("cell_a")
    r_c = need("cell_c")
    r_mu = need("atomic_moment")
    r_b = need("B_app")
    r_damp = need("damping")
    r_t0 = need("T_start")
    r_t1 = need("T_end")
    r_ct = need("cooling_time")
    if missing:
        raise MappingError(missing)

    d_m = to_si(float(r_d.value), r_d.unit, what="grain diameter -> m", log=conv)
    a_m = to_si(float(r_a.value), r_a.unit, what="cell a -> m", log=conv)
    c_m = to_si(float(r_c.value), r_c.unit, what="cell c -> m", log=conv)
    b_T = to_si(float(r_b.value), r_b.unit, what="applied B -> T", log=conv)
    t_cool_s = to_si(float(r_ct.value), r_ct.unit, what="cooling time -> s", log=conv)
    mu_mub = float(r_mu.value)          # keep in muB; solver converts with MU_B
    conv.append(Conversion("atomic moment", "mu_s [A m^2] = muB_value * 9.2740100783e-24",
                           {"muB": mu_mub}, mu_mub * MU_B, "muB", "A m^2"))

    t_start, t_end = float(r_t0.value), float(r_t1.value)
    rate = (t_start - t_end) / (t_cool_s * 1e9)      # K/ns
    conv.append(Conversion("cooling rate",
                           "R = (T_start - T_end) / t_cool",
                           {"T_start": t_start, "T_end": t_end, "t_cool_s": t_cool_s},
                           rate, "K/ns", "K/ns"))

    gam_rel = 1.0
    r_g = table.get("gamma_relative")
    if r_g is not None and r_g.value is not None:
        gam_rel = float(r_g.value)
        provs["gamma_relative"] = r_g.sources[0]
    conv.append(Conversion("gyromagnetic ratio", "gamma = rel * gamma_e",
                           {"rel": gam_rel, "gamma_e": GAMMA_E}, gam_rel * GAMMA_E))

    b_to_h(b_T, what="H_app = B/mu0 (for ME field terms)", log=conv)

    d_nm_rf = rf_d_nm if rf_d_nm is not None else d_m / 1e-9
    conv.append(Conversion("RF diameter input",
                           "d_nm = particle-size (m) / 1e-9"
                           + ("" if rf_d_nm is None else "  [USER OVERRIDE]"),
                           {"d_m": d_m}, d_nm_rf, "m", "nm"))

    cfg = MEConfig(
        d_nm=d_nm_rf, n_atoms=int(r_atoms.value),
        cell_a_m=a_m, cell_c_m=c_m, mu_s_mub=mu_mub, gamma_rel=gam_rel,
        b_app_T=b_T, damping_value=float(r_damp.value),
        damping_interpretation=damping_interpretation,
        t_start_K=t_start, t_end_K=t_end,
        rate_K_per_ns=rate, dT_grid_K=dT_grid_K, p0=0.5,
        provs=provs, conversions=conv)
    cfg.conversions.append(Conversion(
        "ME grid step", "dT_grid app default (logged, not a VAMPIRE value)",
        {}, dT_grid_K, "K", "K"))
    cfg.conversions.append(Conversion(
        "P0 initial", "rule I1 field-cool assumption P0 = 0.5", {}, 0.5))
    return cfg


def me_inputs_for_solver(cfg: MEConfig) -> dict:
    """Solver kwargs derived from the config (single place for physics constants)."""
    v_cell = cfg.v_cell_m3
    v_grain = cfg.v_grain_m3
    mu_s = cfg.mu_s_mub * MU_B
    return {
        "V_grain": v_grain,
        "V_cell": v_cell,
        "MU_S": mu_s,
        "MS_0": mu_s / v_cell,
        "GAMMA": cfg.gamma_rel * GAMMA_E,
        "H_APP": cfg.b_app_T / (4.0e-7 * 3.141592653589793),
        "LAMBDA": (cfg.damping_value if cfg.damping_interpretation == "identity"
                   else cfg.damping_value / (1.0 + cfg.damping_value ** 2)),
        "N_ATOMS": cfg.n_atoms,
    }
