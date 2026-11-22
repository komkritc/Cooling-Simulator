#!/usr/bin/env python3
"""Master-Equation Magnetisation Simulator - web (Streamlit) entry point.

The physics is imported unchanged from ../studio/core (that package is Qt-free), so the
web app and the desktop app compute the same numbers from the same code.  Layout and
interaction follow studio/gui/simple_window.py; see G_web_gui_wireframe.md.

Local launch:  cd web && ./run_web.sh        (uses web/.venv)
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)                                          # webapp package
sys.path.insert(0, os.path.abspath(os.path.join(_ROOT, "..")))     # studio.core

# Which LUT CSV to use is resolved by webapp/context.py: web/data/ (mirror-repo copy),
# the repo root (a plain clone, e.g. Streamlit Cloud), then ME_Cooling_LUT/data.
# It must be resolved before studio.core.find_lut() is ever called.

import streamlit as st                                            # noqa: E402

from webapp import context as ctx                                 # noqa: E402
from webapp import actions, sidebar, main_tab, uploads            # noqa: E402

st.set_page_config(page_title="Master-Equation Magnetisation Simulator", layout="wide")


def main() -> None:
    ctx.check_pins()
    sidebar.ensure_seeded()
    st.session_state.setdefault("session", None)
    st.session_state.setdefault("me_results", [])
    st.session_state.setdefault("run_params", None)
    st.session_state.setdefault("notice", "")
    st.session_state.setdefault("vampire_info", "")

    pal = ctx.palette("dark" if st.session_state.get("wid_dark", ctx.DEFAULTS["dark"]) else "light")

    st.markdown("<div style='font-size:1.3rem;font-weight:700;line-height:1.2;"
                "text-align:center;white-space:nowrap'>"
                "Master-Equation Magnetisation Simulator</div>",
                unsafe_allow_html=True)

    s = sidebar.render(pal)

    if st.session_state["notice"]:
        st.error(st.session_state["notice"])

    main_tab.render(pal, s)

    # footer: environment facts, like the desktop status bar
    lut = ctx.load_lut_meta()
    st.caption(f"{ctx.version()} · matplotlib {ctx.MPL_VERSION} · {ctx.numpy_version()} · "
               f"LUT {lut.get('name', 'not found')} {lut.get('sha256', '')[:12]} · "
               f"ensemble {lut.get('ensemble', 'n/a')} · seed ensemble uses identical "
               f"initial conditions")
    uploads.cleanup_stale()


if __name__ == "__main__":
    main()
