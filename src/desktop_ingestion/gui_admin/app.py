from __future__ import annotations

import logging

from desktop_client.client_backend.desktop.app_mode import DesktopAppMode
from desktop_client.client_backend.desktop.qt_compat import (
    QtDesktopRuntimeError,
    ensure_desktop_qt_runtime,
)
from desktop_client.client_backend.desktop.run_desktop import run


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
