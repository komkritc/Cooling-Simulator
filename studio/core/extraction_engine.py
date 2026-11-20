"""Extraction engine: merge deck + mat + log into a source-traceable ParameterTable.

Rules (plan §A.5):
  * every value carries file+line provenance;
  * missing unit suffix => ASSUMED status (validator reviews it);
  * same key from several sources with different values => CONFLICT (never silent);
  * derived values are computed downstream in mapping_engine, not here.
"""
from __future__ import annotations

import re

from .types import ParameterRecord, ParameterTable, Source, Status
from .vampire_input_parser import DeckParseResult
from .vampire_mat_parser import MatParseResult


def parse_log_atoms(log_path: str) -> tuple[int | None, dict]:
    """Extract atom count and version/githash from a VAMPIRE `log` file."""
    atoms, info = None, {}
    try:
        with open(log_path, "r", errors="replace") as f:
            for i, ln in enumerate(f, 1):
                m = re.search(r"makes up 100 % of all atoms \(?\s*(\d+)\s*atoms", ln)
                if m:
                    atoms, info["atoms_line"] = int(m.group(1)), i
                m = re.match(r".*Version\s+:\s*(\S+)", ln)
                if m:
                    info["version"] = m.group(1)
                m = re.match(r".*Githash\s+:\s*(\S+)", ln)
                if m:
                    info["githash"] = m.group(1)
    except OSError:
        pass
    return atoms, info


# VAMPIRE's native unit when a directive carries no `!unit` suffix. Still flagged
# ASSUMED (needs review) - only the conversion no longer crashes.
VAMPIRE_DEFAULT_UNIT = {"cooling_time": "s", "B_app": "T",
                        "cell_a": "A", "cell_b": "A", "cell_c": "A"}

def _rec_from_deck(d, key: str) -> ParameterRecord:
    st = Status.EXTRACTED if d.unit else Status.ASSUMED
    return ParameterRecord(key=key, value=d.value,
                           unit=d.unit or VAMPIRE_DEFAULT_UNIT.get(key, "unit:assumed"),
                           status=st,
                           sources=[Source(d.file, d.line, d.raw)])


def _rec_from_mat(e, key: str) -> ParameterRecord:
    st = Status.EXTRACTED if e.unit else Status.ASSUMED
    return ParameterRecord(key=key, value=e.value, unit=e.unit or "unit:assumed",
                           status=st, sources=[Source(e.file, e.line, e.raw)])


# deck directives -> friendly parameter keys
DECK_MAP = {
    "dimensions:particle-size": "grain_diameter",
    "dimensions:system-size-x": "system_size_x",
    "dimensions:system-size-y": "system_size_y",
    "dimensions:system-size-z": "grain_height",
    "dimensions:unit-cell-size-x": "cell_a",
    "dimensions:unit-cell-size-y": "cell_b",
    "dimensions:unit-cell-size-z": "cell_c",
    "create:crystal-structure": "crystal_structure",
    "material:file": "material_file",
    "sim:maximum-temperature": "T_start",
    "sim:minimum-temperature": "T_end",
    "sim:equilibration-temperature": "T_equil",
    "sim:cooling-time": "cooling_time",
    "sim:cooling-function": "cooling_function",
    "sim:program": "sim_program",
    "sim:integrator": "integrator",
    "sim:time-step": "time_step",
    "sim:equilibration-time-steps": "equil_steps",
    "sim:total-time-steps": "total_steps",
    "sim:time-steps-increment": "steps_increment",
    "sim:applied-field-strength": "B_app",
    "sim:applied-field-unit-vector": "field_direction",
    "sim:integrator-random-seed": "rng_seed",
}

MAT_MAP = {
    "damping-constant": "damping",
    "atomic-spin-moment": "atomic_moment",
    "uniaxial-anisotropy-constant": "K_u",
    "uniaxial-anisotropy-direction": "easy_axis",
    "relative-gamma": "gamma_relative",
    "material-name": "material_name",
    "exchange-matrix": "exchange_J",
}


def _merge(table: ParameterTable, rec: ParameterRecord):
    old = table.get(rec.key)
    if old is None:
        table.put(rec)
        return
    if old.value == rec.value:
        old.sources.extend(rec.sources)          # same value: keep all citations
        return
    if old.status is not Status.CONFLICT:
        old.status = Status.CONFLICT
        old.sources.extend(rec.sources)          # first source wins as value, both shown
        old.note = "conflicting values; GUI/user must pick one"


def extract(deck: DeckParseResult, mat: MatParseResult | None,
            log_path: str | None = None) -> ParameterTable:
    t = ParameterTable()

    for dkey, pkey in DECK_MAP.items():
        for d in deck.get(dkey):
            _merge(t, _rec_from_deck(d, pkey))
    if deck.first("create:cylinder"):
        d = deck.first("create:cylinder")
        _merge(t, ParameterRecord("grain_shape", "cylinder", "",
                                  Status.EXTRACTED, [Source(d.file, d.line, d.raw)]))

    if mat is not None:
        for mkey, pkey in MAT_MAP.items():
            for e in mat.entries.get(mkey, []):
                _merge(t, _rec_from_mat(e, pkey))

    if log_path:
        atoms, info = parse_log_atoms(log_path)
        if atoms is not None:
            ln = info.get("atoms_line")
            _merge(t, ParameterRecord("n_atoms", atoms, "", Status.EXTRACTED,
                                      [Source(log_path, ln, "atoms from VAMPIRE log")]))
        if "version" in info:
            _merge(t, ParameterRecord("vampire_version", info["version"], "",
                                      Status.EXTRACTED, [Source(log_path)]))
        if "githash" in info:
            _merge(t, ParameterRecord("vampire_githash", info["githash"], "",
                                      Status.EXTRACTED, [Source(log_path)]))

    t.unrecognised = [Source(d.file, d.line, d.raw) for d in deck.unknown] \
        + ([Source(e.file, e.line, e.raw) for e in mat.unknown] if mat else [])
    return t
