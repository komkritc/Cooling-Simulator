"""Web-app context: paths, version pins, LUT metadata, settings defaults.

Version pins here are a runtime check only; the real pins live in ../requirements.txt
(desktop) and web/requirements.txt (web).  matplotlib MUST equal the pinned version or
figure identity with the desktop app cannot be claimed.

DEFAULTS are the exact SimpleWindow widget defaults (studio/gui/simple_window.py
lines 74-160), so the web app starts in the same state as the desktop app.
"""
from __future__ import annotations

import functools
import hashlib
import io
import os
from pathlib import Path

from studio.core.lut_material import LUT_NAME
from studio.gui import theme

WEB_DIR = Path(__file__).resolve().parent.parent          # .../app/web
REPO_DIR = WEB_DIR.parent                                 # the git repo root


LUT_ENV_FROM_OS = os.environ.get("ME_LUT_FILE")   # as launched, before we touch it


def _ensure_lut_env() -> str:
    """Make sure ME_LUT_FILE points at a LUT that this checkout really contains.

    studio.core.find_lut() only looks at $ME_LUT_FILE, <repo>/../data and <repo>/data.
    In this workspace the LUT also lives one level above the repo (ME_Cooling_LUT/data),
    which is why the desktop app finds it - but a plain clone (that is exactly what
    Streamlit Cloud gets) has the CSV at the repo root, and that is not one of the
    candidates.  So the web app resolves it itself, in order of preference.
    """
    if LUT_ENV_FROM_OS and Path(LUT_ENV_FROM_OS).is_file():
        return LUT_ENV_FROM_OS          # an explicit override always wins
    for cand in (WEB_DIR / "data" / LUT_NAME,             # standalone-mirror location
                 REPO_DIR / LUT_NAME,                     # plain clone: CSV at repo root
                 REPO_DIR.parent / "data" / LUT_NAME):    # ME_Cooling_LUT/data (workspace)
        if cand.is_file():
            os.environ["ME_LUT_FILE"] = str(cand)
            return str(cand)
    return ""                                             # no LUT: find_lut() stays empty


LUT_PATH = _ensure_lut_env()
SAMPLE_DATA = WEB_DIR / "sample_data"
# folder handed to AnalysisSession, same layout as a desktop "Load run" folder
SAMPLE_ROOT = SAMPLE_DATA / "vampire_damp0p05_D4nm"
WEB_DATA = WEB_DIR / "data"                                # mirror-repo LUT location

MPL_VERSION = "3.11.1"

# Figure of SimpleWindow (simple_window.py:211): 7x5 inches at 100 dpi, one axis.
PLOT_FIG_W, PLOT_FIG_H, PLOT_DPI = 7.0, 5.0, 100

DARK = False                      # the web app starts light (sidebar can switch to dark)

# Line cycle: SimpleWindow.COLORS (Okabe-Ito colour-blind-safe set).
COLORS = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#000000"]


def version() -> str:
    """web/VERSION if present (the mirror of the desktop tag), else v1.0-web."""
    p = WEB_DIR / "VERSION"
    try:
        return p.read_text().strip()
    except OSError:
        return "v1.0-web"


def numpy_version() -> str:
    from importlib.metadata import version as _v      # numpy 2.x dropped np.__version__
    return f"numpy {_v('numpy')}"


def check_pins() -> None:
    """Refuse to run with a matplotlib other than the one the audit used."""
    import matplotlib
    if matplotlib.__version__ != MPL_VERSION:
        raise RuntimeError(
            f"matplotlib {matplotlib.__version__} != pinned {MPL_VERSION}: figure "
            "identity with the desktop app cannot be claimed. Install "
            "web/requirements.txt into web/.venv.")


# ---------------------------------------------------------------- settings ----
# Key names are chosen to match runner.build_config()/run_params() inputs.
DEFAULTS: dict = dict(
    rates_text="500",
    d_nm=4.0, t0=800.0, t1=300.0, b_T=1.00531, damp=0.05,
    atoms=4602, a_A=2.72, c_A=3.85, mu_mub=3.23, gamma_rel=1.0, dT=1.0, p0=0.5,
    damp_use=0,                     # 0 = "λ = α (validated)", 1 = "λ = α/(1+α²)"
    sg_on=True, sg_win=15.0, sg_poly=3,        # smoothing on by default on the web
    grid=True, params_on=True, dark=False, invert_x=True, import_vampire=True,
    vpath="",
)


def rates_from_text(text: str) -> list[float]:
    """SimpleWindow._rates() parsing; returns [] on bad input so the caller can
    show the same message in a status line instead of a dialog."""
    try:
        r = [float(x) for x in text.replace(";", ",").split(",") if x.strip()]
    except ValueError:
        return []
    if not r or any(x <= 0 for x in r):
        return []
    return r


RATE_MSG = "Enter cooling rate(s) in K/ns, e.g. 500 or 100, 500, 1000"
T_MSG = "Start temperature must be above the end temperature"


def sample_run_dirs() -> list[str]:
    """Bundled example run folders ordered by rate; [] when none are present.

    Two layouts are supported:
      sample_data/vampire_damp0p05_D4nm/cooling_T800/runs/rate_*Kns  (old)
      sample_data/rate_*Kns                                          (new)
    """
    runs = SAMPLE_ROOT / "cooling_T800" / "runs"
    if not runs.is_dir():
        runs = SAMPLE_DATA
    out = [str(d) for d in runs.iterdir() if d.is_dir() and d.name.startswith("rate_")]
    return sorted(out, key=lambda p: float(p.rsplit("rate_", 1)[1][:-len("Kns")]))


def sample_label(run_dir: str) -> str:
    """Short readable name for a bundled run: '500 K/ns (25 seeds)' style."""
    name = Path(run_dir).name
    rate = name[len("rate_"):-len("Kns")] if name.startswith("rate_") else name
    try:
        n = len([d for d in Path(run_dir).iterdir() if (d / "DONE").is_file()])
    except OSError:
        n = 0
    return f"{rate} K/ns  ({n} seeds)"


def palette(mode: str) -> dict:
    theme.set_mode("dark" if mode == "dark" else "light")
    return {k: getattr(theme, k) for k in
            ("BG", "BG_PANEL", "BG_PANEL2", "BG_INPUT", "BORDER", "FG", "FG_DIM",
             "GREEN", "GREEN_DK", "BLUE", "AMBER", "RED", "TITLE_BLUE")}


@functools.lru_cache(maxsize=4)
def load_lut_meta(path: str | None = None) -> dict:
    """Header comments + sha256 of the LUT actually used (the solver loads the numbers)."""
    from studio.core.lut_material import find_lut
    p = path or (str(find_lut()) if find_lut() else "")
    if not p or not os.path.isfile(p):
        return {}
    try:
        with io.open(p, "r", encoding="utf-8") as f:
            meta = {}
            for line in f:
                if not line.startswith("#"):
                    break
                k, _, v = line.lstrip("# ").partition("=")
                if _:
                    meta[k.strip()] = v.strip()
            meta["path"] = p
            meta["name"] = os.path.basename(p)
        with open(p, "rb") as f:
            h = hashlib.sha256()
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
            meta["sha256"] = h.hexdigest()
        return meta
    except OSError:
        return {}
