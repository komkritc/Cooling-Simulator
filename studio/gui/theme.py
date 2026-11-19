"""Dark/light theme (dark navy default) matching cooling_simulator/ui.png mockup. QSS only - no assets."""

BG = "#12161f"
BG_PANEL = "#1a2130"
BG_PANEL2 = "#202a3d"
BG_INPUT = "#141a26"
BORDER = "#2c3850"
FG = "#dfe6f2"
FG_DIM = "#8b98ad"
GREEN = "#3ddc84"
GREEN_DK = "#1f9d5b"
BLUE = "#5aa7ff"
AMBER = "#ffb020"
RED = "#ff5f56"
TITLE_BLUE = "#5aa7ff"

def _build_qss():
    return f"""
QMainWindow, QWidget {{ background:{BG}; color:{FG};
  font-family:'Segoe UI','DejaVu Sans',sans-serif; font-size:13px; }}
QToolBar {{ background:{BG_PANEL}; border:none; border-bottom:1px solid {BORDER}; padding:6px; }}
QToolBar QToolButton {{ background:{BG_PANEL2}; color:{FG}; border:1px solid {BORDER};
  border-radius:6px; padding:6px 14px; margin:0 3px; }}
QToolBar QToolButton:hover {{ border-color:{TITLE_BLUE}; }}
QLabel#appTitle {{ color:{TITLE_BLUE}; font-size:19px; font-weight:700; }}
QLabel#appSub {{ color:{FG}; font-size:12px; }}
QLabel#logoTxt {{ color:{TITLE_BLUE}; font-weight:700; font-size:13px; }}
QFrame#rail {{ background:{BG_PANEL}; border-right:1px solid {BORDER}; }}
QFrame#stepCard {{ background:{BG_PANEL2}; border:1px solid {BORDER}; border-radius:8px; }}
QLabel#stepNum {{ color:{TITLE_BLUE}; font-weight:800; font-size:15px; }}
QLabel#stepTitle {{ font-weight:700; }}
QLabel#stepDesc {{ color:{FG_DIM}; font-size:11px; }}
QFrame#card {{ background:{BG_PANEL}; border:1px solid {BORDER}; border-radius:10px; }}
QLabel#cardHead {{ font-weight:700; font-size:14px; }}
QLabel#cardHeadNum {{ color:{TITLE_BLUE}; font-weight:800; font-size:14px; }}
QGroupBox {{ border:1px solid {BORDER}; border-radius:8px; margin-top:10px;
  padding-top:6px; font-weight:600; }}
QGroupBox::title {{ subcontrol-origin:margin; left:10px; padding:0 4px; }}
QPushButton {{ background:{BG_PANEL2}; color:{FG}; border:1px solid {BORDER};
  border-radius:6px; padding:6px 14px; }}
QPushButton:hover {{ border-color:{TITLE_BLUE}; }}
QPushButton#runBtn {{ background:{GREEN_DK}; color:#fff; font-weight:800; border:none; }}
QPushButton#runBtn:hover {{ background:{GREEN}; color:#08281a; }}
QPushButton#runBtn:disabled {{ background:{BG_PANEL2}; color:{FG_DIM}; }}
QPushButton.chip {{ border-radius:10px; padding:2px 10px; font-size:11px; }}
QTabBar::tab {{ background:{BG_PANEL}; color:{FG_DIM}; padding:8px 18px;
  border:1px solid {BORDER}; border-bottom:none; border-top-left-radius:8px;
  border-top-right-radius:8px; margin-right:2px; }}
QTabBar::tab:selected {{ background:{BG_PANEL2}; color:{FG}; }}
QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QListWidget {{
  background:{BG_INPUT}; border:1px solid {BORDER}; border-radius:6px; padding:5px;
  color:{FG}; selection-background-color:{TITLE_BLUE}; }}
QTableWidget {{ background:{BG_INPUT}; gridline-color:{BORDER}; }}
QHeaderView::section {{ background:{BG_PANEL2}; color:{FG_DIM}; padding:6px;
  border:none; border-right:1px solid {BORDER}; border-bottom:1px solid {BORDER}; }}
QTableWidget QTableCornerButton::section {{ background:{BG_PANEL2}; border:none; }}
QCheckBox {{ spacing:8px; }} QCheckBox::indicator {{ width:16px; height:16px; }}
QProgressBar {{ background:{BG_INPUT}; border:1px solid {BORDER}; border-radius:6px;
  height:14px; text-align:center; color:{FG}; }}
QStatusBar {{ background:{BG_PANEL}; border-top:1px solid {BORDER}; color:{FG_DIM}; }}
QScrollBar:vertical {{ background:{BG_INPUT}; width:10px; }}
QScrollBar::handle:vertical {{ background:{BORDER}; border-radius:5px; min-height:30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height:0; }}
QScrollArea {{ border:none; }}
"""


QSS = _build_qss()

PALETTES = {
    "dark": dict(BG="#12161f", BG_PANEL="#1a2130", BG_PANEL2="#202a3d", BG_INPUT="#141a26",
                 BORDER="#2c3850", FG="#dfe6f2", FG_DIM="#8b98ad", GREEN="#3ddc84",
                 GREEN_DK="#1f9d5b", BLUE="#5aa7ff", AMBER="#ffb020", RED="#ff5f56",
                 TITLE_BLUE="#5aa7ff"),
    "light": dict(BG="#f4f6fa", BG_PANEL="#ffffff", BG_PANEL2="#e9eef6", BG_INPUT="#ffffff",
                  BORDER="#c3ccdb", FG="#1c2433", FG_DIM="#5d6b82", GREEN="#1f9d5b",
                  GREEN_DK="#1f9d5b", BLUE="#1769c2", AMBER="#b9770e", RED="#c0392b",
                  TITLE_BLUE="#1769c2"),
}
MODE = "dark"

def set_mode(mode: str):
    """Switch palette; rebuilds QSS from the (rebound) module colours."""
    global QSS, MODE
    mode = mode if mode in PALETTES else "dark"
    globals().update(PALETTES[mode])
    MODE = mode
    QSS = _build_qss()

def apply_theme(app, mode: str | None = None):
    if mode:
        set_mode(mode)
    app.setStyleSheet(QSS)
