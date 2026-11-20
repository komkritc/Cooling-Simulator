"""Unit handling: declared-unit parsing (VAMPIRE `!unit` suffixes) and SI conversion.

Every conversion performed by the app goes through this module so it can be
recorded in the audit trail.  Absence of a declared suffix gives ASSUMED status
downstream — values are never silently assumed to be SI.
"""
from __future__ import annotations

from .types import Conversion

# VAMPIRE comment-suffix (`!xx`) -> canonical unit tag
SUFFIX_TO_UNIT = {
    "a": "A", "ang": "A", "angstrom": "A",
    "s": "s", "second": "s",
    "t": "T", "tesla": "T",
    "k": "K", "kelvin": "K",
    "mub": "muB", "mu_b": "muB",
    "nm": "nm", "m": "m", "m3": "m3", "j": "J", "am": "A/m", "a_per_m": "A/m",
}

# canonical unit -> factor to multiply by to reach SI base
TO_SI = {
    "A": 1e-10,          # angstrom -> m
    "s": 1.0,
    "T": 1.0,            # flux density (VAMPIRE works with B)
    "K": 1.0,
    "muB": 9.2740100783e-24,   # Bohr magneton -> A m^2
    "nm": 1e-9,          # nanometre -> m
    "m": 1.0,
    "m3": 1.0,
    "J": 1.0,
    "A/m": 1.0,
    "": 1.0,
}
MU0 = 4.0e-7 * 3.14159265358979323846264338327950288  # pi from math below

import math
MU0 = 4.0e-7 * math.pi
MU_B = 9.2740100783e-24
GAMMA_E = 1.76085963e11


def parse_declared_unit(comment: str) -> tuple[str, str]:
    """Extract the `!unit` suffix from a trailing VAMPIRE comment.

    Returns (canonical_unit, raw_suffix).  ('', '') when no suffix present.
    """
    if "!" not in comment:
        return "", ""
    tail = comment.split("!", 1)[1]
    tok = tail.strip().split()[0] if tail.strip() else ""
    unit = SUFFIX_TO_UNIT.get(tok.lower(), "")
    return unit, tok


def to_si(value: float, unit: str, *, what: str,
          log: list[Conversion] | None = None) -> float:
    if unit not in TO_SI:
        raise KeyError(f"unknown unit tag '{unit}' for {what}")
    out = value * TO_SI[unit]
    if log is not None and TO_SI[unit] != 1.0:
        log.append(Conversion(what=what, formula=f"{value} [{unit}] * {TO_SI[unit]:.6e}",
                              inputs={"value": value, "unit": unit}, result=out,
                              unit_in=unit, unit_out="SI"))
    return out


def b_to_h(b_T: float, *, what: str = "H_app",
           log: list[Conversion] | None = None) -> float:
    h = b_T / MU0
    if log is not None:
        log.append(Conversion(what=what, formula="H = B / mu0",
                              inputs={"B_T": b_T, "mu0": MU0}, result=h,
                              unit_in="T", unit_out="A/m"))
    return h
