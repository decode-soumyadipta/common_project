from __future__ import annotations

import logging

from client_desktop.backend.app_mode import DesktopAppMode
from client_desktop.backend.qt_compat import (
    QtDesktopRuntimeError,
    ensure_desktop_qt_runtime,
)
from client_desktop.backend.run_desktop import run


LOGGER = logging.getLogger("desktop_ingestion.gui_admin")


def run_admin_desktop() -> int:
    """Launch the dedicated admin desktop runtime in SERVER mode."""
    qt_backend = ensure_desktop_qt_runtime()
    LOGGER.info("Starting admin desktop mode with backend=%s", qt_backend)
    return run(app_mode=DesktopAppMode.SERVER, qt_backend=qt_backend)


def main() -> int:
    try:
        return run_admin_desktop()
    except QtDesktopRuntimeError as exc:
        raise SystemExit(str(exc)) from exc


__all__ = ["main", "run_admin_desktop"]
