"""Material surrogate as a lookup table (LUT): (D_nm, T) -> m_s, chi_par, chi_perp.

Replaces the random-forest pickles.  The LUT is a CSV (columns diameter_nm, temperature_K,
m_s, chi_L, chi_T) built once from the validated RF surrogate by ../make_lut.py; the app
only interpolates it (bilinear in D and T), so scikit-learn and the pickles are not needed.

A LUT is accepted as 'registered' only if its SHA-256 is listed in lut_registry.json.
Requests outside the LUT range raise ValueError (no silent extrapolation).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REGISTRY = HERE / "lut_registry.json"
LUT_NAME = "lut_current_rf_1-10nm_dD0p1.csv"

LUT_CANDIDATE_DIRS = [
    lambda here: here.parent.parent.parent / "data",     # ME_Cooling_LUT/app/studio/core -> ME_Cooling_LUT/data
    lambda here: here.parent.parent / "data",            # app/data
]

def find_lut(start: Path | None = None) -> Path | None:
    """Locate the LUT CSV: $ME_LUT_FILE, then ME_Cooling_LUT/data, then app/data."""
    env = os.environ.get("ME_LUT_FILE")
    if env and Path(env).is_file():
        return Path(env)
    for mk in LUT_CANDIDATE_DIRS:
        p = mk(HERE) / LUT_NAME
        if p.is_file():
            return p
    return None

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def load_registry() -> dict:
    if REGISTRY.exists():
        with open(REGISTRY) as f:
            return json.load(f)
    return {}

def lut_info(lut_path: Path) -> dict:
    h = sha256_file(lut_path)
    meta = load_registry().get(h, {"registered": False})
    return {"file": str(lut_path), "sha256_lut": h,
            "registered": meta.get("registered", False), "metadata": meta}

class LutMaterial:
    """Bilinear interpolation of the (D, T) lookup table.  Same predict() interface as the old RF."""

    def __init__(self, lut_path: Path):
        self.path = Path(lut_path)
        self.D = self.T = self.table = None

    def load(self):
        a = np.genfromtxt(self.path, delimiter=",", names=True)
        self.D = np.unique(a["diameter_nm"]); self.T = np.unique(a["temperature_K"])
        if len(self.D) * len(self.T) != len(a):
            raise ValueError(f"{self.path.name}: not a complete (D, T) grid")
        order = np.lexsort((a["temperature_K"], a["diameter_nm"]))        # D major, T minor
        shape = (len(self.D), len(self.T))
        self.table = np.stack([a[n][order].reshape(shape) for n in ("m_s", "chi_L", "chi_T")])

    @property
    def d_range(self):
        return float(self.D[0]), float(self.D[-1])

    @property
    def t_range(self):
        return float(self.T[0]), float(self.T[-1])

    def predict(self, D_nm, T):
        """-> (m_s, chi_par, chi_perp) at diameter D_nm (scalar) and temperatures T (array, K)."""
        T = np.asarray(T, dtype=float)
        D_nm = float(D_nm)
        eps = 1e-9
        if not (self.D[0] - eps <= D_nm <= self.D[-1] + eps):
            raise ValueError(f"grain diameter {D_nm:g} nm is outside the LUT range "
                             f"{self.D[0]:g}-{self.D[-1]:g} nm")
        if T.size and (T.min() < self.T[0] - eps or T.max() > self.T[-1] + eps):
            raise ValueError(f"temperature {T.min():g}-{T.max():g} K is outside the LUT range "
                             f"{self.T[0]:g}-{self.T[-1]:g} K")
        i = int(np.clip(np.searchsorted(self.D, D_nm, side="right") - 1, 0, len(self.D) - 2))
        wd = (D_nm - self.D[i]) / (self.D[i + 1] - self.D[i])
        row = (1.0 - wd) * self.table[:, i, :] + wd * self.table[:, i + 1, :]   # (3, nT) at D_nm
        out = [np.interp(T, self.T, row[k]) for k in range(3)]
        return out[0], out[1], out[2]
