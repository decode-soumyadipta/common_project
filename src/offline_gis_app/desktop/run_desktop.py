from __future__ import annotations

import logging
import sys

from offline_gis_app.desktop.app_mode import DesktopAppMode
from offline_gis_app.desktop.logging_setup import configure_desktop_logging
from offline_gis_app.desktop.qt_compat import ensure_desktop_qt_runtime


def run(app_mode: DesktopAppMode = DesktopAppMode.UNIFIED, qt_backend: str | None = None) -> int:
    backend = (qt_backend or ensure_desktop_qt_runtime()).lower()
    from qtpy.QtWidgets import QApplication
    from offline_gis_app.desktop.main_window import MainWindow

    configure_desktop_logging()
    logging.getLogger("desktop").info(
        "Starting desktop application mode=%s qt_backend=%s", app_mode.value, backend
    )
    app = QApplication(sys.argv)
    window = MainWindow(app_mode=app_mode)
    window.show()
    logging.getLogger("desktop").info("Desktop main window shown")
    return app.exec()
