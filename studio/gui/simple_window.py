"""Simple one-screen GUI: set ME parameters -> Run -> plot.

* ME runs alone from manually entered parameters (defaults = FePt 4 nm study).
* "Load VAMPIRE run" is optional: it fills the form from the run's deck/mat and
  overlays the VAMPIRE seed mean on the plot.
The physics is the unchanged studio.core solver.
"""
from __future__ import annotations

import csv
import math
import os
from pathlib import Path

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as Canvas
from matplotlib.figure import Figure
from PySide6.QtCore import QSettings, Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (QTabWidget, QScrollArea, QFrame, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMainWindow, QMessageBox, QPushButton, QSpinBox,
                               QVBoxLayout, QWidget)

from ..core.mapping_engine import me_inputs_for_solver
from ..core.me_solver import MESolver
from ..core.lut_material import LutMaterial, find_lut
from ..core.types import MEConfig
from . import theme

STANDALONE = Path(__file__).resolve().parents[2]
# Okabe-Ito colour-blind-friendly palette and fonts: same as the exported .py plot (me_cooling.py)
COLORS = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#000000"]
import matplotlib as _mpl
_mpl.rcParams.update({"font.family": "sans-serif",
                      "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
                      "mathtext.fontset": "dejavusans"})


class Worker(QThread):
    ok = Signal(object)
    err = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            self.ok.emit(self.fn())
        except Exception as e:                      # surfaced to the user, not swallowed
            self.err.emit(f"{type(e).__name__}: {e}")


def dspin(lo, hi, val, dec=3, step=None, suffix=""):
    w = QDoubleSpinBox()
    w.setRange(lo, hi); w.setDecimals(dec); w.setValue(val); w.setSuffix(suffix)
    w.setKeyboardTracking(False)
    if step:
        w.setSingleStep(step)
    return w


class SimpleWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        from ..version import get_version
        self.setWindowTitle(f"ME Cooling Simulator {get_version()}")
        self.resize(1160, 960)
        self.session = None          # optional loaded VAMPIRE run
        self.results = []            # [(rate, T, m, P, ms, Tc)]
        self._worker = None
        self._ml = None

        # ---------------- form ----------------
        self.ed_rates = QLineEdit("500")
        self.ed_rates.setToolTip("One or several cooling rates in K/ns, comma separated (e.g. 100, 500, 1000)")
        self.sp_d = dspin(1, 10, 4.0, 2, 0.1, " nm")
        self.sp_t0 = dspin(1, 2000, 800, 0, 50, " K")
        self.sp_t1 = dspin(1, 2000, 300, 0, 50, " K")
        self.sp_b = dspin(0, 50, 1.00531, 5, 0.1, " T")
        self.sp_damp = dspin(0.0001, 1, 0.05, 4, 0.01)

        form = QFormLayout()
        self.bt_rm = QPushButton("\u2212100"); self.bt_rp = QPushButton("+100")
        for b_, d_ in ((self.bt_rm, -100), (self.bt_rp, 100)):
            b_.setFixedWidth(64); b_.setToolTip(f"{d_:+d} K/ns on every rate in the box (minimum 1), then re-run")
            b_.clicked.connect(lambda _=False, d=d_: self._bump_rates(d))
        row_rate = QHBoxLayout(); row_rate.setContentsMargins(0, 0, 0, 0)
        row_rate.addWidget(self.ed_rates, 1); row_rate.addWidget(self.bt_rm); row_rate.addWidget(self.bt_rp)
        form.addRow("Cooling rate(s) K/ns", row_rate)
        form.addRow("Grain diameter", self.sp_d)
        form.addRow("Start temperature", self.sp_t0)
        form.addRow("End temperature", self.sp_t1)
        form.addRow("Applied field B", self.sp_b)
        form.addRow("Damping λ", self.sp_damp)

        # advanced (hidden until toggled)
        self.sp_atoms = QSpinBox(); self.sp_atoms.setRange(1, 10**9); self.sp_atoms.setValue(4602)
        self.bt_atoms = QPushButton("from D")
        self.bt_atoms.setToolTip("Set atom count from a sphere of the chosen diameter")
        self.bt_atoms.clicked.connect(self._atoms_from_d)
        row_atoms = QHBoxLayout(); row_atoms.addWidget(self.sp_atoms); row_atoms.addWidget(self.bt_atoms)
        self.sp_a = dspin(0.5, 20, 2.72, 3, 0.01, " Å")
        self.sp_c = dspin(0.5, 20, 3.85, 3, 0.01, " Å")
        self.sp_mu = dspin(0.01, 20, 3.23, 3, 0.1, " μB")
        self.sp_gam = dspin(0.01, 10, 1.0, 3, 0.1)
        self.sp_dT = dspin(0.01, 20, 1.0, 2, 0.5, " K")
        self.sp_p0 = dspin(0, 1, 0.5, 3, 0.05)
        self.cb_damp = QComboBox()
        self.cb_damp.addItems(["λ = α (validated)", "λ = α/(1+α²)"])
        self.adv = QWidget(); af = QFormLayout(self.adv); af.setContentsMargins(0, 0, 0, 0)
        af.addRow("Atoms in grain", row_atoms)
        af.addRow("Cell a", self.sp_a); af.addRow("Cell c", self.sp_c)
        af.addRow("Atomic moment", self.sp_mu); af.addRow("γ (relative)", self.sp_gam)
        af.addRow("T step", self.sp_dT); af.addRow("Initial P₀", self.sp_p0)
        af.addRow("Damping use", self.cb_damp)
        self.adv.setVisible(False)
        self.cb_adv = QCheckBox("Show more parameters")
        self.cb_adv.toggled.connect(self.adv.setVisible)

        self.bt_run = QPushButton("Run ME"); self.bt_run.setObjectName("runBtn")
        self.bt_run.setMinimumHeight(40); self.bt_run.clicked.connect(self.run_me)
        self.settings = QSettings("CoolingModelComparison", "MECoolingSimulator")
        self.cb_sg = QCheckBox("Smooth (SG)")
        self.cb_sg.setToolTip("Savitzky-Golay smoothing of the plotted curves only (CSV export stays raw)")
        self.cb_sg.setChecked(str(self.settings.value("sg_on", "false")).lower() == "true")
        self.sp_sgw = dspin(1, 200, float(self.settings.value("sg_win", 15)), 0, 5, " K")
        self.sp_sgw.setToolTip("Smoothing window width in K")
        self.sp_sgp = QSpinBox(); self.sp_sgp.setRange(1, 7)
        self.sp_sgp.setValue(int(self.settings.value("sg_poly", 3)))
        self.sp_sgp.setToolTip("Polynomial order")
        self.sp_sgp.setPrefix("order ")
        for w_ in (self.sp_sgw, self.sp_sgp):
            w_.setEnabled(self.cb_sg.isChecked())
        self.cb_sg.toggled.connect(self._sg_changed)
        self.sp_sgw.valueChanged.connect(self._sg_changed)
        self.sp_sgp.valueChanged.connect(self._sg_changed)
        # grain diameter and applied field B: every change (arrow click, typed value) re-runs the ME after a short debounce
        self._d_timer = QTimer(self); self._d_timer.setSingleShot(True); self._d_timer.setInterval(300)
        self._d_timer.timeout.connect(self._d_autorun)
        for _sp in (self.sp_d, self.sp_b):
            _sp.valueChanged.connect(lambda _v: self._d_timer.start())
        self.cb_grid = QCheckBox("Show grid")
        self.cb_grid.setChecked(str(self.settings.value("show_grid", "true")).lower() == "true")
        self.cb_grid.toggled.connect(self._grid_toggled)
        self.cb_par = QCheckBox("Show parameters on plot")
        self.cb_par.setToolTip("Print the ME / VAMPIRE parameters under the plot (and in saved PNG)")
        self.cb_par.setChecked(str(self.settings.value("show_params", "true")).lower() == "true")
        self.cb_par.toggled.connect(self._params_toggled)
        self._par_artists = []
        self.cb_dark = QCheckBox("Dark theme")
        self.cb_dark.setChecked(theme.MODE == "dark")
        self.cb_dark.toggled.connect(self._theme_changed)
        self.cb_inv = QCheckBox("Invert x-axis (high T on left)")
        self.cb_inv.setChecked(str(self.settings.value("invert_x", "true")).lower() == "true")
        self.cb_inv.toggled.connect(self._invert_changed)
        self.ed_vpath = QLineEdit(str(self.settings.value("vampire_path", "")))
        self.ed_vpath.setPlaceholderText("VAMPIRE run folder, e.g. …/runs/rate_500Kns (optional)")
        self.ed_vpath.setToolTip("Full path of the VAMPIRE run folder (editable; Enter = load). Remembered.")
        self.ed_vpath.returnPressed.connect(self.load_typed)
        self.bt_browse = QPushButton("Browse…"); self.bt_browse.clicked.connect(self.load_vampire)
        self.bt_load = QPushButton("Load"); self.bt_load.clicked.connect(self.load_typed)
        self.bt_clear = QPushButton("Remove"); self.bt_clear.clicked.connect(self.clear_vampire)
        self.bt_clear.setVisible(False)
        row_v = QHBoxLayout()
        for b in (self.bt_browse, self.bt_load, self.bt_clear):
            row_v.addWidget(b)
        self.cb_vparams = QCheckBox("Import VAMPIRE settings")
        self.cb_vparams.setToolTip("Fill diameter, temperatures, field, damping, atoms, cell, moment and \u03b3 "
                                   "from the loaded VAMPIRE run (the ME cooling rate stays as typed)")
        self.cb_vparams.setChecked(str(self.settings.value("import_vampire", "true")).lower() == "true")
        self.cb_vparams.toggled.connect(self._import_toggled)
        self.lbl_v = QLabel(""); self.lbl_v.setWordWrap(True); self.lbl_v.setStyleSheet(f"color:{theme.FG_DIM}")
        self.bt_png = QPushButton("Save PNG"); self.bt_png.clicked.connect(self.save_png)
        self.bt_csv = QPushButton("Save CSV"); self.bt_csv.clicked.connect(self.save_csv)
        self.bt_py = QPushButton("Export .py"); self.bt_py.clicked.connect(self.export_py)
        self.bt_py.setToolTip("Save a self-contained, readable Python script of this master-equation run to share")
        row_save = QHBoxLayout()
        for b in (self.bt_png, self.bt_csv, self.bt_py):
            row_save.addWidget(b)
        self.lbl_res = QLabel("Set parameters and press Run ME.")
        self.lbl_res.setWordWrap(True); self.lbl_res.setTextInteractionFlags(Qt.TextSelectableByMouse)

        left = QVBoxLayout()
        left.addLayout(form); left.addWidget(self.cb_adv); left.addWidget(self.adv)
        row_opt = QHBoxLayout(); row_opt.addWidget(self.cb_dark); row_opt.addWidget(self.cb_grid)
        row_opt2 = QHBoxLayout(); row_opt2.addWidget(self.cb_par)
        left.addWidget(self.cb_inv); left.addLayout(row_opt); left.addLayout(row_opt2)
        row_sg = QHBoxLayout(); row_sg.addWidget(self.cb_sg)
        row_sg.addWidget(self.sp_sgw); row_sg.addWidget(self.sp_sgp)
        left.addLayout(row_sg)
        left.addWidget(self.bt_run)
        left.addWidget(QLabel("VAMPIRE data (optional)"))
        left.addWidget(self.ed_vpath); left.addLayout(row_v)
        left.addWidget(self.cb_vparams); left.addWidget(self.lbl_v)
        left.addWidget(self.lbl_res)
        self.card = QFrame(); self.card.setObjectName("ratioCard")
        cl = QVBoxLayout(self.card); cl.setContentsMargins(8, 6, 8, 6); cl.setSpacing(3)
        self.card_title = QLabel(); self.card_me = QLabel(); self.card_vm = QLabel(); self.card_status = QLabel()
        for l_ in (self.card_title, self.card_me, self.card_vm, self.card_status):
            l_.setWordWrap(True); l_.setTextFormat(Qt.RichText)
            l_.setTextInteractionFlags(Qt.TextSelectableByMouse); cl.addWidget(l_)
        left.addWidget(self.card)
        left.addStretch(1); left.addLayout(row_save)
        inner = QWidget(); inner.setLayout(left)
        self.left_scroll = lw = QScrollArea(); lw.setWidget(inner); lw.setWidgetResizable(True)
        lw.setFrameShape(QFrame.NoFrame); lw.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lw.setFixedWidth(380)          # scrolls vertically if the panel is taller than the window

        # ---------------- plot ----------------
        self.fig = Figure(figsize=(7, 5), dpi=100, facecolor=theme.BG_PANEL)
        self.canvas = Canvas(self.fig)
        self._rl_timer = QTimer(self); self._rl_timer.setSingleShot(True); self._rl_timer.setInterval(120)
        self._rl_timer.timeout.connect(self._on_resized)
        self.canvas.mpl_connect("resize_event", lambda e: self._rl_timer.start())
        self.ax = self.fig.add_subplot(111)
        self._style_axes()
        self.canvas.draw_idle()

        root = QWidget(); h = QHBoxLayout(root); h.addWidget(lw); h.addWidget(self.canvas, 1)
        # tabs: existing page unchanged as tab 1
        from .psw_tab import PswTestTab
        self.tabs = QTabWidget(); self.tabs.setDocumentMode(True)
        self.tabs.addTab(root, "Cooling Simulator")
        self.psw_tab = PswTestTab(self)
        self.tabs.addTab(self.psw_tab, "Psw / m/ms Test")
        self.tabs.currentChanged.connect(lambda i: self.psw_tab.refresh_context() if i == 1 else None)
        self.setCentralWidget(self.tabs)
        self.statusBar().showMessage("Ready")
        self.ed_rates.setText(str(self.settings.value("me_rates", "500")))
        self._run_params = None      # parameters the displayed ME results were computed with
        self._update_card(reveal=False)
        if self.ed_vpath.text().strip() and os.path.isdir(self.ed_vpath.text().strip()):
            self.open_path(self.ed_vpath.text().strip(), sync_rate=False)

    # ---------------- helpers ----------------
    def _style_axes(self):
        """Publication style of the exported plot: full frame, inward ticks on all sides, minor ticks."""
        from matplotlib.ticker import AutoMinorLocator, MultipleLocator
        ax = self.ax
        ax.set_facecolor(theme.BG_INPUT)
        for sp in ax.spines.values():
            sp.set_visible(True); sp.set_linewidth(0.9); sp.set_color(theme.FG)
        ax.tick_params(which="both", colors=theme.FG, direction="in", top=True, right=True)
        ax.tick_params(which="major", length=4, width=0.8)
        ax.tick_params(which="minor", length=2, width=0.6)
        ax.xaxis.set_minor_locator(AutoMinorLocator(2))
        ax.yaxis.set_major_locator(MultipleLocator(0.2))
        ax.yaxis.set_minor_locator(AutoMinorLocator(2))
        ax.set_xlabel(r"Temperature, $T$ (K)", color=theme.FG)
        ax.set_ylabel(r"Reduced magnetisation, $m_z$", color=theme.FG)
        ax.set_axisbelow(True)
        self._set_grid(ax)

    def _bump_rates(self, delta):
        try:
            rates = self._rates()
        except ValueError as e:
            QMessageBox.warning(self, "Check input", str(e)); return
        new = [max(1.0, r + delta) for r in rates]
        self.ed_rates.setText(", ".join(f"{r:g}" for r in new))
        if self.bt_run.isEnabled():
            self.run_me()

    def _grid_toggled(self, on):
        self.settings.setValue("show_grid", "true" if on else "false")
        self._set_grid(self.ax)
        self.canvas.draw_idle()

    def _set_grid(self, ax):
        # NB: matplotlib re-enables the grid if kwargs such as alpha are passed with False
        if getattr(self, "cb_grid", None) is None or self.cb_grid.isChecked():
            ax.grid(axis="y", which="major", color=theme.BORDER, lw=0.65, alpha=0.9)
            ax.grid(axis="y", which="minor", color=theme.BORDER, lw=0.45, alpha=0.45)
        else:
            ax.grid(False)

    def _params_toggled(self, on):
        self.settings.setValue("show_params", "true" if on else "false")
        if self.results or self.session is not None:
            self._plot()

    def _param_panels(self):
        """[(title, accent, [(label, value), ...])] shown in the card under the plot."""
        rates = ", ".join(f"{r[0]:g}" for r in self.results) or "\u2014"
        damp = f"{self.sp_damp.value():g}" + ("" if self.cb_damp.currentIndex() == 0 else " (\u03b1/(1+\u03b1\u00b2))")
        panels = [
            ("ME", theme.BLUE, [("Rate", f"{rates} K/ns"),
                                ("Diameter", f"{self.sp_d.value():g} nm"),
                                ("T range", f"{self.sp_t0.value():g}\u2192{self.sp_t1.value():g} K "
                                            f"(\u0394{self.sp_dT.value():g})")]),
            ("Physics", theme.GREEN, [("Field B", f"{self.sp_b.value():g} T"),
                                      ("Damping \u03bb", damp),
                                      ("P\u2080", f"{self.sp_p0.value():g}")]),
            ("Material", theme.FG_DIM, [("Atoms", f"{self.sp_atoms.value()}"),
                                        ("Cell a / c", f"{self.sp_a.value():g} / {self.sp_c.value():g} \u00c5"),
                                        ("\u03bc / \u03b3rel", f"{self.sp_mu.value():g} \u03bcB / {self.sp_gam.value():g}")]),
        ]
        sm = (f"SG {self.sp_sgw.value():g} K, order {self.sp_sgp.value()}" if self.cb_sg.isChecked() else "off")
        vs = self._vampire_stats() if self.session is not None else None
        if vs is not None:
            name = os.path.basename(self.session.run_dir)
            name = name if len(name) <= 18 else name[:17] + "\u2026"
            panels.append(("VAMPIRE", theme.AMBER, [("Run", name),
                                                    ("Seeds", f"{vs.n} @ {self.session.rate_deck:g} K/ns"),
                                                    ("Smoothing", sm)]))
        else:
            panels.append(("VAMPIRE", theme.AMBER, [("Run", "none loaded"), ("Seeds", "\u2014"),
                                                    ("Smoothing", sm)]))
        return panels

    def _on_resized(self):
        if self.results or self.session is not None:
            self._layout_figure(); self.canvas.draw_idle()

    def _clear_card_artists(self):
        for a_ in self._par_artists:
            try:
                a_.remove()
            except (ValueError, NotImplementedError):
                pass
        self._par_artists = []

    def _layout_figure(self):
        """tight_layout + (optionally) the parameter card at the bottom of the figure."""
        from matplotlib.patches import FancyBboxPatch, Rectangle
        self._clear_card_artists()
        if not self.cb_par.isChecked():
            self.fig.tight_layout(); return
        W, H = self.fig.get_figwidth(), self.fig.get_figheight()
        row, head, pad = 0.175, 0.24, 0.10               # inches
        card_h = pad + head + 3 * row + pad
        fh = card_h / H; y0 = 0.012; x0 = 0.015; cw = 0.97
        self.fig.tight_layout(rect=[0, y0 + fh + 0.01, 1, 1])
        fig = self.fig
        box = FancyBboxPatch((x0, y0), cw, fh, transform=fig.transFigure,
                             boxstyle="round,pad=0,rounding_size=0.012", mutation_aspect=W / H,
                             fc=theme.BG_PANEL2, ec=theme.BORDER, lw=1.0, zorder=0)
        self._par_artists.append(fig.add_artist(box))
        panels = self._param_panels()
        n = len(panels); gap = 0.012
        pw = (cw - gap * (n + 1)) / n
        for i, (title, acc, rows) in enumerate(panels):
            px = x0 + gap + i * (pw + gap)
            bar = Rectangle((px, y0 + pad / H), 0.05 / W, fh - 2 * pad / H, transform=fig.transFigure,
                            fc=acc, ec="none", zorder=1)
            self._par_artists.append(fig.add_artist(bar))
            tx = px + 0.11 / W
            ytop = y0 + fh - pad / H
            self._par_artists.append(fig.text(tx, ytop, title, ha="left", va="top", fontsize=8.5,
                                              fontweight="bold", color=acc, zorder=2))
            for j, (lab, val) in enumerate(rows):
                yy = ytop - (head + j * row) / H
                self._par_artists.append(fig.text(tx, yy, lab, ha="left", va="top", fontsize=7.5,
                                                  color=theme.FG_DIM, zorder=2))
                self._par_artists.append(fig.text(px + pw - 0.04 / W, yy, val, ha="right", va="top",
                                                  fontsize=7.5, color=theme.FG, zorder=2))

    def _sg_changed(self, *_):
        on = self.cb_sg.isChecked()
        self.sp_sgw.setEnabled(on); self.sp_sgp.setEnabled(on)
        self.settings.setValue("sg_on", "true" if on else "false")
        self.settings.setValue("sg_win", self.sp_sgw.value())
        self.settings.setValue("sg_poly", self.sp_sgp.value())
        if self.results or self.session is not None:
            self._plot()

    def _smooth(self, T, y):
        """Savitzky-Golay on a curve; window given in K, converted via the grid spacing."""
        if not self.cb_sg.isChecked():
            return y
        from scipy.signal import savgol_filter
        T = np.asarray(T, float); y = np.asarray(y, float)
        dT = float(np.median(np.abs(np.diff(T)))) if len(T) > 1 else 0.0
        if dT <= 0:
            return y
        poly = self.sp_sgp.value()
        w = int(round(self.sp_sgw.value() / dT))
        w += (w % 2 == 0)                               # must be odd
        w = max(w, poly + 2 + ((poly + 2) % 2 == 0))    # must exceed polyorder
        if w > len(y):                                  # too long for the data
            w = len(y) - (len(y) % 2 == 0)
        if w <= poly:
            return y
        return savgol_filter(y, w, poly, mode="interp")

    def _theme_changed(self, dark):
        from PySide6.QtWidgets import QApplication
        self.settings.setValue("theme", "dark" if dark else "light")
        theme.apply_theme(QApplication.instance(), "dark" if dark else "light")
        self._restyle()

    def _restyle(self):
        self.lbl_v.setStyleSheet(f"color:{theme.FG_DIM}")
        self._update_card()
        if hasattr(self, "psw_tab"):
            self.psw_tab.restyle()
        self.fig.set_facecolor(theme.BG_PANEL)
        if self.results or self.session is not None:
            self._plot()
        else:
            self.ax.clear(); self._style_axes(); self.canvas.draw_idle()

    def _invert_changed(self, on):
        self.settings.setValue("invert_x", "true" if on else "false")
        if self.results or self.session is not None:
            self._plot()

    def _atoms_from_d(self):
        v_cell = (self.sp_a.value() * 1e-10) ** 2 * self.sp_c.value() * 1e-10
        v = math.pi / 6 * (self.sp_d.value() * 1e-9) ** 3
        self.sp_atoms.setValue(max(1, int(round(v / v_cell))))

    def _rates(self) -> list[float]:
        try:
            r = [float(x) for x in self.ed_rates.text().replace(";", ",").split(",") if x.strip()]
        except ValueError:
            r = []
        if not r or any(x <= 0 for x in r):
            raise ValueError("Enter cooling rate(s) in K/ns, e.g. 500 or 100, 500, 1000")
        return r

    def _config(self, rate: float) -> MEConfig:
        if self.sp_t0.value() <= self.sp_t1.value():
            raise ValueError("Start temperature must be above the end temperature")
        return MEConfig(
            d_nm=self.sp_d.value(), n_atoms=self.sp_atoms.value(),
            cell_a_m=self.sp_a.value() * 1e-10, cell_c_m=self.sp_c.value() * 1e-10,
            mu_s_mub=self.sp_mu.value(), gamma_rel=self.sp_gam.value(),
            b_app_T=self.sp_b.value(), damping_value=self.sp_damp.value(),
            damping_interpretation="identity" if self.cb_damp.currentIndex() == 0 else "ll_to_gilbert",
            t_start_K=self.sp_t0.value(), t_end_K=self.sp_t1.value(),
            rate_K_per_ns=rate, dT_grid_K=self.sp_dT.value(), p0=self.sp_p0.value())

    def _model(self) -> LutMaterial:
        if self._ml is None:
            path = find_lut()
            if path is None:
                raise FileNotFoundError("material lookup table (lut_current_rf_1-10nm_dD0p1.csv) not found; "
                                        "set ME_LUT_FILE or keep it in ../data")
            ml = LutMaterial(path); ml.load(); self._ml = ml
        return self._ml

    def _d_autorun(self):
        if self._worker is not None and self._worker.isRunning():
            self._d_timer.start()                # a run is in progress: retry shortly
            return
        self.run_me()

    # ---------------- run ME ----------------
    def run_me(self):
        try:
            rates = self._rates()
            cfgs = [self._config(r) for r in rates]
        except ValueError as e:
            QMessageBox.warning(self, "Check input", str(e)); return
        self.bt_run.setEnabled(False); self.statusBar().showMessage("Running…")
        c0 = cfgs[0]
        self._pending_params = dict(
            d_nm=c0.d_nm, t_start_K=c0.t_start_K, t_end_K=c0.t_end_K, b_app_T=c0.b_app_T,
            damping_value=c0.damping_value, damping_interpretation=c0.damping_interpretation,
            n_atoms=c0.n_atoms, cell_a_m=c0.cell_a_m, cell_c_m=c0.cell_c_m,
            mu_s_mub=c0.mu_s_mub, gamma_rel=c0.gamma_rel,
            dT_grid_K=c0.dT_grid_K, p0=c0.p0)

        def job():
            ml = self._model()
            out = []
            for cfg in cfgs:
                solver = MESolver(ml, me_inputs_for_solver(cfg)); solver.configure(cfg)
                T, m, P, ms, cl, ct, Tc, Gam = solver.predict(
                    cfg.rate_K_per_ns, cfg.t_start_K, cfg.t_end_K, cfg.dT_grid_K)
                out.append((cfg.rate_K_per_ns, T, m, P, ms, Tc))
            return out

        self._worker = Worker(job, self)
        self._worker.ok.connect(self._run_done); self._worker.err.connect(self._run_failed)
        self._worker.start()

    def _run_failed(self, msg):
        self.bt_run.setEnabled(True); self.statusBar().showMessage("Error")
        QMessageBox.critical(self, "Run failed", msg)

    def _run_done(self, results):
        self.results = results
        self._run_params = getattr(self, "_pending_params", None)
        self.settings.setValue("me_rates", self.ed_rates.text())
        self.bt_run.setEnabled(True); self.statusBar().showMessage("Done")
        self._plot()

    def _vampire_stats(self):
        if self.session is None or not self.session.seeds:
            return None
        from ..core.statistics import compute_stats
        return compute_stats(self.session.seeds)

    @staticmethod
    def _vampire_final(vs, T_end):
        """R_VAMPIRE = median_i[m_i(T_end)] / m_s,VAMPIRE(T_end), from the actual T_end row.

        m_i = longitudinal Mz of seed i; m_s,VAMPIRE = median over seeds of the magnetisation
        length |m_i| at the same row.  No interpolation: returns (None, reason) if the data
        has no row within 0.5 K of T_end.  -> (ratio, median_mz, ms_vampire, reason)
        """
        i = int(np.argmin(np.abs(vs.T - T_end)))
        if abs(vs.T[i] - T_end) > 0.5:
            return None, None, None, f"VAMPIRE has no row at {T_end:g} K (nearest {vs.T[i]:g} K)"
        mz = float(np.median(vs.mz_per_seed[:, i])); msv = float(np.median(vs.mlen[:, i]))
        if msv <= 0:
            return None, None, None, "VAMPIRE magnetisation length is zero"
        return mz / msv, mz, msv, ""

    def _mismatches(self, rate):
        """Why the displayed ME run at `rate` is NOT directly comparable to the loaded VAMPIRE run."""
        v = self.session
        if v is None or not v.seeds:
            return ["no VAMPIRE data loaded"]
        out = []
        vr = v.rate_deck
        if not vr or abs(vr - rate) > 1e-6 * max(1.0, rate):
            out.append(f"cooling rate (ME {rate:g} vs VAMPIRE {vr:g} K/ns)" if vr else "VAMPIRE rate unknown")
        c, p = v.cfg, self._run_params
        if c is None:
            out.append("VAMPIRE parameters could not be read")
            return out
        if p is None:
            out.append("ME parameters unknown")
            return out
        def num(label, mv, vv, unit="", tol=1e-6):
            if abs(mv - vv) > tol * max(abs(vv), 1e-30):
                out.append(f"{label} (ME {mv:g} vs VAMPIRE {vv:g}{unit})")
        num("grain diameter", p["d_nm"], c.d_nm, " nm")
        num("start T", p["t_start_K"], c.t_start_K, " K"); num("end T", p["t_end_K"], c.t_end_K, " K")
        num("field B", p["b_app_T"], c.b_app_T, " T", 1e-4)
        num("damping", p["damping_value"], c.damping_value)
        if p["damping_interpretation"] != c.damping_interpretation:
            out.append("damping interpretation")
        num("atoms", p["n_atoms"], c.n_atoms); num("cell a", p["cell_a_m"], c.cell_a_m)
        num("cell c", p["cell_c_m"], c.cell_c_m); num("atomic moment", p["mu_s_mub"], c.mu_s_mub)
        num("\u03b3", p["gamma_rel"], c.gamma_rel)
        return out

    def _reveal_card(self):
        QTimer.singleShot(0, lambda: self.left_scroll.ensureWidgetVisible(self.card, 0, 8))

    def _update_card(self, reveal=True):
        """Final Magnetisation Ratio card: ME (blue) | VAMPIRE (orange) | status."""
        blue, amber, dim, fg = theme.BLUE, theme.AMBER, theme.FG_DIM, theme.FG
        self.card.setStyleSheet(
            f"QFrame#ratioCard {{ background:{theme.BG_PANEL2}; border:1px solid {theme.BORDER};"
            f" border-radius:8px; }} QFrame#ratioCard QLabel {{ background:transparent; }}")
        T_end = self.results[0][1][-1] if self.results else self.sp_t1.value()
        Tl = f"{T_end:g} K"
        self.card_title.setText(f"<b>Final Magnetisation Ratio ({Tl})</b>")
        self.card_title.setToolTip("R_ME = m_ME / ms_ME;  R_VAMPIRE = median_i[m_i] / ms_VAMPIRE, where "
                                   "ms_VAMPIRE = median over seeds of the magnetisation length |m_i|")
        # ME
        if self.results:
            rows = "".join(f"<br>{r:g} K/ns &nbsp;<b style='color:{blue}'>{m[-1] / ms[-1]:.4f}</b>"
                           for r, T, m, P, ms, Tc in self.results)
        else:
            rows = f"<br><span style='color:{dim}'>run ME to see values</span>"
        self.card_me.setText(f"<span style='color:{blue}'><b>\u25a0 ME</b></span> "
                             f"<span style='color:{dim}'>m/ms</span>{rows}")
        self.card_me.setStyleSheet(f"border-left:3px solid {blue}; padding-left:6px;")
        # VAMPIRE
        vs = self._vampire_stats()
        vres = self._vampire_final(vs, T_end) if vs is not None else None
        if vs is None:
            body = f"<br><span style='color:{dim}'>no VAMPIRE data loaded</span>"
        elif vres[0] is None:
            body = f"<br><span style='color:{dim}'>{vres[3]}</span>"
        else:
            body = (f"<br>{self.session.rate_deck:g} K/ns &nbsp;<b style='color:{amber}'>{vres[0]:.4f}</b>"
                    f" <span style='color:{dim}'>({vs.n} seeds)</span>")
        self.card_vm.setText(f"<span style='color:{amber}'><b>\u25a0 VAMPIRE</b></span> "
                             f"<span style='color:{dim}'>median m / ms</span>{body}")
        self.card_vm.setStyleSheet(f"border-left:3px solid {amber}; padding-left:6px;")
        # status: valid only if some displayed ME run matches the VAMPIRE conditions
        if not self.results or vs is None:
            st = f"<span style='color:{dim}'>Load VAMPIRE data and run ME to compare.</span>"
        elif vres[0] is None:
            st = f"<span style='color:{theme.AMBER}'>\u26a0 Cannot compare: {vres[3]}</span>"
        else:
            ok = [(r, m[-1] / ms[-1]) for r, T, m, P, ms, Tc in self.results if not self._mismatches(r)]
            if ok:
                r, rme = ok[0]
                st = (f"<span style='color:{theme.GREEN}'>\u2713 Comparable at {r:g} K/ns</span> &nbsp;"
                      f"\u0394R = |{rme:.4f} \u2212 {vres[0]:.4f}| = <b>{abs(rme - vres[0]):.4f}</b>")
            else:
                reasons = self._mismatches(self.results[0][0])
                for rr in self.results[1:]:                  # prefer the run closest to VAMPIRE's rate
                    if abs(rr[0] - self.session.rate_deck) < abs(self.results[0][0] - self.session.rate_deck):
                        reasons = self._mismatches(rr[0])
                st = (f"<span style='color:{theme.AMBER}'><b>Not directly comparable</b></span>"
                      f"<br><span style='color:{dim}'>differs: {'; '.join(reasons)}</span>")
        self.card_status.setText(st)
        if reveal and self.isVisible():
            self._reveal_card()

    def _plot(self):
        self.ax.clear(); self._style_axes()
        lines = []
        vs = self._vampire_stats()
        vrate = self.session.rate_deck if vs is not None else None
        Ts = []
        if vs is not None:
            vcol = COLORS[0]
            # one seed -> sem is NaN (ddof=1); show no error band instead of crashing the plot
            vm = self._smooth(vs.T, vs.mean)
            vsem = self._smooth(vs.T, np.nan_to_num(np.asarray(vs.sem, float), nan=0.0))
            self.ax.fill_between(vs.T, vm - 2 * vsem, vm + 2 * vsem, color=vcol, alpha=0.25, lw=0)
            self.ax.plot(vs.T, vm, color=vcol, lw=2.2,
                         label=f"VAMPIRE {vrate:g} K/ns (n={vs.n}, \u00b12 s.e.m.)")
            Ts += [vs.T.max(), vs.T.min()]
            lines.append(f"VAMPIRE {vrate:g} K/ns: {vs.n} seeds")
        for i, (rate, T, m, P, ms, Tc) in enumerate(self.results):
            col = COLORS[(i + (vs is not None)) % len(COLORS)]
            m_s = self._smooth(T, m)
            if m_s is not m:                      # raw numerical result stays visible, but secondary
                self.ax.plot(T, m, color=col, lw=0.85, alpha=0.24, zorder=2)
            self.ax.plot(T, m_s, "--" if vs is not None else "-", color=col, lw=2.2, zorder=3,
                         label=f"ME {rate:g} K/ns")
            txt = f"ME {rate:g} K/ns: m(end)={m[-1]:.3f}, P_rev={1 - P[-1]:.3f}, Tc\u2248{Tc:.0f} K"
            # R_m = m/m_s at the final temperature, raw (never smoothed) values
            lab = f"m({T[-1]:g} K)/ms({T[-1]:g} K)"
            txt += f", {lab}: ME={m[-1] / ms[-1]:.4f}"
            if vs is not None:
                v_r, _, _, why = self._vampire_final(vs, T[-1])
                if abs(vrate - rate) > 1e-6 * max(1.0, rate):
                    txt += f" | VAMPIRE: not compared (VAMPIRE run is {vrate:g} K/ns, ME is {rate:g} K/ns)"
                else:
                    txt += (f" | VAMPIRE(median of {vs.n} seeds)={v_r:.4f}" if v_r is not None
                            else f" | VAMPIRE: not compared ({why})")
            if vs is not None and abs(rate - vrate) <= 1e-9 * max(1.0, rate):
                txt += f", rmse vs VAMPIRE={vs.rmse_me(T, m):.4f}"
            lines.append(txt)
            Ts += [T.max(), T.min()]
        if not Ts:
            return
        lo, hi = min(Ts), max(Ts)
        self.ax.set_xlim((hi, lo) if self.cb_inv.isChecked() else (lo, hi))
        self.ax.set_ylim(0.0, 1.04)
        self.ax.margins(x=0.01)
        if hi - lo >= 300:
            from matplotlib.ticker import MultipleLocator
            self.ax.xaxis.set_major_locator(MultipleLocator(100))
        if self.results:                          # Curie temperature marker (as in the exported plot)
            Tc = self.results[0][5]
            self.ax.axvline(Tc, color=theme.FG_DIM, lw=1.1, ls=(0, (4, 3)), zorder=1)
            self.ax.annotate(rf"$T_{{\mathrm{{C}}}} = {Tc:.0f}\,\mathrm{{K}}$",
                             xy=(Tc, 0.97), xycoords=("data", "axes fraction"),
                             xytext=(7, -2), textcoords="offset points", ha="left", va="top",
                             fontsize=9, color=theme.FG,
                             bbox=dict(boxstyle="round,pad=0.22", fc=theme.BG_INPUT, ec="none", alpha=0.88))
        self.ax.legend(loc="lower right", facecolor=theme.BG_INPUT, edgecolor="none",
                       framealpha=0.92, labelcolor=theme.FG, fontsize=9)
        self.ax.set_title(f"D = {self.sp_d.value():g} nm", color=theme.FG)
        self._layout_figure()
        self.canvas.draw_idle()
        self.lbl_res.setText("\n".join(lines))
        self._update_card()

    # ---------------- optional VAMPIRE ----------------
    def load_vampire(self):
        start = self.ed_vpath.text().strip()
        if not os.path.isdir(start):
            start = str(STANDALONE.parent / "data" / "raw")
        d = QFileDialog.getExistingDirectory(self, "Select VAMPIRE run folder (e.g. rate_500Kns)", start)
        if d:
            self.open_path(d)

    def load_typed(self):
        d = self.ed_vpath.text().strip()
        if not os.path.isdir(d):
            QMessageBox.warning(self, "VAMPIRE path", f"Folder not found:\n{d}"); return
        self.open_path(d)

    def open_path(self, d, sync_rate=True):
        self._sync_rate = bool(sync_rate)     # user-triggered loads set the ME rate to match
        self.bt_load.setEnabled(False); self.bt_browse.setEnabled(False)
        self.ed_vpath.setText(d)
        self.statusBar().showMessage("Loading VAMPIRE run…")

        def job():
            from ..core.session import AnalysisSession
            s = AnalysisSession(self._resolve(d), snap_diameter=False); s.load_seeds()   # use the deck's real diameter
            return s

        self._worker = Worker(job, self)
        self._worker.ok.connect(self._vampire_loaded); self._worker.err.connect(self._vampire_failed)
        self._worker.start()

    @staticmethod
    def _resolve(d):
        # a single seed folder (seed_N with DONE) was picked: use its parent rate folder
        if (os.path.basename(os.path.normpath(d)).startswith("seed_")
                and os.path.isfile(os.path.join(d, "DONE"))):
            return os.path.dirname(os.path.abspath(d))
        if not any(n.startswith("seed_") for n in os.listdir(d)):
            for root, dirs, _ in os.walk(d):
                if any(n.startswith("rate_") for n in dirs):
                    return os.path.join(root, sorted(n for n in dirs if n.startswith("rate_"))[0])
        return d

    def _apply_vampire_settings(self):
        """Copy everything EXCEPT the ME cooling rate (independent) into the form."""
        if self.session is None or self.session.cfg is None:
            return
        c = self.session.cfg
        self.sp_d.blockSignals(True); self.sp_d.setValue(c.d_nm); self.sp_d.blockSignals(False)
        self.sp_t0.setValue(c.t_start_K); self.sp_t1.setValue(c.t_end_K)
        self.sp_b.blockSignals(True); self.sp_b.setValue(c.b_app_T); self.sp_b.blockSignals(False); self.sp_damp.setValue(c.damping_value)
        self.sp_atoms.setValue(c.n_atoms)
        self.sp_a.setValue(c.cell_a_m * 1e10); self.sp_c.setValue(c.cell_c_m * 1e10)
        self.sp_mu.setValue(c.mu_s_mub); self.sp_gam.setValue(c.gamma_rel)
        self.cb_damp.setCurrentIndex(0 if c.damping_interpretation == "identity" else 1)

    def _import_toggled(self, on):
        self.settings.setValue("import_vampire", "true" if on else "false")
        if on and self.session is not None:
            if self.session.cfg is None:
                QMessageBox.warning(self, "Import VAMPIRE settings",
                                    f"ME parameters could not be read from the run: {self.session.mapping_error}")
                return
            self._apply_vampire_settings()
            self.statusBar().showMessage("VAMPIRE settings imported \u2014 press Run ME")

    def _vampire_failed(self, msg):
        self.bt_load.setEnabled(True); self.bt_browse.setEnabled(True)
        self.statusBar().showMessage("Error")
        QMessageBox.critical(self, "Could not load VAMPIRE run", msg)

    def _vampire_loaded(self, s):
        self.bt_load.setEnabled(True); self.bt_browse.setEnabled(True)
        self.statusBar().showMessage("VAMPIRE run loaded")
        self.session = s
        self.settings.setValue("vampire_path", self.ed_vpath.text().strip())
        self.bt_clear.setVisible(True)
        rate_txt = f"{s.rate_deck:g} K/ns" if s.rate_deck else "rate unknown"
        note = ""
        if s.cfg is None:
            note = f"\nME parameters could not be read from it: {s.mapping_error}"
        elif self.cb_vparams.isChecked():
            self._apply_vampire_settings()
        synced = False
        if getattr(self, "_sync_rate", True) and s.rate_deck:
            self.ed_rates.setText(f"{s.rate_deck:g}"); synced = True
        if s.cfg is not None:
            note = f"\nGrain D = {s.rf_d:g} nm from the deck (LUT interpolated), N = {s.cfg.n_atoms} atoms" + note
        self.lbl_v.setText(f"{s.run_dir}\n{len(s.seeds)} seeds, {rate_txt}. "
                           + ("ME rate set to match (you can change it freely)." if synced
                              else "ME rate is set separately above.") + note)
        self.lbl_v.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._update_card()
        if synced or not self.results:
            if self.bt_run.isEnabled():
                self.run_me()
            else:                                  # a run is in progress: redo it with the new rate
                self._worker.finished.connect(self.run_me, Qt.SingleShotConnection)
        else:
            self._plot()

    def clear_vampire(self):
        self.session = None; self.bt_clear.setVisible(False); self.lbl_v.setText("")
        if self.results:
            self._plot()
        self._update_card()

    # ---------------- export ----------------
    def save_png(self):
        if not self.results:
            return
        p, _ = QFileDialog.getSaveFileName(self, "Save figure", "me_cooling.png", "PNG (*.png)")
        if p:
            self.fig.savefig(p, dpi=200, facecolor=self.fig.get_facecolor())

    def export_py(self):
        params = getattr(self, "_run_params", None)
        if not self.results or not params:
            QMessageBox.information(self, "Export .py", "Press Run ME first.")
            return
        p, _ = QFileDialog.getSaveFileName(self, "Export master-equation code",
                                           "me_cooling_standalone.py", "Python (*.py)")
        if not p:
            return
        import shutil
        from ..core.code_export import generate_script
        from ..version import get_version
        dest = Path(p)
        cfgs = [MEConfig(rate_K_per_ns=r[0], **params) for r in self.results]
        dest.write_text(generate_script(cfgs, dest.name, get_version(), self._model().path.name), encoding="utf-8")
        lut = self._model().path
        msg = f"Saved {dest.name}."
        if not (dest.parent / lut.name).exists() and QMessageBox.question(
                self, "Copy lookup table?",
                f"{dest.name} also needs {lut.name} in the same folder.\nCopy it now (~8 MB)?"
        ) == QMessageBox.Yes:
            shutil.copy2(lut, dest.parent / lut.name)
            msg += " Lookup table copied."
        self.statusBar().showMessage(msg)

    def save_csv(self):
        if not self.results:
            return
        p, _ = QFileDialog.getSaveFileName(self, "Save data", "me_cooling.csv", "CSV (*.csv)")
        if not p:
            return
        with open(p, "w", newline="") as f:
            w = csv.writer(f); w.writerow(["rate_K_per_ns", "T_K", "m", "P_up", "m_s"])
            for rate, T, m, P, ms, Tc in self.results:
                for row in zip(T, m, P, ms):
                    w.writerow([rate, *row])
