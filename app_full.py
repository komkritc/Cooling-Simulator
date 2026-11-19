#!/usr/bin/env python3
"""Entry point: VAMPIRE - Master Equation Comparison Studio (full PySide6 GUI)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from studio.gui import theme
from studio.gui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("VAMPIRE-ME Comparison Studio")
    theme.apply_theme(app)
    win = MainWindow()
    win.show()
    if len(sys.argv) > 1:
        win.ed_run.setText(sys.argv[1])
        win._worker = __import__("studio.gui.widgets", fromlist=["OpenWorker"]).OpenWorker(sys.argv[1], win)
        win._worker.done_ok.connect(win._opened)
        win._worker.done_err.connect(win._open_failed)
        win._worker.start()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
