"""Main window of the VAMPIRE - Master Equation Comparison Studio.

Layout follows the approved mockup (cooling_simulator/ui.png):
  left 5-step rail | tabbed centre (Configuration / Plots / Numerical /
  Parameter Audit / Log) | toolbar | status bar.
"""
from __future__ import annotations

import os
import re
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QCheckBox,
                               QTabWidget, QScrollArea, QFileDialog,
                               QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox,
                               QStatusBar, QToolBar, QSplitter, QTableWidget,
                               QTableWidgetItem, QHeaderView, QMessageBox,
                               QSizePolicy, QFrame, QGroupBox)
from PySide6.QtGui import QAction

from studio.gui import theme
from studio.gui.widgets import (GroupCard, StepCard, ParameterTable,
                                EquationsDialog, SourceViewer, badge, chip,
                                mathtext_pixmap, ME_EQUATIONS,
                                OpenWorker, RunWorker)


def _natural_rate(path: str) -> float | None:
    m = re.search(r"rate_(\d+)Kns", path)
    return float(m.group(1)) if m else None


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VAMPIRE - Master Equation Comparison Studio")
        self.resize(1460, 860)
        self.session = None
        self.result = None
        self.issues: list = []
        self.figure = None
        self.last_export_dir = os.path.expanduser("~")
        self.t0 = time.time()

        self._toolbar()
        central = QWidget()
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._rail(), 0)
        self.tabs = QTabWidget()
        self._build_tabs()
        outer.addWidget(self.tabs, 1)
        self.setCentralWidget(central)
        self._statusbar()
        self.log("Ready. Open a VAMPIRE run directory to begin.")

    # ------------------------------------------------------------ toolbar
    def _toolbar(self):
        tb = QToolBar("main")
        tb.setMovable(False)
        tb.setStyleSheet("QToolBar{padding:8px;}")
        self.addToolBar(tb)
        title = QLabel("  VAMPIRE - ME   Master Equation Comparison Studio   "
                       "\u00b7  Atomic Simulation (VAMPIRE) + Two-State Master "
                       "Equation (Roy Formalism)")
        title.setObjectName("appSub")
        tb.addWidget(title)
        tb.addSeparator()
        for text, slot in (("New", self.act_new), ("Open", self.act_open),
                           ("Save", self.act_save), ("Export \u25be", self.act_export),
                           ("Settings", self.act_settings), ("Help", self.act_help)):
            act = QAction(text, self)
            act.triggered.connect(slot)
            tb.addAction(act)

    # ------------------------------------------------------------ rail
    def _rail(self) -> QWidget:
        rail = QFrame()
        rail.setObjectName("rail")
        rail.setFixedWidth(250)
        v = QVBoxLayout(rail)
        v.setContentsMargins(12, 14, 12, 12)
        v.setSpacing(8)
        logo = QLabel("\u269b  VAMPIRE \u2013 ME\n    Comparison Studio")
        logo.setObjectName("logoTxt")
        v.addWidget(logo)
        self.step_cards = []
        steps = [("Input Files", "Point VAMPIRE files and RF model"),
                 ("Extract Parameters", "Read and analyze VAMPIRE settings"),
                 ("ME Configuration", "Map parameters to Master Equation"),
                 ("Comparison Settings", "Select mode and options"),
                 ("Results", "Compare, plot and export")]
        for i, (t, d) in enumerate(steps, start=1):
            c = StepCard(i, t, d)
            c.mousePressEvent = lambda ev, idx=i: self._goto(idx)
            v.addWidget(c)
            self.step_cards.append(c)
        v.addStretch(1)
        return rail

    def _goto(self, n: int):
        self.tabs.setCurrentIndex(0)
        card = self.cards.get(n)
        if card:
            self.scroll.ensureWidgetVisible(card, 0, 60)

    # ------------------------------------------------------------ tabs
    def _build_tabs(self):
        self.cards = {}
        self._build_config_tab()
        self._build_plots_tab()
        self._build_numbers_tab()
        self._build_audit_tab()
        self._build_log_tab()

    def _build_config_tab(self):
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        body = QWidget()
        v = QVBoxLayout(body)
        v.setSpacing(12)

        # ---- 1 Input Files
        c1 = GroupCard(1, "Input Files")
        self.cards[1] = c1
        g = QVBoxLayout()
        self.ed_run = QLineEdit()
        self.ed_deck = QLineEdit(); self.ed_mat = QLineEdit()
        self.ed_model = QLineEdit()
        for ed in (self.ed_deck, self.ed_mat, self.ed_model):
            ed.setReadOnly(True)
        row = QHBoxLayout()
        row.addWidget(QLabel("Run folder"))
        row.addWidget(self.ed_run, 1)
        b = QPushButton("Browse\u2026")
        b.clicked.connect(self.act_open)
        row.addWidget(b)
        g.addLayout(row)
        for lbl, ed in (("Deck (input)", self.ed_deck),
                        ("Material (.mat)", self.ed_mat),
                        ("RF model dir", self.ed_model)):
            r2 = QHBoxLayout()
            r2.addWidget(QLabel(lbl))
            r2.addWidget(ed, 1)
            g.addLayout(r2)
        self.lbl_detect = QLabel("Waiting for run folder\u2026")
        self.lbl_detect.setStyleSheet(f"color:{theme.FG_DIM}")
        g.addWidget(self.lbl_detect)
        c1.body.addLayout(g)
        v.addWidget(c1)

        # ---- 2 Extracted VAMPIRE Parameters
        c2 = GroupCard(2, "Extracted VAMPIRE Parameters")
        self.cards[2] = c2
        self.badge2 = badge("\u2713 Extracted Successfully")
        self.badge2.setVisible(False)
        c2.head_extra.addWidget(self.badge2)
        self.param_table = ParameterTable()
        self.param_table.cellDoubleClicked.connect(self._show_source)
        self.param_table.setMinimumHeight(230)
        c2.body.addWidget(self.param_table)
        hint = QLabel("Double-click a row to view the exact source line.")
        hint.setStyleSheet(f"color:{theme.FG_DIM};font-size:11px")
        c2.body.addWidget(hint)
        v.addWidget(c2)

        # ---- 3 ME Configuration
        c3 = GroupCard(3, "Master Equation (ME) Configuration")
        self.cards[3] = c3
        box = QFrame()
        box.setStyleSheet(f"background:{theme.BG_INPUT};"
                          f"border:1px solid {theme.BORDER};border-radius:8px;")
        bv = QVBoxLayout(box)
        hv = QHBoxLayout()
        hv.addWidget(QLabel("Roy Two-State Master Equation"))
        hv.addStretch(1)
        bve = QPushButton("\u2295 View Full Equations")
        bve.clicked.connect(lambda: EquationsDialog(self).exec())
        hv.addWidget(bve)
        bv.addLayout(hv)
        eq = QLabel()
        eq.setPixmap(mathtext_pixmap(ME_EQUATIONS, width_px=760, font_size=12))
        bv.addWidget(eq)
        c3.body.addWidget(box)
        grid = QHBoxLayout()
        self.me_params = QPlainTextEdit()
        self.me_params.setReadOnly(True)
        self.me_params.setMinimumHeight(130)
        self.me_mats = QPlainTextEdit()
        self.me_mats.setReadOnly(True)
        self.me_mats.setMinimumHeight(130)
        for title, w in (("ME parameters (from mapping)", self.me_params),
                         ("Material functions", self.me_mats)):
            col = QVBoxLayout()
            col.addWidget(QLabel(title))
            col.addWidget(w)
            grid.addLayout(col)
        c3.body.addLayout(grid)
        v.addWidget(c3)
        # ---- 4 Comparison Settings
        c4 = GroupCard(4, "Comparison Settings")
        self.cards[4] = c4
        row = QHBoxLayout()
        self.ck_mean = QCheckBox("VAMPIRE ensemble mean"); self.ck_mean.setChecked(True)
        self.ck_sem = QCheckBox("\u00b12 SEM band"); self.ck_sem.setChecked(True)
        self.ck_me = QCheckBox("Master Equation (ME)"); self.ck_me.setChecked(True)
        self.ck_hist = QCheckBox("Final-state histogram"); self.ck_hist.setChecked(True)
        self.ck_trans = QCheckBox("Transverse magnetisation"); self.ck_trans.setChecked(True)
        self.ck_seeds = QCheckBox("Show per-seed traces"); self.ck_seeds.setChecked(True)
        for ck in (self.ck_mean, self.ck_sem, self.ck_me, self.ck_hist,
                   self.ck_trans, self.ck_seeds):
            ck.toggled.connect(self._restyle_figure)
            row.addWidget(ck)
        row.addStretch(1)
        row.addWidget(QLabel("Diameter"))
        self.sp_d = QDoubleSpinBox()
        self.sp_d.setRange(1.0, 50.0)
        self.sp_d.setDecimals(2)
        self.sp_d.setSingleStep(0.25)
        self.sp_d.setSuffix(" nm")
        self.sp_d.setEnabled(False)
        self.sp_d.setToolTip(
            "Grain diameter fed to the RF surrogate and (in sphere-volume "
            "mode) used for V = pi/6 d^3. Default = validated snapped value. "
            "Any change is logged as a user override in the record.")
        row.addWidget(self.sp_d)
        row.addWidget(QLabel("Cooling rate"))
        self.sp_rate = QSpinBox()
        self.sp_rate.setRange(1, 100000)
        self.sp_rate.setSuffix(" K/ns")
        self.sp_rate.setEnabled(False)
        self.sp_rate.setToolTip("Default from deck (T, cooling time). "
                                "Editing logs a user override.")
        row.addWidget(self.sp_rate)
        c4.body.addLayout(row)
        rowv = QHBoxLayout()
        rowv.addWidget(QLabel("Grain volume model"))
        self.cmb_vol = QComboBox()
        self.cmb_vol.addItems(["V = n_atoms x v_cell  (validated — default)",
                               "V = pi/6 * D^3  (hypothetical sphere)"])
        self.cmb_vol.setToolTip(
            "Validated pipeline computes grain volume from the deck atom "
            "count. The sphere mode is a hypothetical what-if scenario: "
            "results are NOT validated and the choice is logged in the "
            "comparison record.")
        rowv.addWidget(self.cmb_vol, 1)
        self.lbl_ov = QLabel("")
        self.lbl_ov.setStyleSheet(f"color:{theme.AMBER};font-weight:600")
        rowv.addWidget(self.lbl_ov)
        c4.body.addLayout(rowv)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Damping interpretation"))
        self.cmb_damping = QComboBox()
        self.cmb_damping.addItems(["\u03bb = \u03b1  (identity \u2014 as in validated code)",
                                   "\u03bb = \u03b1/(1+\u03b1\u00b2)  (Gilbert \u2192 Landau\u2013Lifshitz)"])
        self.cmb_damping.setToolTip(
            "VAMPIRE reports damping constant \u03b1. The validated ME code used "
            "the same number as the LL damping \u03bb (identity). Change only "
            "after discussing the physics \u2014 rule M2.")
        row2.addWidget(self.cmb_damping, 1)
        self.btn_run = QPushButton("\u25b6  Run Comparison")
        self.btn_run.setObjectName("runBtn")
        self.btn_run.setMinimumHeight(36)
        self.btn_run.clicked.connect(self.act_run)
        self.btn_run.setEnabled(False)
        breset = QPushButton("Reset")
        breset.clicked.connect(self.act_reset)
        row2.addWidget(self.btn_run)
        row2.addWidget(breset)
        c4.body.addLayout(row2)
        v.addWidget(c4)

        # ---- 5 Results placeholder (real UI in Plots tab)
        c5 = GroupCard(5, "Results: VAMPIRE vs Master Equation")
        self.cards[5] = c5
        self.lbl_c5 = QLabel("\u23f3 Set options, then press Run Comparison.")
        self.lbl_c5.setStyleSheet(f"color:{theme.FG_DIM}")
        c5.body.addWidget(self.lbl_c5)
        r5 = QHBoxLayout()
        self.btn_png = QPushButton("Export Plot")
        self.btn_csv = QPushButton("Export Data (CSV)")
        self.btn_pdf = QPushButton("Report (PDF)")
        self.btn_rec = QPushButton("Save Record")
        for b_ in (self.btn_png, self.btn_csv, self.btn_pdf, self.btn_rec):
            b_.setEnabled(False)
        self.btn_png.clicked.connect(lambda: self.export_one("png"))
        self.btn_csv.clicked.connect(lambda: self.export_one("csv"))
        self.btn_pdf.clicked.connect(lambda: self.export_one("pdf"))
        self.btn_rec.clicked.connect(self.act_save)
        r5.addWidget(self.lbl_c5, 1)
        r5.addLayout(r5btns := QHBoxLayout())
        for b_ in (self.btn_png, self.btn_csv, self.btn_pdf, self.btn_rec):
            r5btns.addWidget(b_)
        c5.body.addLayout(r5)
        v.addWidget(c5)
        v.addStretch(1)
        self.scroll.setWidget(body)
        self.tabs.addTab(self.scroll, "Configuration")

    # ------------------------------------------------------------ plots tab
    def _build_plots_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        self.plot_info = QLabel("No results yet \u2014 press Run Comparison "
                                "(Configuration tab, section 4).")
        self.plot_info.setStyleSheet(f"color:{theme.FG_DIM}")
        v.addWidget(self.plot_info)
        self.plot_label = QLabel()
        self.plot_label.setAlignment(Qt.AlignCenter)
        host = QWidget()
        hv = QVBoxLayout(host)
        hv.setContentsMargins(0, 0, 0, 0)
        hv.addWidget(self.plot_label)
        self.plot_scroll = QScrollArea()
        self.plot_scroll.setWidget(host)
        self.plot_scroll.setWidgetResizable(True)
        v.addWidget(self.plot_scroll, 1)
        self.plot_scroll.viewport().installEventFilter(self)
        self.tabs.addTab(w, "Plots")

    def _build_numbers_tab(self):
        self.num_txt = QPlainTextEdit()
        self.num_txt.setReadOnly(True)
        f = self.num_txt.font()
        f.setFamily("monospace")
        self.num_txt.setFont(f)
        self.tabs.addTab(self.num_txt, "Numerical Results")

    # ------------------------------------------------------------ audit tab
    def _build_audit_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        split = QSplitter(Qt.Vertical)
        self.audit_table = ParameterTable()
        self.audit_table.cellDoubleClicked.connect(self._show_source)
        split.addWidget(self.audit_table)
        box = QGroupBox("Cross-source validation")
        bv = QVBoxLayout(box)
        self.lbl_val = QLabel("no session loaded")
        bv.addWidget(self.lbl_val)
        self.issue_table = QTableWidget()
        self.issue_table.setColumnCount(3)
        self.issue_table.setHorizontalHeaderLabels(["Severity", "Rule", "Message"])
        self.issue_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.issue_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.issue_table.verticalHeader().setVisible(False)
        bv.addWidget(self.issue_table)
        split.addWidget(box)
        split.setSizes([480, 300])
        v.addWidget(split)
        self.tabs.addTab(w, "Parameter Audit")

    def _build_log_tab(self):
        self.log_txt = QPlainTextEdit()
        self.log_txt.setReadOnly(True)
        self.tabs.addTab(self.log_txt, "Log")

    def _statusbar(self):
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.st_ready = QLabel(" Ready")
        self.st_files = QLabel(" VAMPIRE: \u2014")
        self.st_me = QLabel(" ME: \u2014")
        self.st_elapsed = QLabel("Elapsed: 0.0 s")
        sb.addWidget(self.st_ready)
        sb.addWidget(QFrame(frameShape=QFrame.VLine))
        sb.addWidget(self.st_files, 1)
        sb.addPermanentWidget(self.st_me)
        sb.addPermanentWidget(QFrame(frameShape=QFrame.VLine))
        sb.addPermanentWidget(self.st_elapsed)

    def act_export(self):
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        m.addAction("Plot (PNG)", lambda: self.export_one("png"))
        m.addAction("Data (CSV)", lambda: self.export_one("csv"))
        m.addAction("Report (PDF)", lambda: self.export_one("pdf"))
        btn = self.sender()
        if btn is not None:
            m.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    # ------------------------------------------------------------ logging
    def log(self, msg: str):
        self.log_txt.appendPlainText(time.strftime("[%H:%M:%S] ") + msg)

    # ------------------------------------------------------------ actions
    def act_new(self):
        self.session = None
        self.result = None
        self.issues = []
        for ed in (self.ed_run, self.ed_deck, self.ed_mat, self.ed_model):
            ed.setText("")
        self.param_table.set_records([])
        self.audit_table.set_records([])
        self.issue_table.setRowCount(0)
        self.num_txt.setPlainText("")
        self.badge2.setVisible(False)
        self.btn_run.setEnabled(False)
        for b_ in (self.btn_png, self.btn_csv, self.btn_pdf, self.btn_rec):
            b_.setEnabled(False)
        self.lbl_c5.setText("\u23f3 Set options, then press Run Comparison.")
        self.log("Session cleared.")

    def act_open(self):
        d = QFileDialog.getExistingDirectory(self, "Open VAMPIRE run directory",
                                             self.last_export_dir)
        if not d:
            return
        self.last_export_dir = d
        d = self._resolve_rate_dir(d)
        self.ed_run.setText(d)
        self.st_ready.setText(" Parsing\u2026")
        self.log(f"Opening {d}")
        self._worker = OpenWorker(d, self)
        self._worker.done_ok.connect(self._opened)
        self._worker.done_err.connect(self._open_failed)
        self._worker.start()

    @staticmethod
    def _resolve_rate_dir(d: str) -> str:
        """If d is a parent containing runs/rate_*Kns or rate_*Kns children,
        and d itself has no seeds, descend to the single rate dir found."""
        from studio.core.vampire_output_reader import find_seeds
        if find_seeds(d):
            return d
        cands = []
        for sub in ("runs", "."):
            p = os.path.join(d, sub)
            if os.path.isdir(p):
                cands += [os.path.join(p, e) for e in sorted(os.listdir(p))
                          if os.path.isdir(os.path.join(p, e)) and find_seeds(os.path.join(p, e))]
        return cands[0] if len(cands) == 1 else d

    def _open_failed(self, msg: str):
        self.st_ready.setText(" Error")
        self.log("ERROR " + msg)
        QMessageBox.warning(self, "Could not open", msg)

    def _opened(self, s):
        self.session = s
        self.issues = s.validation_issues
        self.ed_deck.setText(str(getattr(s.deck, "path", "") or ""))
        self.ed_mat.setText(os.path.join(s.seed_dirs_all[0], "*.mat")
                            if s.mat else "(no .mat found)")
        self.ed_model.setText(str(s.model_dir) if s.model_dir
                              else "(RF model not found)")
        nseeds = len(s.seed_dirs_all)
        self.lbl_detect.setText(
            f"Auto-detected: {nseeds} DONE seeds \u00b7 deck \u00b7 "
            f"{'.mat' if s.mat else 'no .mat'} \u00b7 "
            f"{'RF model found' if s.model_dir else 'NO RF model'}")
        rate = _natural_rate(s.run_dir)
        self.sp_rate.setEnabled(True)
        self.sp_rate.setValue(int(rate) if rate else int(round(s.cfg.rate_K_per_ns if s.cfg else 0)))
        self.sp_d.setEnabled(True)
        self.sp_d.setValue(s.rf_d)
        self.cmb_vol.setCurrentIndex(0)
        self.lbl_ov.setText("")
        self.badge2.setVisible(s.mapping_error == [])
        self.param_table.set_records(s.table.all())
        self.audit_table.set_records(s.table.all())
        self._fill_me_cards()
        self._fill_validation()
        self.btn_run.setEnabled(s.cfg is not None)
        crit = [i for i in self.issues if i.severity == "critical"]
        warn = [i for i in self.issues if i.severity == "warning"]
        self.st_ready.setText(f" {len(s.table.all())} params extracted")
        self.st_files.setText(
            f" VAMPIRE: D = {s.table.value('grain_diameter')} \u00c5, "
            f"T {s.cfg.t_start_K if s.cfg else '?'} \u2192 "
            f"{s.cfg.t_end_K if s.cfg else '?'} K, "
            f"R = {self.sp_rate.value()} K/ns, N_seeds = {nseeds}")
        snap = " (D snapped to RF-trained value)" if s.rf_d_snapped else ""
        self.st_me.setText(f" ME: two-state model (RF surrogate{snap})")
        self.log(f"Parsed {nseeds} DONE seeds; "
                 f"{len(s.table.all())} parameters; "
                 f"{len(crit)} critical / {len(warn)} warning issues")
        if s.mapping_error:
            QMessageBox.warning(
                self, "Parameters missing",
                "Cannot map to ME \u2014 missing: " + ", ".join(s.mapping_error) +
                "\nUse the Parameter Audit tab to supply values.")

    def _fill_me_cards(self):
        s, cfg = self.session, self.session.cfg
        if cfg is None:
            self.me_params.setPlainText("mapping failed: " +
                                        ", ".join(self.session.mapping_error))
            return
        inp = __import__("studio.core.mapping_engine",
                         fromlist=["me_inputs_for_solver"]
                         ).me_inputs_for_solver(cfg)
        lines = [
            f"Grain diameter (ME)    {cfg.d_nm:.4g} nm",
            f"Grain volume V         {cfg.v_grain_m3:.4g} m\u00b3 "
            f"({cfg.n_atoms} atoms)",
            f"Cell volume            {cfg.v_cell_m3:.4g} m\u00b3",
            f"Atomic moment          {cfg.mu_s_mub:.4g} \u00b5B",
            f"M_s(0) = mu/v_cell     {inp['MS_0']:.4g} A/m",
            f"\u03b3 (rel)               {cfg.gamma_rel:.4g}",
            f"\u03bb (damping)           {inp['LAMBDA']:.4g} "
            f"[{cfg.damping_interpretation}]",
            f"Applied field          {cfg.b_app_T:.4g} T",
            f"Cooling rate           {cfg.rate_K_per_ns:g} K/ns",
            f"T start \u2192 end           {cfg.t_start_K:g} \u2192 "
            f"{cfg.t_end_K:g} K   (grid \u0394T = {cfg.dT_grid_K:g} K)",
            f"Initial P_+            {cfg.p0:g}"]
        self.me_params.setPlainText("\n".join(lines))
        m = self.session.model_meta or {}
        md = m.get("metadata", {})
        self.me_mats.setPlainText(
            f"RF model      {self.session.model_dir}\n"
            f"trained D     {md.get('D_nm', '?')} nm    "
            f"(deck: {self.session.table.value('grain_diameter')} \u00c5)"
            f"{'  \u2190 snapped' if self.session.rf_d_snapped else ''}\n"
            f"Tc(K)         {md.get('Tc_K', '?')} (from log)\n"
            f"targets       {', '.join(m.get('targets', []))}\n"
            f"registry      {m.get('registry', 'UNREGISTERED')}")

    def _fill_validation(self):
        from studio.core.consistency_validator import summarise
        summ = summarise(self.issues)
        self.lbl_val.setText(
            f"{summ['n_pass']} pass / {summ['n_warning']} warning / "
            f"{summ['n_critical']} critical")
        self.issue_table.setRowCount(len(self.issues))
        for row, i in enumerate(self.issues):
            colour = {"critical": theme.RED, "warning": theme.AMBER,
                      "pass": theme.GREEN}.get(i.severity, theme.FG)
            it = QTableWidgetItem(i.severity)
            it.setForeground(self._qcol(colour))
            self.issue_table.setItem(row, 0, it)
            self.issue_table.setItem(row, 1, QTableWidgetItem(i.rule))
            msg = i.message + ("  [" + ", ".join(s.cite().split("/")[-1]
                                                 for s in i.evidence) + "]"
                               if i.evidence else "")
            self.issue_table.setItem(row, 2, QTableWidgetItem(msg))

    # ------------------------------------------------------------ run/reset
    def act_reset(self):
        for ck in (self.ck_mean, self.ck_sem, self.ck_me, self.ck_hist,
                   self.ck_trans, self.ck_seeds):
            ck.setChecked(True)
        self.log("Options reset to validated defaults.")

    def act_run(self):
        if self.session is None:
            return
        interp = "identity" if self.cmb_damping.currentIndex() == 0 else "gilbert"
        if interp != self.session.damping_interpretation:
            if QMessageBox.question(
                    self, "Confirm damping change",
                    "The validated pipeline used \u03bb = \u03b1 (identity). "
                    "Switching changes the ME physics. Continue?") != QMessageBox.Yes:
                self.cmb_damping.setCurrentIndex(0)
                return
            self.session.damping_interpretation = interp
            self.session.cfg = None
            from studio.core.mapping_engine import map_to_me, MappingError
            try:
                self.session.cfg = map_to_me(
                    self.session.table, dT_grid_K=self.session.dT_grid_K,
                    damping_interpretation=interp,
                    rf_d_nm=self.session.rf_d)
            except MappingError as e:
                QMessageBox.warning(self, "Mapping failed", str(e))
                return
        # user overrides (diameter / cooling rate / volume model)
        d_val = (self.sp_d.value()
                 if self.sp_d.isEnabled() else None)
        rate_val = float(self.sp_rate.value()) if self.sp_rate.isEnabled() else None
        vol = "sphere" if self.cmb_vol.currentIndex() == 1 else "deck"
        try:
            changed = self.session.apply_settings(
                d_nm=d_val, rate_K_per_ns=rate_val, volume_mode=vol)
        except Exception as exc:                                   # noqa: BLE001
            QMessageBox.warning(self, "Settings error", str(exc))
            return
        if changed:
            self.lbl_ov.setText("\u270e overrides: " + "; ".join(changed))
            for c in changed:
                self.log("OVERRIDE " + c)
                if "HYPOTHETICAL" in c:
                    self.log("WARNING " + c)
            self._fill_me_cards()
        else:
            self.lbl_ov.setText("")

        self.btn_run.setEnabled(False)
        self.st_ready.setText(" Running\u2026")
        self.t0 = time.time()
        self._worker2 = RunWorker(self.session, self)
        self._worker2.done_ok.connect(self._ran)
        self._worker2.done_err.connect(self._run_failed)
        self._worker2.start()

    def _run_failed(self, msg: str):
        self.btn_run.setEnabled(True)
        self.st_ready.setText(" Error")
        self.log("ERROR " + msg)
        QMessageBox.warning(self, "Comparison failed", msg)

    def _ran(self, res):
        self.result = res
        elapsed = time.time() - self.t0
        self.st_elapsed.setText(f"Elapsed: {elapsed:.1f} s")
        s = self.session
        self.num_txt.setPlainText("\n".join(s.numbers_lines(res)))
        self.lbl_c5.setText("\u2713 Comparison completed.")
        self.lbl_c5.setStyleSheet(f"color:{theme.GREEN};font-weight:700")
        for b_ in (self.btn_png, self.btn_csv, self.btn_pdf, self.btn_rec):
            b_.setEnabled(True)
        self.btn_run.setEnabled(True)
        self.st_ready.setText(" Comparison completed")
        self.log(f"ME m(300K)={res.m300:.3f}  P_rev={res.prev300:.3f}  "
                 f"rmse={res.rmse:.4f}  Tc={res.Tc:g} K")
        self._draw_figure()
        self.tabs.setCurrentIndex(1)

    # ------------------------------------------------------------ figure
    def _draw_figure(self):
        """Render with the Agg backend (same code path as the regression
        baseline) and show a scaled pixmap - avoids Qt canvas clipping."""
        from io import BytesIO
        from PySide6.QtGui import QPixmap
        from studio.core.plotting_engine import create_figure, style_dark
        rate = self.session.cfg.rate_K_per_ns
        panels = "abcd" if self.ck_hist.isChecked() else "abc"
        fig = create_figure(
            self.result, rate, panels=panels,
            show_mean=self.ck_mean.isChecked(), show_sem=self.ck_sem.isChecked(),
            show_me=self.ck_me.isChecked())
        if not self.ck_seeds.isChecked():
            for ln in list(fig.axes[0].lines):
                if ln.get_linewidth() == 0.5:
                    ln.remove()
        style_dark(fig)
        buf = BytesIO()
        fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
        import matplotlib.pyplot as plt
        plt.close(fig)
        self._plot_png = buf.getvalue()
        self.figure = fig
        pm = QPixmap()
        pm.loadFromData(self._plot_png)
        self.plot_label.setPixmap(pm.scaled(
            self.plot_scroll.viewport().size(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.plot_info.setText(
            f"Results: {rate:g} K/ns, D = {self.session.rf_d:g} nm, "
            f"N_seeds = {self.result.stats.n}   "
            f"(a) M_z(T) ensemble vs ME \u00b7 (b) final-state histogram \u00b7 "
            f"(c) transverse / |m| / m_s(T) \u00b7 (d) final M_z vs transverse share")

    def eventFilter(self, obj, ev):
        from PySide6.QtCore import QEvent
        if (obj is self.plot_scroll.viewport()
                and ev.type() == QEvent.Resize and getattr(self, "_plot_png", None)):
            from PySide6.QtGui import QPixmap
            pm = QPixmap()
            pm.loadFromData(self._plot_png)
            self.plot_label.setPixmap(pm.scaled(
                self.plot_scroll.viewport().size(),
                Qt.KeepAspectRatio, Qt.SmoothTransformation))
        return False

    def _restyle_figure(self):
        if self.result is not None:
            self._draw_figure()

    # ------------------------------------------------------------ export/save
    def export_one(self, kind: str):
        from studio.core.plotting_engine import save, arrays_csv
        if self.result is None:
            return
        rate = int(self.session.cfg.rate_K_per_ns)
        stem = f"mz_{rate}_studio"
        d = QFileDialog.getExistingDirectory(self, "Export to", self.last_export_dir)
        if not d:
            return
        self.last_export_dir = d
        if kind == "png":
            p = os.path.join(d, stem + ".png")
            save(self._export_fig(), p)
        elif kind == "csv":
            p = os.path.join(d, stem + ".csv")
            arrays_csv(p, self.result)
        else:
            p = os.path.join(d, stem + "_report.pdf")
            self._make_report(p)
        self.log(f"Exported {p}")

    def _export_fig(self):
        """Export uses the validated light-styled figure (regression path)."""
        from studio.core.plotting_engine import create_figure
        return create_figure(self.result, self.session.cfg.rate_K_per_ns)

    def _make_report(self, path: str):
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
        with PdfPages(path) as pdf:
            cover = plt.figure(figsize=(8.27, 11.69))
            cover.text(0.08, 0.93, "VAMPIRE \u2013 ME Comparison Report",
                       fontsize=20, weight="bold")
            cover.text(0.08, 0.88, f"Run: {self.session.run_dir}", fontsize=9)
            body = "\n".join(self.session.numbers_lines(self.result))
            cover.text(0.08, 0.82, body, fontsize=8, family="monospace",
                       va="top")
            pdf.savefig(cover)
            cover.clf()
            pdf.savefig(self._export_fig())
            plt.close("all")

    def act_save(self):
        from studio.core.audit_manager import save_record
        if self.result is None:
            QMessageBox.information(self, "Save record",
                                    "Run a comparison first.")
            return
        import io
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        buf = io.BytesIO()
        FigureCanvasAgg(self._export_fig()).print_png(buf)
        rec = save_record(self.session, self.result, self.issues,
                          figures={f"mz_{int(self.session.cfg.rate_K_per_ns)}.png":
                                   buf.getvalue()})
        self.log(f"Comparison record saved: {rec}")
        QMessageBox.information(self, "Save record", f"Saved:\n{rec}")

    # ------------------------------------------------------------ misc
    def _show_source(self, row, _col):
        table = self.sender()
        rec = table.record_at(row)
        if rec and rec.sources:
            SourceViewer(rec, self).show()

    def act_settings(self):
        QMessageBox.information(
            self, "Settings",
            "Settings live in the Comparison Settings card:\n"
            "  \u00b7 damping interpretation (rule M2 \u2014 guarded)\n"
            "  \u00b7 \u0394T grid (advanced, via record re-run)\n"
            "  \u00b7 material LUT must be in core/lut_registry.json (rule R1)")

    def act_help(self):
        QMessageBox.information(
            self, "Help",
            "1. Open a VAMPIRE run directory (folder with seed_*/DONE).\n"
            "2. Check extracted parameters and the Parameter Audit tab.\n"
            "3. Press Run Comparison; results appear in the Plots tab.\n"
            "4. Export PNG/CSV/PDF, or Save Record for a reproducible\n"
            "   audit package (record.json + arrays.csv + checksums).\n\n"
            "Physics is frozen to the validated me_B_roy pipeline; the app\n"
            "is read-only with respect to simulation data.")

    @staticmethod
    def _qcol(hexcode: str):
        from PySide6.QtGui import QColor
        return QColor(hexcode)
