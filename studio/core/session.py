"""AnalysisSession: the Qt-free orchestration service used by GUI and tests.

Pipeline (plan §A.4): scan run dir -> parse deck/mat/log -> extract ->
map to MEConfig (with registered-model diameter snap, logged) -> validate ->
load seeds -> ME solve -> statistics.  Produces immutable, JSON-serialisable
objects for the audit manager.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import consistency_validator as cv
from .extraction_engine import extract
from .mapping_engine import map_to_me, me_inputs_for_solver, MappingError
from .me_solver import MESolver
from .lut_material import LutMaterial, find_lut, lut_info
from .statistics import ComparisonStats, compute_stats
from .units import to_si
from .vampire_input_parser import parse_deck, DECK_KEYS
from .vampire_mat_parser import parse_mat
from .vampire_output_reader import (find_seeds, incomplete_seeds, load_seed,
                                    header_provenance, layout_from_deck)


@dataclass
class ComparisonResult:
    stats: ComparisonStats
    T_me: np.ndarray
    m_me: np.ndarray
    P_me: np.ndarray
    ms_me: np.ndarray
    Tc: float
    Gam_me: np.ndarray
    rmse: float
    m300: float
    prev300: float


class AnalysisSession:
    def __init__(self, run_dir: str, *, rf_d_nm: float | None = None,
                 damping_interpretation: str = "identity",
                 dT_grid_K: float = 1.0,
                 snap_diameter: bool = True):
        self.run_dir = os.path.abspath(run_dir)
        self.seed_dirs_all = find_seeds(self.run_dir)
        self.incomplete = incomplete_seeds(self.run_dir)
        if not self.seed_dirs_all:
            raise FileNotFoundError(
                f"no DONE seeds under {self.run_dir} "
                f"({len(self.incomplete)} incomplete dirs ignored)")

        deck_path = self._find_deck(self.seed_dirs_all[0])
        self.deck = parse_deck(deck_path, DECK_KEYS)

        mat_path = self._find_mat(os.path.dirname(deck_path))
        self.mat = parse_mat(mat_path) if mat_path else None

        log_path = os.path.join(self.seed_dirs_all[0], "log")
        self.table = extract(self.deck, self.mat,
                             log_path if os.path.isfile(log_path) else None)

        self.data_root = self._guess_data_root()
        lut = find_lut()
        self.model_dir = lut                      # path of the LUT csv (kept name for the audit/GUI)
        self.model_meta = lut_info(lut) if lut else None

        # RF diameter: by default snap to the registered model's trained diameter when within 5 %
        # (validated baseline).  snap_diameter=False uses the deck's own particle size, which the
        # LUT interpolates (e.g. 4.08 nm between the 4.0 and 4.1 nm grid rows).
        _gd = self.table.get("grain_diameter")
        d_deck_nm = (to_si(float(_gd.value), _gd.unit, what="grain diameter")
                     / 1e-9) if _gd is not None and _gd.value else 0.0
        d_train = (self.model_meta or {}).get("metadata", {}).get("D_nm")
        self.rf_d_snapped = False
        if rf_d_nm is not None:
            self.rf_d = rf_d_nm
        elif (snap_diameter and d_train and d_deck_nm and
              abs(d_deck_nm - d_train) / d_train <= 0.05):
            self.rf_d, self.rf_d_snapped = d_train, True
        else:
            self.rf_d = d_deck_nm or 4.0

        self.damping_interpretation = damping_interpretation
        self.dT_grid_K = dT_grid_K
        self.overrides: dict = {}          # user-set overrides (for audit)
        self.cfg = None
        self.mapping_error: list[str] = []
        try:
            self.cfg = map_to_me(self.table, dT_grid_K=dT_grid_K,
                                 damping_interpretation=damping_interpretation,
                                 rf_d_nm=self.rf_d)
        except MappingError as e:
            self.mapping_error = e.missing

        self.rate_deck = (self.cfg.rate_K_per_ns if self.cfg
                          else _rate_from_run_dir(self.run_dir))

        self.layout = layout_from_deck(self.deck)
        self.seeds = []
        self.provenance = header_provenance(self.seed_dirs_all[0])

    # ---------- helpers ----------
    @staticmethod
    def _find_deck(seed_dir: str) -> str:
        for name in ("input",):
            p = os.path.join(seed_dir, name)
            if os.path.isfile(p):
                return p
        import glob
        c = sorted(glob.glob(os.path.join(seed_dir, "*.input")))
        if c:
            return c[0]
        raise FileNotFoundError(f"no deck (input / *.input) in {seed_dir}")

    @staticmethod
    def _find_mat(seed_dir: str) -> str | None:
        import glob
        c = sorted(glob.glob(os.path.join(seed_dir, "*.mat")))
        return c[0] if c else None

    def _guess_data_root(self) -> str:
        d = self.run_dir
        for _ in range(6):
            d = os.path.dirname(d)
            if os.path.isdir(os.path.join(d, "model")) or \
               os.path.isfile(os.path.join(d, "manifest.tsv")):
                return d
        return os.path.dirname(self.run_dir)

    # ---------- API ----------
    def apply_settings(self, *, d_nm: float | None = None,
                       rate_K_per_ns: float | None = None,
                       volume_mode: str | None = None) -> list[str]:
        """Rebuild the ME configuration with explicit user overrides.

        Every applied override is appended to cfg.conversions and to
        self.overrides so it lands in the comparison record (audit rule).
        Returns human-readable descriptions of what changed."""
        if self.cfg is None:
            raise RuntimeError("ME config unavailable: missing "
                               + str(self.mapping_error))
        changed: list[str] = []
        d_new = self.rf_d if d_nm is None else float(d_nm)
        r_new = (self.rate_deck if rate_K_per_ns is None
                 else float(rate_K_per_ns))
        v_new = self.cfg.volume_mode if volume_mode is None else volume_mode

        if abs(d_new - self.rf_d) > 1e-9 or self.overrides.get("d_nm"):
            self.rf_d = d_new
        self.cfg = map_to_me(self.table, dT_grid_K=self.dT_grid_K,
                             damping_interpretation=self.damping_interpretation,
                             rf_d_nm=self.rf_d)
        if d_nm is not None:
            self.overrides["d_nm"] = d_new
            trained = (self.model_meta or {}).get("metadata", {}).get("D_nm", "?")
            changed.append(f"diameter -> {d_new:g} nm (user override; deck "
                           f"{d_deck_nm(self.table):.3g} nm, RF-trained "
                           f"{trained} nm)")
        if abs(r_new - self.rate_deck) > 1e-12:
            from .types import Conversion
            self.cfg.conversions.append(Conversion(
                "cooling rate OVERRIDE", "user-set rate; deck value was "
                f"{self.rate_deck:g} K/ns", {"rate_K_per_ns": r_new}, r_new,
                "K/ns", "K/ns"))
            self.overrides["rate_K_per_ns"] = r_new
            changed.append(f"cooling rate -> {r_new:g} K/ns (deck: "
                           f"{self.rate_deck:g} K/ns)")
        self.cfg.rate_K_per_ns = r_new
        if v_new != "deck":
            from .types import Conversion
            import math
            v = math.pi / 6.0 * (self.cfg.d_nm * 1e-9) ** 3
            self.cfg.volume_mode = v_new
            self.cfg.conversions.append(Conversion(
                "grain volume OVERRIDE", "V = pi/6 * d^3 (hypothetical sphere;"
                " validated mode uses n_atoms * v_cell)",
                {"d_nm": self.cfg.d_nm}, v, "m^3", "m^3"))
            self.overrides["volume_mode"] = v_new
            changed.append(f"volume model -> sphere(D) = {v:.4g} m^3 "
                           "(HYPOTHETICAL - validated mode is deck n_atoms x cell)")
        else:
            self.cfg.volume_mode = "deck"
        return changed

    def load_seeds(self, only: list[int] | None = None) -> None:
        self.seeds = []
        for sd in self.seed_dirs_all:
            if only is not None and _seed_id(sd) not in only:
                continue
            self.seeds.append(load_seed(sd, self.layout))

    def sampling_info(self) -> tuple[float, bool] | None:
        if not self.seeds:
            return None
        T = self.seeds[0].temp()[self.seeds[0].cool_mask]
        dT = np.diff(T)
        return float(np.median(dT)), bool(np.all(dT < 0))

    def seed_info(self) -> dict:
        return {"loaded": bool(self.seeds),
                "n_done": len(self.seed_dirs_all),
                "n_loaded": len(self.seeds),
                "n_incomplete": len(self.incomplete),
                "extra_cols": (self.seeds[0].layout.extra_cols
                               if self.seeds else self.layout and []),
                "sampling": self.sampling_info()}

    def validate(self) -> list:
        return cv.validate(self.table, self.cfg, self.model_meta,
                           self.seed_info(), run_dir_hint=self.run_dir)

    def run_comparison(self) -> ComparisonResult:
        if self.cfg is None:
            raise RuntimeError(f"ME config unavailable: missing {self.mapping_error}")
        if not self.seeds:
            self.load_seeds()
        ml = LutMaterial(self.model_dir); ml.load()
        solver = MESolver(ml, me_inputs_for_solver(self.cfg))
        solver.configure(self.cfg)
        T_me, m, P, ms, cl, ct, Tc, Gam = solver.predict(
            self.cfg.rate_K_per_ns, self.cfg.t_start_K, self.cfg.t_end_K,
            self.cfg.dT_grid_K)
        stats = compute_stats(self.seeds)
        rmse = stats.rmse_me(T_me, m)
        return ComparisonResult(stats=stats, T_me=T_me, m_me=m, P_me=P,
                                ms_me=ms, Tc=Tc, Gam_me=Gam, rmse=rmse,
                                m300=float(m[-1]), prev300=float(1 - P[-1]))

    def numbers_lines(self, res: ComparisonResults | None = None) -> list[str]:
        """Text identical in format to the validated numbers_<rate>.txt."""
        r = res or self.run_comparison()
        s = r.stats
        lines = [
            f"ME = me_B_roy (Roy): omega1(T)=gamma/chi_perp(T), (1-H/HK)^2 barrier; "
            f"Tc = {r.Tc:g} K",
            f"ME: m(300 K) = {r.m300:.3f}, P_rev = {r.prev300:.3f}; "
            f"rmse vs VAMPIRE mean over 800-300 K = {r.rmse:.4f}",
            f"{self.cfg.rate_K_per_ns:g} K/ns, {s.n} seeds: up {s.up}, reversed {s.down}, "
            f"partly ordered {s.partial}; mean final Mz = {s.mean_final:+.4f} "
            f"+- {s.sem_final:.4f}; mean |m| at 300 K = {s.mean_mlen_300:.3f}; "
            f"P_down = {s.p_down_vampire:.3f}",
            "T(K) | VAMPIRE mean +- 2 sem | ME Roy | Gamma_Roy (1/s)"]
        for t in (750, 700, 680, 660, 640, 620, 600, 550, 500, 400, 305):
            ww = (s.T >= t - 5) & (s.T < t + 5)
            j = int(np.argmin(np.abs(r.T_me - t)))
            lines.append(
                f"{t:4d} | {s.mean[ww].mean():+.3f} +- "
                f"{2*s.sem[ww].mean():.3f} | "
                f"{np.interp(t, r.T_me[::-1], r.m_me[::-1]):+.3f} | "
                f"{r.Gam_me[j]:.3e}")
        return lines


def _rate_from_run_dir(d: str) -> float:
    import re
    m = re.search(r"rate_(\d+)Kns", d)
    return float(m.group(1)) if m else 0.0


def d_deck_nm(table) -> float:
    return (table.value("grain_diameter") or 0) / 10.0


def _seed_id(d: str) -> int:
    import re
    m = re.search(r"seed_(\d+)", d)
    return int(m.group(1)) if m else -1


# keep typing happy for the helper signature
ComparisonResults = ComparisonResult
