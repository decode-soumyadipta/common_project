from __future__ import annotations

from offline_gis_app.desktop.app_mode import DesktopAppMode
from offline_gis_app.desktop.qt_compat import QtDesktopRuntimeError, ensure_desktop_qt_runtime
from offline_gis_app.desktop.run_desktop import run
from offline_gis_app.desktop.standalone_runtime import configure_standalone_runtime


def main() -> int:
    configure_standalone_runtime(mode="server")
    try:
        qt_backend = ensure_desktop_qt_runtime()
    except QtDesktopRuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    return run(app_mode=DesktopAppMode.SERVER, qt_backend=qt_backend)


if __name__ == "__main__":
    raise SystemExit(main())
