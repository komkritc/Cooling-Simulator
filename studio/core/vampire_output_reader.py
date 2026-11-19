"""VAMPIRE output reader: seed enumeration + column-layout reconstruction (rule O1).

The column layout of `output_seed*.dat` is NOT assumed: it is reconstructed from
the deck's `output:` directive order with fixed block widths.  If the computed
width does not match the file, loading is refused (critical) unless the surplus
is only *trailing unmapped* columns, in which case the mapped columns are kept
and the surplus is recorded as 'unmapped extra columns' (amber note).

Validated conventions for the mapped columns:
  T = column index of output:temperature;  m_z signed = col7 * col6 for this
  deck family (magnetisation block = 3 unit-vector components, then
  magnetisation-length) — the same mapping the standalone scripts use.
Equilibration rows (T >= 799.5 K) are excluded identically (`cool` mask).
"""
from __future__ import annotations

import glob
import os
import re
from dataclasses import dataclass, field

import numpy as np

# fixed block widths per known output directive
OUT_WIDTHS = {
    "output:real-time": 1, "output:step": 1, "output:temperature": 1,
    "output:applied-field-strength": 1, "output:total-energy": 1,
    "output:magnetisation": 3, "output:magnetisation-length": 1,
    "output:mean-magnetisation-length": 1, "output:mean-susceptibility": 1,
    "unknown": 1,
}


@dataclass
class ColumnLayout:
    blocks: list[tuple[str, int, int]] = field(default_factory=list)  # (directive, start, width)
    extra_cols: list[int] = field(default_factory=list)               # unmapped trailing indices
    inferred: bool = False

    def index_of(self, directive: str) -> int | None:
        for d, start, _w in self.blocks:
            if d == directive:
                return start
        return None

    def as_list(self) -> list[dict]:
        return [{"directive": d, "start": s, "width": w} for d, s, w in self.blocks]


def layout_from_deck(deck) -> ColumnLayout:
    lay = ColumnLayout()
    i = 0
    for key in deck.directives:
        if not key.startswith("output:"):
            continue
        w = OUT_WIDTHS.get(key, OUT_WIDTHS["unknown"])
        lay.blocks.append((key, i, w))
        i += w
    return lay


@dataclass
class SeedData:
    seed: int
    path: str
    data: np.ndarray                      # raw rows
    layout: ColumnLayout
    t_col: int
    mdir_col: int                         # signed cos-theta_z (m_z direction)
    mlen_col: int                         # magnetisation length
    mx_col: int
    my_col: int
    cool_mask: np.ndarray                 # T < 799.5 (cooling rows only)

    def mz(self) -> np.ndarray:
        return self.data[:, self.mlen_col] * self.data[:, self.mdir_col]

    def temp(self) -> np.ndarray:
        return self.data[:, self.t_col]


def _seed_from_dir(d: str) -> int:
    m = re.search(r"seed_(\d+)", d)
    return int(m.group(1)) if m else -1


def find_seeds(runs_dir: str) -> list[str]:
    """All seed directories with a DONE marker (rule D1), sorted by seed id."""
    ds = [d for d in glob.glob(os.path.join(runs_dir, "seed_*"))
          if os.path.isfile(os.path.join(d, "DONE"))]
    return sorted(ds, key=_seed_from_dir)


def incomplete_seeds(runs_dir: str) -> list[str]:
    return [d for d in glob.glob(os.path.join(runs_dir, "seed_*"))
            if not os.path.isfile(os.path.join(d, "DONE"))]


def load_seed(seed_dir: str, layout: ColumnLayout,
              strict: bool = True) -> SeedData:
    dat = next(iter(sorted(glob.glob(os.path.join(seed_dir, "output_seed*.dat")))), None)
    if dat is None:
        raise FileNotFoundError(f"no output_seed*.dat in {seed_dir}")
    rows = []
    with open(dat, "r", errors="replace") as f:
        for ln in f:
            if ln.startswith("#") or not ln.strip():
                continue
            rows.append([float(x) for x in ln.replace(",", " ").split()])
    data = np.array(rows)
    if data.ndim != 2 or data.shape[0] < 10:
        raise ValueError(f"{dat}: too few data rows")

    lay = ColumnLayout(blocks=list(layout.blocks), inferred=layout.inferred)
    expected = sum(w for _d, _s, w in lay.blocks)
    width = data.shape[1]
    if width != expected:
        if width > expected:
            lay.extra_cols = list(range(expected, width))
            lay.inferred = True
        elif strict:
            raise ValueError(
                f"column-layout mismatch (rule O1): deck output directives imply "
                f"{expected} columns but {dat} has {width}")

    t_col = lay.index_of("output:temperature")
    mdir_col = mlen_col = mx_col = my_col = None
    for d, s, w in lay.blocks:
        if d == "output:magnetisation" and w == 3:
            mx_col, my_col, mdir_col = s, s + 1, s + 2
        elif d == "output:magnetisation-length":
            mlen_col = s
    if None in (t_col, mdir_col, mlen_col):
        raise ValueError(f"cannot locate T / magnetisation columns in {dat}")

    # plausibility of the mapped columns (part of rule O1)
    T = data[:, t_col]
    vec = data[:, [mx_col, my_col, mdir_col]]
    if not (200.0 <= np.nanmax(T) <= 2000.0):
        raise ValueError(f"{dat}: temperature column implausible (max {np.nanmax(T)})")
    if np.nanmax(np.abs(vec)) > 1.5:
        raise ValueError(f"{dat}: magnetisation unit-vector columns implausible")

    cool = T < 799.5
    return SeedData(_seed_from_dir(seed_dir), dat, data, lay,
                    t_col, mdir_col, mlen_col, mx_col, my_col, cool)


def header_provenance(seed_dir: str) -> dict:
    """Provenance block from the '#' header of the first output file."""
    info: dict[str, str] = {}
    dat = next(iter(sorted(glob.glob(os.path.join(seed_dir, "output_seed*.dat")))), None)
    if not dat:
        return info
    with open(dat, "r", errors="replace") as f:
        for ln in f:
            if not ln.startswith("#"):
                break
            m = re.match(r"#\s*(time|hostname|path|version|githash)\s*:\s*(.*?)\s*$", ln)
            if m:
                info[m.group(1)] = m.group(2)
    return info
