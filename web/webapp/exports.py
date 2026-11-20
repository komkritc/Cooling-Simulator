"""Export buttons: PNG, CSV, standalone .py, and the audit record (zipped).

All content is produced by the same studio.core code paths the desktop app uses;
the only web-specific step is turning files into bytes for st.download_button.
"""
from __future__ import annotations

import csv as _csv
import io
import os
import tempfile
import zipfile

import streamlit as st

from . import context as ctx
from . import runner, uploads


def png_bytes(fig, dpi: int = 200) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor=fig.get_facecolor())
    return buf.getvalue()


def csv_bytes(results) -> bytes:
    """Exactly the desktop SimpleWindow.save_csv() layout (raw, never smoothed)."""
    buf = io.StringIO()
    w = _csv.writer(buf)
    w.writerow(["rate_K_per_ns", "T_K", "m", "P_up", "m_s"])
    for rate, T, m, P, ms, Tc in results:
        for row in zip(T, m, P, ms):
            w.writerow([rate, *row])
    return buf.getvalue().encode()


def py_bytes(s: dict, results, run_params: dict) -> bytes:
    from studio.core.types import MEConfig
    from studio.core.code_export import generate_script
    from studio.core.lut_material import find_lut
    cfgs = [MEConfig(rate_K_per_ns=r[0], **run_params) for r in results]
    lut = find_lut()
    txt = generate_script(cfgs, "me_cooling_standalone.py", ctx.version(),
                          lut.name if lut else "lut_current_rf_1-10nm_dD0p1.csv")
    return txt.encode()


def _records_root() -> str:
    """Temp dir for records, kept for the process lifetime and removed on exit."""
    d = st.session_state.get("rec_root")
    if not d or not os.path.isdir(d):
        d = tempfile.mkdtemp(prefix="mecool_records_")
        uploads.track(d)
        st.session_state["rec_root"] = d
    return d


def record_zip_bytes(session, s: dict, rate: float, fig=None) -> tuple[bytes, str]:
    """audit_manager.save_record() into a temp dir, then zip it for download."""
    from studio.core import audit_manager
    res = runner.compare_vampire(session, s, rate)
    issues = session.validate()
    figures = {"figure.png": png_bytes(fig, dpi=200)} if fig is not None else None
    rec = audit_manager.save_record(session, res, issues, figures=figures,
                                    out_root=_records_root())
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(rec):
            for f in files:
                p = os.path.join(root, f)
                z.write(p, os.path.relpath(p, rec))
    return buf.getvalue(), os.path.basename(rec)


def render(pal: dict, s: dict, results, session, run_params) -> None:
    st.markdown("#### Export")
    c1, c2, c3, c4 = st.columns(4)
    fig = st.session_state.get("fig_obj")

    if results:
        c1.download_button("PNG (publication)",
                           data=png_bytes(fig, dpi=200) if fig is not None else b"",
                           file_name="me_cooling.png", mime="image/png",
                           disabled=not results, key="dl_png")
        c2.download_button("CSV (raw arrays)", data=csv_bytes(results),
                           file_name="me_cooling.csv", mime="text/csv", key="dl_csv")
        if run_params:
            c3.download_button("Standalone .py", data=py_bytes(s, results, run_params),
                               file_name="me_cooling_standalone.py", mime="text/x-python",
                               key="dl_py",
                               help="Self-contained, readable master-equation script; "
                                    "it also needs the LUT CSV in the same folder")
        else:
            c3.download_button("Standalone .py", data=b"", file_name="me_cooling_standalone.py",
                               disabled=True, key="dl_py")
    else:
        for col, label in ((c1, "PNG (publication)"), (c2, "CSV (raw arrays)"),
                           (c3, "Standalone .py")):
            col.download_button(label, data=b"", disabled=True)

    if session is not None and getattr(session, "seeds", None):
        rate = results[0][0] if results else session.rate_deck
        try:
            data, name = record_zip_bytes(session, s, rate, fig)
            c4.download_button("Record (.zip)", data=data, file_name=f"{name}.zip",
                               mime="application/zip", key="dl_rec",
                               help="record.json + arrays.csv + numbers.txt + figures + "
                                    "checksums.sha256 (audit_manager format)")
        except Exception as e:
            c4.download_button("Record (.zip)", data=b"", disabled=True)
            st.caption(f"record unavailable: {type(e).__name__}: {e}")
    else:
        c4.download_button("Record (.zip)", data=b"", disabled=True)
