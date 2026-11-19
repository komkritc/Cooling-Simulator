"""Seed-ensemble statistics — identical definitions to the validated scripts.

final window 300-310 K; up > +0.7; reversed < -0.7; mean +- 2*SEM;
transverse share at 300 K; rmse of ME vs VAMPIRE mean over the cooling range.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .vampire_output_reader import SeedData


@dataclass
class ComparisonStats:
    T: np.ndarray                       # VAMPIRE temperature axis (cooling rows)
    mz_per_seed: np.ndarray             # (n_seeds, n_T)
    mean: np.ndarray
    sem: np.ndarray
    transverse: np.ndarray              # (n_seeds, n_T) sqrt(Mx^2+My^2)
    mlen: np.ndarray                    # (n_seeds, n_T) |m|
    fin: np.ndarray                     # final Mz per seed
    up: int
    down: int
    partial: int
    n: int
    p_down_vampire: float
    mean_final: float
    sem_final: float
    mean_mlen_300: float
    transverse_share: np.ndarray        # per seed at 300 K
    me_overlaid: dict = field(default_factory=dict)

    def rmse_me(self, T_me, m_me) -> float:
        mi = np.interp(self.T, T_me[::-1], m_me[::-1])
        return float(np.sqrt(np.mean((mi - self.mean) ** 2)))


def compute_stats(seeds: list[SeedData],
                  window: tuple[float, float] = (300.0, 310.0),
                  up_thresh: float = 0.7, down_thresh: float = -0.7) -> ComparisonStats:
    if not seeds:
        raise ValueError("no seeds loaded")
    T = seeds[0].temp()[seeds[0].cool_mask]
    mz = np.array([s.mz()[s.cool_mask] for s in seeds])
    tr = np.array([np.sqrt((s.data[:, s.mlen_col] * s.data[:, s.mx_col]) ** 2
                           + (s.data[:, s.mlen_col] * s.data[:, s.my_col]) ** 2)[s.cool_mask]
                   for s in seeds])
    am = np.array([s.data[:, s.mlen_col][s.cool_mask] for s in seeds])
    n = len(seeds)
    w = (T >= window[0]) & (T < window[1])
    fin = mz[:, w].mean(axis=1)
    mean = mz.mean(axis=0)
    sem = mz.std(axis=0, ddof=1) / np.sqrt(n)
    up = int((fin > up_thresh).sum())
    dn = int((fin < down_thresh).sum())
    share = np.array([((tr[i][w] ** 2).mean() / (am[i][w] ** 2).mean()) for i in range(n)])
    return ComparisonStats(
        T=T, mz_per_seed=mz, mean=mean, sem=sem, transverse=tr, mlen=am,
        fin=fin, up=up, down=dn, partial=n - up - dn, n=n,
        p_down_vampire=float((fin < 0).mean()),
        mean_final=float(fin.mean()),
        sem_final=float(fin.std(ddof=1) / np.sqrt(n)),
        mean_mlen_300=float(am[:, w].mean()),
        transverse_share=share)
