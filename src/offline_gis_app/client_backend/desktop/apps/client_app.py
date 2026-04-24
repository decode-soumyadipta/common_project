from __future__ import annotations

import argparse
import os
import traceback
from pathlib import Path
from datetime import datetime

from offline_gis_app.client_backend.desktop.app_mode import DesktopAppMode
from offline_gis_app.client_backend.desktop.qt_compat import (
    QtDesktopRuntimeError,
    select_qt_api,
)
from offline_gis_app.client_backend.desktop.run_desktop import run
from offline_gis_app.client_backend.desktop.standalone_runtime import (
    configure_standalone_runtime,
)


def _write_error_log(message: str) -> None:
    """Write startup/runtime errors to a local debug file."""
    try:
        log_dir = Path.home() / "OfflineGIS"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "client_error.log"
        with open(log_file, "a") as f:
            f.write(message + "\n")
    except Exception:
        pass  # Silently fail if we can't write the log


def _write_startup_trace(message: str) -> None:
    try:
        log_dir = Path.home() / "OfflineGIS"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "client_startup_trace.log"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"{timestamp} | {message}\n")
    except Exception:
        pass


def _run_api_only() -> int:
    import uvicorn
    from offline_gis_app.server_backend.app import app

    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
    return 0


def main() -> int:
    try:
        _write_startup_trace("client_main_enter")
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--api-only", action="store_true")
        args, _ = parser.parse_known_args()
        _write_startup_trace(f"args_parsed api_only={args.api_only}")

        # Client should only enter API-only mode when explicitly requested.
        # This avoids accidental headless launches if OFFLINE_GIS_API_ONLY leaks
        # into the parent environment.
        if args.api_only:
            _write_startup_trace("api_only_mode_selected")
            return _run_api_only()

        # Safer defaults for offline systems where GPU sandbox or
        # graphics backend issues can prevent WebEngine windows from appearing.
        os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
        os.environ.setdefault("QT_OPENGL", "software")
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
        _write_startup_trace("qt_env_configured")

        configure_standalone_runtime(mode="client")
        _write_startup_trace("standalone_runtime_configured")
        # Avoid blocking preflight probes at startup; select backend and let
        # actual runtime imports occur during GUI startup.
        qt_backend = select_qt_api()
        _write_startup_trace(f"qt_backend_selected={qt_backend}")
        _write_startup_trace("calling_run_desktop")
        return run(app_mode=DesktopAppMode.CLIENT, qt_backend=qt_backend)
    except QtDesktopRuntimeError as exc:
        error_msg = f"Qt Runtime Error: {str(exc)}"
        _write_error_log(error_msg)
        _write_startup_trace("qt_runtime_error")
        raise SystemExit(error_msg) from exc
    except Exception as exc:
        error_msg = f"Unexpected error: {str(exc)}\n{traceback.format_exc()}"
        _write_error_log(error_msg)
        _write_startup_trace("unexpected_error")
        raise SystemExit(error_msg) from exc


if __name__ == "__main__":
    raise SystemExit(main())
