"""Reusable GUI widgets for the Comparison Studio."""
from __future__ import annotations

import io

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (QFrame, QLabel, QVBoxLayout, QHBoxLayout, QWidget,
                               QTableWidget, QTableWidgetItem, QHeaderView,
                               QDialog, QPushButton, QScrollArea, QPlainTextEdit)

from studio.core.types import Status
from studio.gui import theme

# ---------------------------------------------------------------- cards

class GroupCard(QFrame):
    """Numbered section card with a coloured header row and body layout."""

    def __init__(self, number: int, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.card_no = number
        head = QHBoxLayout()
        num = QLabel(f"{number}.")
        num.setObjectName("cardHeadNum")
        t = QLabel(title)
        t.setObjectName("cardHead")
        head.addWidget(num)
        head.addWidget(t)
        self.head_extra = QHBoxLayout()      # right-aligned widgets (badges)
        head.addStretch(1)
        head.addLayout(self.head_extra)
        self.body = QVBoxLayout()
        root = QVBoxLayout(self)
        root.addLayout(head)
        root.addLayout(self.body)
        root.setContentsMargins(14, 10, 14, 12)
        root.setSpacing(8)


class StepCard(QFrame):
    def __init__(self, number: int, title: str, desc: str, parent=None):
        super().__init__(parent)
        self.setObjectName("stepCard")
        lay = QHBoxLayout(self)
        n = QLabel(str(number))
        n.setObjectName("stepNum")
        n.setFixedWidth(18)
        box = QVBoxLayout()
        box.setSpacing(1)
        t = QLabel(title)
        t.setObjectName("stepTitle")
        d = QLabel(desc)
        d.setObjectName("stepDesc")
        d.setWordWrap(True)
        box.addWidget(t)
        box.addWidget(d)
        lay.addWidget(n)
        lay.addLayout(box)
        lay.setContentsMargins(10, 8, 10, 8)


# ---------------------------------------------------------------- chips

_CHIP = {
    Status.EXTRACTED: ("● Extracted", theme.GREEN),
    Status.DERIVED: ("⚙ Derived", theme.BLUE),
    Status.CONFLICT: ("▲ Conflict", theme.AMBER),
    Status.ASSUMED: ("▲ Assumed", theme.AMBER),
    Status.MISSING: ("✕ Missing", theme.RED),
    Status.USER: ("✎ Edited", theme.BLUE),
}


def chip(status: Status) -> QLabel:
    text, colour = _CHIP[status]
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color:{colour}; font-weight:600;")
    return lbl


def badge(text: str, colour: str = theme.GREEN) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color:{colour}; border:1px solid {colour}; border-radius:10px;"
        f"padding:2px 10px; font-size:11px; font-weight:700;")
    return lbl


# ---------------------------------------------------------------- param table

class ParameterTable(QTableWidget):
    """Parameter | Value | Unit | Source | chip  (click a row -> source viewer)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(5)
        self.setHorizontalHeaderLabels(
            ["Parameter", "Value", "Unit", "Source", "Status"])
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        self._records: list = []

    def set_records(self, records):
        self._records = list(records)
        self.setRowCount(len(self._records))
        for row, r in enumerate(self._records):
            src = r.sources[0] if r.sources else None
            val = r.value
            valtxt = f"{val:g}" if isinstance(val, float) else str(val)
            unit = "" if r.unit == "unit:assumed" else r.unit
            cells = [r.key.replace("_", " "), valtxt, unit or "\u2014",
                     (src.file.rsplit("/", 1)[-1] + (f":{src.line}" if src.line else ""))
                     if src else "—"]
            for col, txt in enumerate(cells):
                item = QTableWidgetItem(txt)
                item.setToolTip(src.file if src else "")
                self.setItem(row, col, item)
            self.setCellWidget(row, 4, chip(r.status))

    def record_at(self, row: int):
        return self._records[row] if 0 <= row < len(self._records) else None


# ---------------------------------------------------------------- dialogs

def mathtext_pixmap(latex_lines: list[str], width_px: int = 620,
                    font_size: int = 13) -> QPixmap:
    """Render a block of mathtext lines to a QPixmap (no LaTeX needed)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    n = len(latex_lines)
    fig = plt.Figure(figsize=(width_px / 100, 0.42 * n + 0.25), dpi=140)
    fig.patch.set_facecolor(theme.BG_INPUT)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    for i, line in enumerate(reversed(latex_lines)):
        ax.text(0.02, (i + 0.5) / n, line, color="#cfe0ff", fontsize=font_size)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=theme.BG_INPUT)
    plt.close(fig)
    img = QImage.fromData(buf.getvalue())
    return QPixmap.fromImage(img)


ME_EQUATIONS = [
    r"$\langle m_z\rangle=m_s(T)\,[2P_+-1]$"""
    r"$\qquad P\leftarrow P_{eq}+(P_0-P_{eq})\,e^{-\Gamma(T)\Delta t}$",
    r"$\Gamma=2\alpha_2\omega_1\sqrt{\sigma/\pi}\;e^{-\sigma(1-H/H_K)^2(1-r/2)}$"""
    r"$\;(\chi_L\leq\chi_T)$",
    r"$\omega_1=\gamma/\chi_\perp(T)$"""
    r"$\qquad\sigma=\frac{\mu_0 M_s^2 m_s^2 V}{2\chi_\perp k_BT}$"""
    r"$\qquad r=2\chi_L/\chi_T$",
    r"$\alpha_2=\frac{\lambda}{m_s}\left[\frac{\tanh q}{q}-\frac{T}{3T_C}\right]$"""
    r"$q=\frac{3T_C m_s}{2(S+1)T}$"""
    r"$\qquad P_{eq}=\frac{1}{2}\left[1+\tanh\frac{\mu_0 V M_s m_s H}{k_BT}\right]$",
    r"$m_s,\chi_\perp,\chi_L,T_C$ from the RF surrogate; $V=n_{atoms}v_{cell}$; "
    r"field-lowered barrier for $T<T_C$ (Roy formalism)",
]


class EquationsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Master Equation — two-state (Roy formalism)")
        self.resize(760, 360)
        lay = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        v = QVBoxLayout(body)
        lbl = QLabel()
        lbl.setPixmap(mathtext_pixmap(ME_EQUATIONS))
        v.addWidget(lbl)
        note = QLabel("Formulas reproduced verbatim from the validated module "
                      "derived/me_B_roy.py (physics frozen — see PLAN.md).")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{theme.FG_DIM}")
        v.addWidget(note)
        v.addStretch(1)
        scroll.setWidget(body)
        lay.addWidget(scroll)


class SourceViewer(QDialog):
    """Show the raw file with the cited line highlighted, plus full source list."""

    def __init__(self, record, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Source — {record.key}")
        self.resize(820, 460)
        lay = QVBoxLayout(self)
        for src in record.sources:
            head = QLabel(f"{src.file}" + (f"  line {src.line}" if src.line else ""))
            head.setStyleSheet(f"color:{theme.BLUE}; font-weight:600")
            lay.addWidget(head)
            txt = QPlainTextEdit()
            txt.setReadOnly(True)
            try:
                with open(src.file, encoding="utf-8", errors="replace") as fh:
                    lines = fh.read().splitlines()
                if src.line:
                    lo = max(0, src.line - 15)
                    window = [f"{i+1:>5} | {ln}" for i, ln in
                              enumerate(lines[lo:src.line + 14], start=lo)]
                    txt.setPlainText("\n".join(window))
                else:
                    txt.setPlainText("\n".join(lines[:80]))
            except OSError as exc:
                txt.setPlainText(f"(cannot read file: {exc})")
            lay.addWidget(txt)
        if record.note:
            lay.addWidget(QLabel(record.note))


# ---------------------------------------------------------------- worker

class OpenWorker(QThread):
    """Parse a run directory into an AnalysisSession (no solving)."""

    done_ok = Signal(object)          # AnalysisSession
    done_err = Signal(str)

    def __init__(self, data_dir: str, parent=None):
        super().__init__(parent)
        self.data_dir = data_dir

    def run(self):
        try:
            from studio.core.session import AnalysisSession
            s = AnalysisSession(self.data_dir)
            s.validation_issues = s.validate()
            self.done_ok.emit(s)
        except Exception as exc:                              # noqa: BLE001
            self.done_err.emit(f"{type(exc).__name__}: {exc}")


class RunWorker(QThread):
    """Run ME solve + statistics on an already-parsed session."""

    done_ok = Signal(object)          # ComparisonResult
    done_err = Signal(str)

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

    def run(self):
        try:
            res = self.session.run_comparison()
            self.done_ok.emit(res)
        except Exception as exc:                              # noqa: BLE001
            self.done_err.emit(f"{type(exc).__name__}: {exc}")
