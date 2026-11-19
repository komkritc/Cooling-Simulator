"""Shared data types for the VAMPIRE–ME Comparison Studio core (no Qt imports here)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Status(Enum):
    EXTRACTED = "extracted"     # read directly from a VAMPIRE file (●)
    DERIVED = "derived"         # computed by the app from extracted values (⚙)
    CONFLICT = "conflict"       # two sources disagree; user must decide (▲)
    ASSUMED = "assumed"         # read but unit/interpretation assumed; needs review (▲)
    MISSING = "missing"         # not available anywhere; needs user input (✕)
    USER = "user_input"         # typed in by the user (✎)


@dataclass
class Source:
    file: str                  # absolute path
    line: Optional[int] = None
    raw: str = ""              # verbatim source line (or formula for derived)

    def cite(self) -> str:
        return f"{self.file}:{self.line}" if self.line else self.file


@dataclass
class ParameterRecord:
    key: str
    value: Any
    unit: str = ""             # declared unit tag: 'A','s','T','muB','K','' or 'unit:assumed'
    status: Status = Status.EXTRACTED
    sources: list[Source] = field(default_factory=list)
    note: str = ""

    def as_dict(self) -> dict:
        return {"key": self.key, "value": self.value, "unit": self.unit,
                "status": self.status.value,
                "sources": [{"file": s.file, "line": s.line, "raw": s.raw}
                            for s in self.sources],
                "note": self.note}


class ParameterTable:
    """Ordered, source-traceable parameter store (extraction engine output)."""

    def __init__(self):
        self.records: dict[str, ParameterRecord] = {}
        self.order: list[str] = []
        self.unrecognised: list[Source] = []   # parsed but unused directives

    def put(self, rec: ParameterRecord):
        if rec.key not in self.records:
            self.order.append(rec.key)
        self.records[rec.key] = rec

    def get(self, key: str) -> Optional[ParameterRecord]:
        return self.records.get(key)

    def value(self, key: str) -> Any:
        r = self.records.get(key)
        return None if r is None else r.value

    def all(self) -> list[ParameterRecord]:
        return [self.records[k] for k in self.order]

    def as_dicts(self) -> list[dict]:
        return [r.as_dict() for r in self.all()]


@dataclass
class Conversion:
    """One unit conversion / derived formula, recorded for the audit trail."""
    what: str
    formula: str
    inputs: dict
    result: Any
    unit_in: str = ""
    unit_out: str = ""


@dataclass
class MEConfig:
    """Every input the ME solver needs — each item provenance-tagged via `provs`."""
    d_nm: float                       # diameter fed to the RF surrogate (nm)
    n_atoms: int
    cell_a_m: float                   # unit cell a (m)
    cell_c_m: float                   # unit cell c (m)
    mu_s_mub: float                   # atomic spin moment (mu_B)
    gamma_rel: float                  # relative gamma from .mat
    b_app_T: float                    # applied flux density (T)
    damping_value: float              # value read from .mat (interpretation per below)
    t_start_K: float
    t_end_K: float
    rate_K_per_ns: float              # cooling rate
    damping_interpretation: str = "identity"   # 'identity' (λ=α) or 'll_to_gilbert'
    dT_grid_K: float = 1.0            # ME temperature grid step (app default, logged)
    p0: float = 0.5                   # initial up/down probability (rule I1)
    volume_mode: str = "deck"         # 'deck' (n_atoms*v_cell, validated) |
                                      # 'sphere' (V = pi/6 d^3, hypothetical)
    provs: dict = field(default_factory=dict)
    conversions: list[Conversion] = field(default_factory=list)

    # ---- derived, SI ----
    @property
    def v_cell_m3(self) -> float:
        return self.cell_a_m ** 2 * self.cell_c_m

    @property
    def v_grain_m3(self) -> float:
        if self.volume_mode == "sphere":
            import math
            return math.pi / 6.0 * (self.d_nm * 1e-9) ** 3
        return self.n_atoms * self.v_cell_m3

    @property
    def rate_K_per_s(self) -> float:
        return self.rate_K_per_ns * 1e9

    @property
    def dt_s(self) -> float:
        return self.dT_grid_K / self.rate_K_per_s

    def as_dict(self) -> dict:
        d = {k: getattr(self, k) for k in
             ("d_nm", "n_atoms", "cell_a_m", "cell_c_m", "mu_s_mub", "gamma_rel",
              "b_app_T", "damping_value", "damping_interpretation", "t_start_K",
              "t_end_K", "rate_K_per_ns", "dT_grid_K", "p0")}
        d["derived"] = {"v_cell_m3": self.v_cell_m3, "v_grain_m3": self.v_grain_m3,
                        "dt_s": self.dt_s}
        d["provenance"] = {k: (s.cite() if isinstance(s, Source) else str(s))
                           for k, s in self.provs.items()}
        d["conversions"] = [c.__dict__ for c in self.conversions]
        return d


@dataclass
class ValidationIssue:
    rule: str
    severity: str            # 'pass' | 'warning' | 'critical'
    message: str
    evidence: list[Source] = field(default_factory=list)
