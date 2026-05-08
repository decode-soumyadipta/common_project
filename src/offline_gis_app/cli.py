import argparse

import uvicorn

from server_gateway.api.app import app
from platform_core.config.settings import settings
from client_desktop.backend.app_mode import DesktopAppMode
from client_desktop.backend.qt_compat import (
    QtDesktopRuntimeError,
    ensure_desktop_qt_runtime,
)


def run_api() -> None:
    uvicorn.run(app, host=settings.api_host, port=settings.api_port, log_level="info")


def run_desktop(mode: DesktopAppMode = DesktopAppMode.UNIFIED) -> None:
    try:
        qt_backend = ensure_desktop_qt_runtime()
    except QtDesktopRuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    from client_desktop.backend.run_desktop import run

    raise SystemExit(run(app_mode=mode, qt_backend=qt_backend))


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline 3D GIS launcher")
    parser.add_argument(
        "target", choices=["api", "desktop", "desktop-server", "desktop-client"]
    )
    args = parser.parse_args()
    if args.target == "api":
        run_api()
        return
    run_desktop(mode=DesktopAppMode.from_cli_target(args.target))


if __name__ == "__main__":
    main()
