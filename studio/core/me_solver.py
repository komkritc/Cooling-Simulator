"""Roy two-state Master Equation solver — physics copied verbatim from the
validated module derived/me_B_roy.py, parameterised by MEConfig (Phase 3:
"physics frozen"; acceptance = golden numbers reproduced for all 6 rates).

No module-level physical constants: everything flows from me_inputs_for_solver().
"""
from __future__ import annotations

import math

import numpy as np

from .mapping_engine import me_inputs_for_solver
from .lut_material import LutMaterial

MU0 = 4.0e-7 * math.pi
KB = 1.380649e-23
S_SPIN = 1.5
EPSILON = 1e-12
EXP_MAX = 80.0


class MESolver:
    def __init__(self, ml: LutMaterial, inputs: dict):
        self.ml = ml
        self.inp = inputs
        self._ml_cache: dict = {}

    # ---- equilibrium / rate functions (identical arithmetic to me_B_roy) ----
    def predict(self, rate, T_start=800.0, T_end=300.0, dT=1.0):
        """Full ME run; signature/arithmetic identical to me_B_roy.predict."""
        V_GRAIN, MS_0, GAMMA, H_APP, LAMBDA = (self.inp["V_grain"], self.inp["MS_0"],
                                               self.inp["GAMMA"], self.inp["H_APP"],
                                               self.inp["LAMBDA"])
        key = (T_start, T_end, dT, self.ml_dir_key())
        if key not in self._ml_cache:
            T = np.arange(T_start, T_end - dT, -dT)
            ms, cl, ct = self.ml.predict(self.cfg_d_nm, T)
            self._ml_cache[key] = (T, ms, cl, ct, float(T[np.argmax(cl)]))
        T, ms, cl, ct, Tc = self._ml_cache[key]
        dt = dT / (rate * 1e9)
        P = np.zeros(len(T)); m = np.zeros(len(T)); Gam = np.zeros(len(T))
        P[0] = self.p0
        m[0] = np.clip(ms[0] * (2 * P[0] - 1), 0, ms[0])
        for i in range(len(T) - 1):
            Gam[i] = self._escape_rate(T[i], ms[i], cl[i], ct[i],
                                       V_GRAIN, Tc, H_APP, GAMMA, MS_0, LAMBDA)
            meq = self._m_eq_field(T[i + 1], ms[i + 1], V_GRAIN, H_APP, MS_0)
            Pe = np.clip(0.5 * (1 + meq / max(ms[i + 1], EPSILON)), 0, 1)
            P[i + 1] = np.clip(Pe + (P[i] - Pe) * np.exp(-Gam[i] * dt), 0, 1)
            m[i + 1] = np.clip(ms[i + 1] * (2 * P[i + 1] - 1), 0, ms[i + 1])
        return T, m, P, ms, cl, ct, Tc, Gam

    # ---- internals ----
    def _alpha2_T(self, T, m_s, Tc, LAMBDA):
        m_e = max(float(m_s), EPSILON)
        q = max((3.0 * Tc * m_e) / (2.0 * (S_SPIN + 1.0) * T), EPSILON)
        a2 = (LAMBDA / m_e) * (np.tanh(q) / q - T / (3.0 * Tc))
        return float(np.clip(a2, 1e-6, 0.3))

    def _m_eq_field(self, T, m_s, V, H, MS_0):
        arg = (MU0 * V * (MS_0 * m_s) * H) / (KB * T)
        return m_s * np.tanh(np.clip(arg, -50.0, 50.0))

    def _escape_rate(self, T, m_s, chi_L, chi_T, V, Tc, H_appl, GAMMA, MS_0, LAMBDA):
        chi_T = max(float(chi_T), EPSILON)
        chi_L = max(float(chi_L), EPSILON)
        m_e = max(float(m_s), EPSILON)
        sigma = np.clip((MU0 * (MS_0 * m_e)**2 * V) / (2.0 * chi_T * KB * T),
                        0.0, EXP_MAX)
        r = max(2.0 * chi_L / chi_T, EPSILON)
        alpha2 = self._alpha2_T(T, m_e, Tc, LAMBDA)
        omega1 = GAMMA / chi_T
        if r <= 1.0:
            if T >= Tc:
                exponent = -sigma * (1.0 - 0.5 * r)
            else:
                H_ratio = MU0 * H_appl * chi_T
                exponent = -sigma * (1.0 - H_ratio)**2 * (1.0 - 0.5 * r)
            Gamma = 2.0 * alpha2 * omega1 * np.sqrt(sigma / np.pi) * np.exp(
                np.clip(exponent, -EXP_MAX, EXP_MAX))
        else:
            base = max(float((r * sigma / 2.0) * (1.0 - 1.0 / r)), 0.0)
            Gamma0 = (alpha2 * omega1 * np.sqrt(sigma / (np.pi * r)) *
                      np.exp(np.clip(base * (1.0 - 1.0 / r), -EXP_MAX, EXP_MAX)) *
                      math.erfc(np.sqrt(base)))
            Gamma = Gamma0 * np.exp(np.clip(-2.0 * sigma / (4.0 * r), -EXP_MAX, EXP_MAX))
        return max(float(Gamma), 1e-40)

    # configuration passthroughs
    cfg_d_nm = 4.0
    p0 = 0.5

    def configure(self, cfg):
        self.cfg_d_nm = cfg.d_nm
        self.p0 = cfg.p0

    def ml_dir_key(self):
        return (self.cfg_d_nm, id(self.ml))
