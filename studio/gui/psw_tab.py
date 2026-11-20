"""'Psw / m/ms Test' tab.

Two physically separate quantities at the final temperature (default 300 K):
  * m/ms  - normalised magnetisation.
        ME:       m_ME(T_end) / ms_ME(T_end)                      (solver arrays)
        VAMPIRE:  median_i[m_i(T_end)] / median_i[|m_i|(T_end)]   (same as the ratio card)
  * Psw   - switching (reversal) probability.
        ME:       Psw = 1 - P_up(T_end)                           (solver P, as is)
        VAMPIRE:  fraction of seeds with m_i(T_end) < 0           (a median of a 0/1 outcome is
                  not meaningful, so the empirical fraction k/n is reported)
Nothing here changes the solver; it only calls MESolver.predict like the main page.
"""
from __future__ import annotations

import os
import re

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as Canvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea,
                               QSizePolicy, QSpinBox, QVBoxLayout, QWidget)

from ..core.me_solver import MESolver
from ..core.mapping_engine import me_inputs_for_solver
from . import theme


class _Job(QThread):
    ok = Signal(object)
    err = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            self.ok.emit(self.fn())
        except Exception as e:
            self.err.emit(f"{type(e).__name__}: {e}")


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    f = QFrame(); f.setObjectName("card")
    f.setStyleSheet("QFrame#card QLabel, QFrame#card QCheckBox { background: transparent; }")
    lay = QVBoxLayout(f); lay.setContentsMargins(12, 8, 12, 10); lay.setSpacing(6)
    h = QLabel(title); h.setObjectName("cardHead"); lay.addWidget(h)
    return f, lay


def _rate_of_dir(name: str):
    m = re.fullmatch(r"rate_(\d+(?:\.\d+)?)Kns", name)
    return float(m.group(1)) if m else None


class PswTestTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self._vcache: dict = {}          # run_dir -> AnalysisSession (seeds loaded)
        self._res = None
        self._job = None
        self._runs: dict[float, str] = {}

        # ---- header ----
        self.lbl_title = QLabel("Psw / m/ms TEST"); self.lbl_title.setObjectName("appTitle")
        self.lbl_sub = QLabel(); self.lbl_sub.setObjectName("appSub")

        # ---- ME box ----
        me_card, ml = _card("ME Solver")
        self.sp_me_rate = QDoubleSpinBox(); self.sp_me_rate.setRange(0.01, 1e6)
        self.sp_me_rate.setDecimals(2); self.sp_me_rate.setValue(500); self.sp_me_rate.setSuffix(" K/ns")
        self.sp_me_rate.setKeyboardTracking(False)
        ml.addWidget(QLabel("Cooling rate")); ml.addWidget(self.sp_me_rate)
        ml.addWidget(self._dim("Other parameters come from the Cooling Simulator tab."))
        ml.addStretch(1)

        # ---- VAMPIRE box ----
        v_card, vl = _card("VAMPIRE")
        self.cb_vrate = QComboBox(); self.cb_vrate.setToolTip(
            "Rates available in the loaded VAMPIRE dataset folder (siblings of the loaded run)")
        self.sp_seeds = QSpinBox(); self.sp_seeds.setRange(1, 1000); self.sp_seeds.setValue(25)
        self.sp_seeds.setToolTip("Use at most the first N seeds of every VAMPIRE run in this test "
                                 "(a run with fewer seeds uses all it has; the table shows the count used)")
        self.lbl_vinfo = self._dim("")
        vl.addWidget(QLabel("Cooling rate")); vl.addWidget(self.cb_vrate)
        self.cb_vrate.currentIndexChanged.connect(self._sync_me_rate)   # picking a VAMPIRE rate sets the ME rate to match
        vl.addWidget(QLabel("Number of seeds")); vl.addWidget(self.sp_seeds)
        vl.addWidget(self.lbl_vinfo)
        row_top = QHBoxLayout(); row_top.addWidget(me_card, 1); row_top.addWidget(v_card, 1)

        # ---- quantities ----
        q_card, ql = _card("TEST QUANTITIES")
        self.cb_m = QCheckBox("Normalised magnetisation   m(T) / ms(T)"); self.cb_m.setChecked(True)
        self.cb_p = QCheckBox("Switching probability   Psw(T) = 1 − P_up(T), directly from solver")
        self.cb_p.setChecked(True)
        self.cb_cmp = QCheckBox("Compare both quantities  (ME vs VAMPIRE difference Δ)")
        self.cb_cmp.setChecked(True)
        self.cb_cmp.setToolTip("Adds an ME − VAMPIRE difference column for each selected quantity")
        self.bt_run = QPushButton("RUN TEST"); self.bt_run.setObjectName("runBtn")
        self.bt_run.setMinimumHeight(38); self.bt_run.clicked.connect(self.run_test)
        for c in (self.cb_m, self.cb_p, self.cb_cmp):
            ql.addWidget(c)
        ql.addWidget(self.bt_run)

        # ---- results ----
        r_card, rl = _card("RESULTS")
        self.lbl_table = QLabel("Press RUN TEST."); self.lbl_table.setTextFormat(Qt.RichText)
        self.lbl_table.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_match = QLabel(); self.lbl_match.setTextFormat(Qt.RichText)
        self.lbl_warn = QLabel(); self.lbl_warn.setTextFormat(Qt.RichText); self.lbl_warn.setWordWrap(True)
        self.lbl_note = self._dim("")
        for w in (self.lbl_table, self.lbl_match, self.lbl_warn, self.lbl_note):
            w.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
            rl.addWidget(w)

        # ---- plot ----
        p_card, pl = _card("PLOT")
        self.fig = Figure(figsize=(9, 3.4), dpi=100)
        self.canvas = Canvas(self.fig); self.canvas.setMinimumHeight(330)
        pl.addWidget(self.canvas)

        for l_ in (self.lbl_vinfo, self.lbl_sub):
            l_.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        body = QWidget(); bl = QVBoxLayout(body); bl.setSpacing(10); bl.setContentsMargins(14, 10, 14, 14)
        bl.addWidget(self.lbl_title); bl.addWidget(self.lbl_sub)
        bl.addLayout(row_top); bl.addWidget(q_card); bl.addWidget(r_card); bl.addWidget(p_card)
        bl.addStretch(1)
        sc = QScrollArea(); sc.setWidget(body); sc.setWidgetResizable(True); sc.setFrameShape(QFrame.NoFrame)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.addWidget(sc)
        self.refresh_context()
        self._draw_empty()

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _dim(text):
        l = QLabel(text); l.setWordWrap(True); l.setObjectName("stepDesc"); return l

    def _sync_me_rate(self, *_):
        """ME Solver rate follows the selected VAMPIRE rate (the ME box stays editable afterwards)."""
        r = self.cb_vrate.currentData()
        if r is not None:
            self.sp_me_rate.setValue(float(r))

    def refresh_context(self):
        """Pull D / final T from the main form and list the VAMPIRE dataset rates."""
        m = self.main
        self.lbl_sub.setText(f"D = {m.sp_d.value():g} nm  |  Final temperature = {m.sp_t1.value():g} K")
        cur = self.cb_vrate.currentData()
        self._runs = {}
        s = m.session
        if s is not None:
            parent = os.path.dirname(s.run_dir)
            for name in sorted(os.listdir(parent)) if os.path.isdir(parent) else []:
                r = _rate_of_dir(name)
                p = os.path.join(parent, name)
                if r is not None and os.path.isdir(p) and any(n.startswith("seed_") for n in os.listdir(p)):
                    self._runs[r] = p
            if s.rate_deck:                       # make sure the loaded run is present
                self._runs.setdefault(round(float(s.rate_deck), 6), s.run_dir)
        self.cb_vrate.blockSignals(True); self.cb_vrate.clear()
        for r in sorted(self._runs):
            self.cb_vrate.addItem(f"{r:g} K/ns", r)
        if self._runs:
            want = cur if cur in self._runs else (round(float(s.rate_deck), 6) if s and s.rate_deck in self._runs
                                                  else sorted(self._runs)[0])
            if want not in self._runs and s is not None:
                want = min(self._runs, key=lambda r: abs(r - float(s.rate_deck or r)))
            i = self.cb_vrate.findData(want)
            self.cb_vrate.setCurrentIndex(max(i, 0))
            if want != cur:                       # new dataset / first fill: match the ME rate; keep a manual ME edit otherwise
                self._sync_me_rate()
            self.lbl_vinfo.setText(f"Dataset: {os.path.dirname(s.run_dir)}\n{len(self._runs)} rates available")
        else:
            self.lbl_vinfo.setText("No VAMPIRE data: load a run on the Cooling Simulator tab "
                                   "(ME-only values will still be computed).")
        self.cb_vrate.blockSignals(False)

    @staticmethod
    def _condition_diffs(cfg, vcfg) -> list[str]:
        """Everything that must match for a direct ME/VAMPIRE comparison, EXCEPT the cooling rate."""
        out = []
        if vcfg is None:
            return ["VAMPIRE parameters could not be read"]
        def num(label, a, b, unit="", tol=1e-6):
            if abs(a - b) > tol * max(abs(b), 1e-30):
                out.append(f"{label} (ME {a:g} vs VAMPIRE {b:g}{unit})")
        num("grain diameter", cfg.d_nm, vcfg.d_nm, " nm")
        num("start T", cfg.t_start_K, vcfg.t_start_K, " K"); num("end T", cfg.t_end_K, vcfg.t_end_K, " K")
        num("field B", cfg.b_app_T, vcfg.b_app_T, " T", 1e-4)
        num("damping", cfg.damping_value, vcfg.damping_value)
        if cfg.damping_interpretation != vcfg.damping_interpretation:
            out.append("damping interpretation")
        num("atoms", cfg.n_atoms, vcfg.n_atoms); num("cell a", cfg.cell_a_m, vcfg.cell_a_m)
        num("cell c", cfg.cell_c_m, vcfg.cell_c_m); num("atomic moment", cfg.mu_s_mub, vcfg.mu_s_mub)
        num("γ", cfg.gamma_rel, vcfg.gamma_rel)
        return out

    # ------------------------------------------------------------ run
    def run_test(self):
        if not (self.cb_m.isChecked() or self.cb_p.isChecked()):
            QMessageBox.information(self, "Test quantities", "Tick at least one quantity."); return
        m = self.main
        try:
            me_rate = float(self.sp_me_rate.value())
            grid = {float(r) for r in np.geomspace(100, 10000, 21)} | set(self._runs) | {me_rate}
            grid = sorted(grid)
            cfgs = {r: m._config(r) for r in grid}            # built here (widgets are not thread-safe)
        except ValueError as e:
            QMessageBox.warning(self, "Check input", str(e)); return
        v_rate = self.cb_vrate.currentData()
        n_seeds = int(self.sp_seeds.value())
        runs = dict(self._runs)
        self.bt_run.setEnabled(False); m.statusBar().showMessage("Running Psw / m/ms test…")

        def job():
            ml = m._model()
            me = {}
            for r in grid:
                cfg = cfgs[r]
                sv = MESolver(ml, me_inputs_for_solver(cfg)); sv.configure(cfg)
                T, mm, P, ms, *_ = sv.predict(r, cfg.t_start_K, cfg.t_end_K, cfg.dT_grid_K)
                me[r] = dict(T_end=float(T[-1]), mms=float(mm[-1] / ms[-1]), psw=float(1.0 - P[-1]))
            vam = {}
            from ..core.session import AnalysisSession
            from ..core.statistics import compute_stats
            for r, path in runs.items():
                s = self._vcache.get(path)
                if s is None:
                    s = AnalysisSession(path); s.load_seeds(); self._vcache[path] = s
                seeds = s.seeds[:n_seeds]
                st = compute_stats(seeds)
                T_end = cfgs[me_rate].t_end_K
                i = int(np.argmin(np.abs(st.T - T_end)))
                if abs(st.T[i] - T_end) > 0.5:
                    vam[r] = dict(error=f"no row at {T_end:g} K (nearest {st.T[i]:g} K)"); continue
                mz = st.mz_per_seed[:, i]; ml_ = st.mlen[:, i]
                vam[r] = dict(n=st.n, mms=float(np.median(mz) / np.median(ml_)),
                              k_rev=int((mz < 0).sum()), psw=float((mz < 0).mean()),
                              rate_deck=float(s.rate_deck or r),
                              diffs=self._condition_diffs(cfgs[me_rate], s.cfg))
            return dict(me=me, vam=vam, me_rate=me_rate, v_rate=v_rate, n_seeds=n_seeds,
                        T_end=cfgs[me_rate].t_end_K, d_nm=cfgs[me_rate].d_nm)

        self._job = _Job(job, self)
        self._job.ok.connect(self._done); self._job.err.connect(self._failed)
        self._job.start()

    def _failed(self, msg):
        self.bt_run.setEnabled(True); self.main.statusBar().showMessage("Error")
        QMessageBox.critical(self, "Test failed", msg)

    def _done(self, res):
        self.bt_run.setEnabled(True); self.main.statusBar().showMessage("Psw / m/ms test done")
        self._res = res
        self._show_results(); self._plot()

    # ------------------------------------------------------------ results table
    def _show_results(self):
        r = self._res
        blue, amber, dim, fg = theme.BLUE, theme.AMBER, theme.FG_DIM, theme.FG
        me = r["me"][r["me_rate"]]
        v = r["vam"].get(r["v_rate"]) if r["v_rate"] is not None else None
        v_ok = v is not None and "error" not in v
        cmp_on = self.cb_cmp.isChecked()
        Tl = f"{r['T_end']:g} K"
        th = f"style='color:{dim};text-align:left;padding:2px 14px 2px 0'"
        td = "style='padding:2px 14px 2px 0'"
        rows = [f"<tr><th {th}>Quantity</th><th {th}>ME ({r['me_rate']:g} K/ns)</th>"
                f"<th {th}>VAMPIRE median ({'%g K/ns' % r['v_rate'] if r['v_rate'] is not None else '—'})</th>"
                + (f"<th {th}>Δ (ME − VAMPIRE)</th>" if cmp_on else "") + "</tr>"]
        def vtxt(key):
            if v is None:
                return "<span style='color:%s'>no data</span>" % dim
            if "error" in v:
                return "<span style='color:%s'>%s</span>" % (dim, v["error"])
            return f"<b style='color:{amber}'>{v[key]:.4f}</b>" + (
                f" <span style='color:{dim}'>({v['k_rev']}/{v['n']} reversed)</span>" if key == "psw" else "")
        def row(label, key):
            d = (f"<td {td}>{me[key] - v[key]:+.4f}</td>" if (cmp_on and v_ok) else
                 (f"<td {td}>—</td>" if cmp_on else ""))
            return (f"<tr><td {td}>{label}</td><td {td}><b style='color:{blue}'>{me[key]:.4f}</b></td>"
                    f"<td {td}>{vtxt(key)}</td>{d}</tr>")
        if self.cb_m.isChecked():
            rows.append(row(f"m({Tl}) / ms({Tl})", "mms"))
        if self.cb_p.isChecked():
            rows.append(row(f"Psw({Tl})", "psw"))
        self.lbl_table.setText("<table cellspacing='0'>" + "".join(rows) + "</table>")

        rate_ok = v_ok and abs(v["rate_deck"] - r["me_rate"]) <= 1e-6 * max(1.0, r["me_rate"])
        if v is None:
            self.lbl_match.setText(f"<b>Cooling rate match:</b> <span style='color:{dim}'>no VAMPIRE data</span>")
        else:
            col = theme.GREEN if rate_ok else theme.RED
            vr = v["rate_deck"] if v_ok else r["v_rate"]
            self.lbl_match.setText(f"<b>Cooling rate match:</b> <b style='color:{col}'>{'YES' if rate_ok else 'NO'}</b>"
                                   f" <span style='color:{dim}'>(ME {r['me_rate']:g} vs VAMPIRE {vr:g} K/ns)</span>")
        warn = []
        if v_ok:
            if not rate_ok:
                warn.append(f"cooling rate (ME {r['me_rate']:g} vs VAMPIRE {v['rate_deck']:g} K/ns)")
            warn += v["diffs"]
        if warn:
            self.lbl_warn.setText(f"<span style='color:{theme.AMBER}'><b>⚠ Not directly comparable</b> — "
                                  f"differs: {'; '.join(warn)}</span>")
        else:
            self.lbl_warn.setText(f"<span style='color:{theme.GREEN}'>✓ Conditions match.</span>" if v_ok else "")
        self.lbl_note.setText("m/ms and Psw are separate quantities. VAMPIRE m/ms = median_i[m_i] / median_i[|m_i|] "
                              "at the final row; VAMPIRE Psw = fraction of the first "
                              f"{r['n_seeds']} seeds with m_i < 0 (a 0/1 outcome per seed, so no median).")

    # ------------------------------------------------------------ plot
    def _style(self, ax):
        ax.set_facecolor(theme.BG_INPUT)
        for s in ax.spines.values():
            s.set_color(theme.BORDER)
        ax.tick_params(colors=theme.FG)
        ax.grid(alpha=0.25)

    def _draw_empty(self):
        self.fig.clear(); self.fig.set_facecolor(theme.BG_PANEL)
        ax = self.fig.add_subplot(111); self._style(ax)
        ax.text(0.5, 0.5, "Press RUN TEST", ha="center", va="center", color=theme.FG_DIM, transform=ax.transAxes)
        ax.set_xticks([]); ax.set_yticks([]); self.canvas.draw_idle()

    def _plot(self):
        r = self._res
        quants = [(k, lab) for k, lab, on in (("mms", "m / ms", self.cb_m.isChecked()),
                                              ("psw", "Psw", self.cb_p.isChecked())) if on]
        self.fig.clear(); self.fig.set_facecolor(theme.BG_PANEL)
        rates = sorted(r["me"])
        for i, (key, lab) in enumerate(quants):
            ax = self.fig.add_subplot(1, len(quants), i + 1); self._style(ax)
            ax.plot(rates, [r["me"][x][key] for x in rates], "-", color=theme.BLUE, lw=2, label="ME")
            ax.plot([r["me_rate"]], [r["me"][r["me_rate"]][key]], "o", color=theme.BLUE, ms=8, mec="white", zorder=5)
            vr = sorted(x for x, d in r["vam"].items() if "error" not in d)
            if vr:
                match = [x for x in vr if not r["vam"][x]["diffs"]]
                other = [x for x in vr if x not in match]
                if match:
                    ax.plot(match, [r["vam"][x][key] for x in match], "s", color=theme.AMBER, ms=7,
                            label=f"VAMPIRE (n≤{r['n_seeds']})")
                if other:
                    ax.plot(other, [r["vam"][x][key] for x in other], "s", mfc="none", mec=theme.AMBER, ms=7,
                            label="VAMPIRE (conditions differ)")
            ax.set_xscale("log")
            ax.set_xlabel("Cooling rate (K/ns)", color=theme.FG)
            ax.set_ylabel(f"{lab} at {r['T_end']:g} K", color=theme.FG)
            ax.set_title(f"{lab} vs cooling rate  (D = {r['d_nm']:g} nm)", color=theme.FG, fontsize=10)
            if key == "psw":
                ax.set_ylim(bottom=0)
            ax.legend(facecolor=theme.BG_PANEL, edgecolor=theme.BORDER, labelcolor=theme.FG, fontsize=8)
        self.fig.tight_layout(); self.canvas.draw_idle()

    def restyle(self):
        if self._res is not None:
            self._show_results(); self._plot()
        else:
            self._draw_empty()
