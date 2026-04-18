import argparse

import uvicorn

from offline_gis_app.api.app import app
from offline_gis_app.config.settings import settings
from offline_gis_app.desktop.app_mode import DesktopAppMode


def run_api() -> None:
    uvicorn.run(app, host=settings.api_host, port=settings.api_port, log_level="info")


def run_desktop(mode: DesktopAppMode = DesktopAppMode.UNIFIED) -> None:
    from offline_gis_app.desktop.run_desktop import run

    raise SystemExit(run(app_mode=mode))


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline 3D GIS launcher")
    parser.add_argument("target", choices=["api", "desktop", "desktop-server", "desktop-client"])
    args = parser.parse_args()
    if args.target == "api":
        run_api()
        return
    run_desktop(mode=DesktopAppMode.from_cli_target(args.target))


if __name__ == "__main__":
    main()

