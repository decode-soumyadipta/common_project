from __future__ import annotations

from offline_gis_app.client_backend.desktop.app_mode import DesktopAppMode
from offline_gis_app.client_backend.desktop.qt_compat import QtDesktopRuntimeError, ensure_desktop_qt_runtime
from offline_gis_app.client_backend.desktop.run_desktop import run
from offline_gis_app.client_backend.desktop.standalone_runtime import configure_standalone_runtime


def main() -> int:
    configure_standalone_runtime(mode="client")
    try:
        qt_backend = ensure_desktop_qt_runtime()
    except QtDesktopRuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    return run(app_mode=DesktopAppMode.CLIENT, qt_backend=qt_backend)


if __name__ == "__main__":
    raise SystemExit(main())
