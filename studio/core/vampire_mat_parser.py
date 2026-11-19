"""Parser for VAMPIRE material files (`*.mat`): `material[N]:key=value` lines."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .units import parse_declared_unit


@dataclass
class MatEntry:
    key: str            # e.g. 'damping-constant'
    block: int          # material[1] -> 1
    raw_value: str
    value: float | str | None
    unit: str
    file: str
    line: int
    raw: str


MAT_KEYS = {
    "material-name", "damping-constant", "atomic-spin-moment",
    "uniaxial-anisotropy-constant", "uniaxial-anisotropy-direction",
    "relative-gamma", "minimum-height", "maximum-height",
}


def _coerce(raw: str):
    raw = raw.strip()
    try:
        return float(raw)
    except ValueError:
        pass
    if "," in raw:
        try:
            return tuple(float(p) for p in raw.split(","))
        except ValueError:
            pass
    return raw


@dataclass
class MatParseResult:
    entries: dict[str, list[MatEntry]] = field(default_factory=dict)
    unknown: list[MatEntry] = field(default_factory=list)
    path: str = ""

    def first(self, key: str):
        e = self.entries.get(key, [])
        return e[0] if e else None


_LINE = re.compile(r"^\s*material\[(\d+)\]\s*:\s*([\w-]+)\s*=\s*(.+?)\s*$")


def parse_mat(path: str) -> MatParseResult:
    res = MatParseResult(path=str(path))
    with open(path, "r", errors="replace") as f:
        for i, ln in enumerate(f, start=1):
            if ln.strip().startswith("#") or not ln.strip():
                continue
            m = _LINE.match(ln.split("#")[0])
            if not m:
                continue
            block, key, raw = int(m.group(1)), m.group(2), m.group(3)
            raw_val = raw.split("!")[0].strip()
            unit, _ = parse_declared_unit("!" + ln.split("!", 1)[1]) if "!" in ln else ("", "")
            e = MatEntry(key, block, raw_val, _coerce(raw_val), unit,
                         str(path), i, ln.rstrip())
            if key.startswith("exchange-matrix"):
                res.entries.setdefault("exchange-matrix", []).append(e)
            elif key in MAT_KEYS:
                res.entries.setdefault(key, []).append(e)
            else:
                res.unknown.append(e)
    return res
