from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from offline_gis_app.desktop.logging_setup import configure_desktop_logging
from offline_gis_app.desktop.main_window import MainWindow


def run() -> int:
    configure_desktop_logging()
    logging.getLogger("desktop").info("Starting desktop application")
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    logging.getLogger("desktop").info("Desktop main window shown")
    return app.exec()
