from __future__ import annotations

import logging
import sys
from pathlib import Path

from offline_gis_app.client_backend.desktop.app_mode import DesktopAppMode
from offline_gis_app.client_backend.desktop.logging_setup import configure_desktop_logging
from offline_gis_app.client_backend.desktop.qt_compat import ensure_desktop_qt_runtime


def _write_startup_trace(message: str) -> None:
    try:
        log_dir = Path.home() / "OfflineGIS"
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / "client_startup_trace.log", "a", encoding="utf-8") as handle:
            handle.write(message + "\n")
    except Exception:
        pass


def run(app_mode: DesktopAppMode = DesktopAppMode.UNIFIED, qt_backend: str | None = None) -> int:
    _write_startup_trace("run:enter")
    backend = (qt_backend or ensure_desktop_qt_runtime()).lower()
    _write_startup_trace(f"run:backend={backend}")
    try:
        from qtpy.QtWidgets import QApplication, QLabel, QMessageBox, QVBoxLayout, QWidget
        from qtpy.QtCore import QCoreApplication, Qt, QTimer
        _write_startup_trace("run:qt_widgets_import_ok")
    except Exception as exc:  # pragma: no cover - runtime defensive branch
        _write_startup_trace(f"run:qt_widgets_import_error={exc!r}")
        raise

    configure_desktop_logging()
    logging.getLogger("desktop").info(
        "Starting desktop application mode=%s qt_backend=%s", app_mode.value, backend
    )
    _write_startup_trace(f"run:start mode={app_mode.value} backend={backend}")

    # Required by QtWebEngine: this must be set before QApplication is created.
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    _write_startup_trace("run:aa_share_openglcontexts_set")

    # Import WebEngine module before QApplication to satisfy QtWebEngine init ordering.
    from qtpy import QtWebEngineWidgets  # noqa: F401
    _write_startup_trace("run:qtwebengine_preloaded")

    app = QApplication(sys.argv)
    _write_startup_trace("run:qapplication_created")

    # Show an immediate lightweight startup window so users get instant visual
    # feedback even if heavy initialization takes a few seconds.
    startup_window = QWidget()
    startup_window.setWindowTitle("Offline 3D GIS - Loading")
    startup_window.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
    startup_window.setMinimumSize(420, 120)
    startup_layout = QVBoxLayout(startup_window)
    startup_layout.addWidget(QLabel("Starting Offline 3D GIS..."))
    startup_layout.addWidget(QLabel("Loading map engine and local services"))
    startup_window.show()
    startup_window.raise_()
    startup_window.activateWindow()
    app.processEvents()
    _write_startup_trace("run:startup_window_shown")

    holder: dict[str, object] = {}

    def _launch_main_window() -> None:
        try:
            _write_startup_trace("run:main_window_import_start")
            from offline_gis_app.client_backend.desktop.main_window import MainWindow

            _write_startup_trace("run:main_window_import_done")
            window = MainWindow(app_mode=app_mode)
            holder["window"] = window
            _write_startup_trace("run:main_window_init_done")
            window.show()
            window.setWindowState(
                (window.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive
            )
            window.raise_()
            window.activateWindow()
            startup_window.close()
            app.processEvents()
            _write_startup_trace("run:main_window_shown")
            logging.getLogger("desktop").info("Desktop main window shown")
        except Exception as exc:  # pragma: no cover - runtime defensive branch
            _write_startup_trace(f"run:main_window_init_error={exc!r}")
            logging.getLogger("desktop").exception("Main window initialization failed")
            QMessageBox.critical(
                startup_window,
                "Offline 3D GIS Startup Error",
                f"Desktop UI failed to initialize:\n{exc}",
            )
            startup_window.close()
            app.quit()

    QTimer.singleShot(0, _launch_main_window)
    return app.exec()
