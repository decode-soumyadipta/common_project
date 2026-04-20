from __future__ import annotations

import logging
import platform
import sys

from offline_gis_app.desktop.app_mode import DesktopAppMode
from offline_gis_app.desktop.logging_setup import configure_desktop_logging


def _desktop_runtime_error_message(exc: Exception) -> str:
    system_name = platform.system().lower()
    lines = [
        "Desktop runtime dependencies are missing or incompatible.",
        f"Original error: {exc}",
        "",
        "For conda (recommended):",
        "  conda install -c conda-forge pyside6 pyside6-webengine",
        "  # fallback on some channel builds: conda install -c conda-forge pyside6 pyside6-addons",
        "",
        "For venv/pip:",
        "  pip install -e .[desktop]",
        "",
        "Quick check:",
        "  python -c \"from PySide6.QtWebEngineWidgets import QWebEngineView; print('QtWebEngine OK')\"",
    ]
    if system_name == "windows":
        lines.extend(
            [
                "",
                "Windows note:",
                "  If DLL load errors persist, install the Microsoft Visual C++ 2015-2022 Redistributable (x64)",
                "  and recreate the environment.",
            ]
        )
    return "\n".join(lines)


def _load_desktop_runtime() -> tuple[type, type]:
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView as _QWebEngineView  # noqa: F401
        from PySide6.QtWidgets import QApplication as _QApplication
        from offline_gis_app.desktop.main_window import MainWindow as _MainWindow
    except Exception as exc:  # pragma: no cover - only triggers on broken desktop runtime
        raise RuntimeError(_desktop_runtime_error_message(exc)) from exc
    return _QApplication, _MainWindow


def run(app_mode: DesktopAppMode = DesktopAppMode.UNIFIED) -> int:
    configure_desktop_logging()
    logger = logging.getLogger("desktop")
    logger.info("Starting desktop application mode=%s", app_mode.value)

    try:
        QApplication, MainWindow = _load_desktop_runtime()
    except RuntimeError as exc:
        logger.error("%s", exc)
        print(str(exc), file=sys.stderr)
        return 2

    app = QApplication(sys.argv)
    window = MainWindow(app_mode=app_mode)
    window.show()
    logger.info("Desktop main window shown")
    return app.exec()
