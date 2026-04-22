from __future__ import annotations

import argparse
import os
import traceback
from pathlib import Path

from offline_gis_app.client_backend.desktop.app_mode import DesktopAppMode
from offline_gis_app.client_backend.desktop.qt_compat import QtDesktopRuntimeError, ensure_desktop_qt_runtime
from offline_gis_app.client_backend.desktop.run_desktop import run
from offline_gis_app.client_backend.desktop.standalone_runtime import configure_standalone_runtime


def _write_error_log(message: str) -> None:
    """Write startup/runtime errors to a local debug file."""
    try:
        log_dir = Path.home() / "OfflineGIS"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "server_error.log"
        with open(log_file, "a") as f:
            f.write(message + "\n")
    except Exception:
        pass  # Silently fail if we can't write the log


def _run_api_only() -> int:
    import uvicorn
    from offline_gis_app.server_backend.app import app

    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
    return 0


def main() -> int:
    try:
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--api-only", action="store_true")
        args, _ = parser.parse_known_args()

        if args.api_only or os.environ.get("OFFLINE_GIS_API_ONLY") == "1":
            return _run_api_only()

        configure_standalone_runtime(mode="server")
        qt_backend = ensure_desktop_qt_runtime()
        return run(app_mode=DesktopAppMode.SERVER, qt_backend=qt_backend)
    except QtDesktopRuntimeError as exc:
        error_msg = f"Qt Runtime Error: {str(exc)}"
        _write_error_log(error_msg)
        raise SystemExit(error_msg) from exc
    except Exception as exc:
        error_msg = f"Unexpected error: {str(exc)}\n{traceback.format_exc()}"
        _write_error_log(error_msg)
        raise SystemExit(error_msg) from exc


if __name__ == "__main__":
    raise SystemExit(main())
