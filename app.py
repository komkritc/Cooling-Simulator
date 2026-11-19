#!/usr/bin/env python3
"""Entry point: ME Cooling Simulator (simple GUI).  Old full GUI: app_full.py."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from studio.gui import theme
from studio.gui.simple_window import SimpleWindow

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ME Cooling Simulator")
    from PySide6.QtCore import QSettings
    saved = str(QSettings("CoolingModelComparison", "MECoolingSimulator").value("theme", "light"))
    theme.apply_theme(app, saved)
    win = SimpleWindow()
    win.show()
    if len(sys.argv) > 1:                     # optional: preload a VAMPIRE run folder
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: win.open_path(sys.argv[1]))
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
