from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from offline_gis_app.desktop.app_mode import DesktopAppMode
from offline_gis_app.desktop.logging_setup import configure_desktop_logging
from offline_gis_app.desktop.main_window import MainWindow


def run(app_mode: DesktopAppMode = DesktopAppMode.UNIFIED) -> int:
    configure_desktop_logging()
    logging.getLogger("desktop").info("Starting desktop application mode=%s", app_mode.value)
    app = QApplication(sys.argv)
    window = MainWindow(app_mode=app_mode)
    window.show()
    logging.getLogger("desktop").info("Desktop main window shown")
    return app.exec()
