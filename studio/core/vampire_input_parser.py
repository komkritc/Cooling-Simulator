"""Parser for VAMPIRE main input decks (`input`, `*.input`).

Format: `directive=value` lines, `#` comments, optional `!unit` suffix in comments.
Nothing is dropped: every directive is stored with file+line provenance, and
directives the app does not understand go to `unknown` (shown in the GUI's
"unrecognised parameters" table, per plan §A.5.4).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .units import parse_declared_unit


@dataclass
class Directive:
    key: str
    raw_value: str
    value: float | str | None
    unit: str          # canonical declared unit ('' if none)
    unit_raw: str      # raw `!xx` suffix text ('' if none)
    file: str
    line: int
    raw: str


def _coerce(raw: str):
    raw = raw.strip()
    if raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        pass
    low = raw.lower()
    if low in ("true", "false"):
        return low == "true"
    if "," in raw and all(_coerce(p) is not None for p in raw.split(",")):
        return tuple(float(p) for p in raw.split(","))
    return raw


@dataclass
class DeckParseResult:
    directives: dict[str, list[Directive]] = field(default_factory=dict)
    unknown: list[Directive] = field(default_factory=list)
    header_notes: list[str] = field(default_factory=list)   # metadata comment lines
    path: str = ""

    def get(self, key: str) -> list[Directive]:
        return self.directives.get(key, [])

    def first(self, key: str):
        d = self.get(key)
        return d[0] if d else None


def parse_deck(path: str, known_keys: set[str] | None = None) -> DeckParseResult:
    """Parse one deck file.  `known_keys` marks directives the extraction engine uses."""
    res = DeckParseResult(path=str(path))
    with open(path, "r", errors="replace") as f:
        for i, ln in enumerate(f, start=1):
            s = ln.split("#", 1)
            body, comment = s[0], (s[1] if len(s) > 1 else "")
            s = ln.strip()
            if s.startswith("#"):
                m = re.match(r"#\s*(generator|protocol|case|grain|schedule|schedule.*|cooling_time.*):?\s*(.*)",
                             s)
                if m:
                    res.header_notes.append(s.lstrip("# ").rstrip())
                continue
            if not body.strip():
                continue
            if "=" not in body:
                # flag-only directive (e.g. `create:cylinder`, `output:real-time`)
                key = body.split("!")[0].strip()
                d = Directive(key, "", None, "", "", str(path), i, ln.rstrip())
                if known_keys is None or key in known_keys or ":" in key:
                    res.directives.setdefault(key, []).append(d)
                else:
                    res.unknown.append(d)
                continue
            key, raw = body.split("=", 1)
            key = key.strip()
            raw_val = raw.split("#", 1)[0].split("!")[0].strip()
            # the `!unit` suffix lives after `!` anywhere on the line
            if "!" in ln:
                unit, unit_raw = parse_declared_unit("!" + ln.split("!", 1)[1])
            else:
                unit, unit_raw = "", ""
            d = Directive(key, raw_val, _coerce(raw_val), unit, unit_raw,
                          str(path), i, ln.rstrip())
            if known_keys is None or key in known_keys:
                res.directives.setdefault(key, []).append(d)
            else:
                res.unknown.append(d)
    return res


# Directives the extraction engine consumes (everything else -> unknown table)
DECK_KEYS = {
    "create:cylinder", "create:crystal-structure",
    "dimensions:unit-cell-size-x", "dimensions:unit-cell-size-y",
    "dimensions:unit-cell-size-z", "dimensions:system-size-x",
    "dimensions:system-size-y", "dimensions:system-size-z",
    "dimensions:particle-size", "material:file",
    "sim:program", "sim:integrator", "sim:cooling-function",
    "sim:maximum-temperature", "sim:minimum-temperature",
    "sim:equilibration-temperature", "sim:cooling-time",
    "sim:time-step", "sim:equilibration-time-steps",
    "sim:total-time-steps", "sim:time-steps-increment",
    "sim:applied-field-strength", "sim:applied-field-unit-vector",
    "sim:integrator-random-seed",
    "output:real-time", "output:step", "output:temperature",
    "output:applied-field-strength", "output:total-energy",
    "output:magnetisation", "output:magnetisation-length",
    "output:mean-magnetisation-length", "output:mean-susceptibility",
    "screen:real-time", "screen:temperature", "screen:mean-magnetisation-length",
}
