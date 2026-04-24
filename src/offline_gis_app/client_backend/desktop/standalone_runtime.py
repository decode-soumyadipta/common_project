from __future__ import annotations

import os
from pathlib import Path


DEFAULT_APP_HOME_NAME = "OfflineGIS"


def _default_app_home() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / DEFAULT_APP_HOME_NAME
    return Path.home() / DEFAULT_APP_HOME_NAME


def _sqlite_url(path: Path) -> str:
    normalized = path.resolve()
    return f"sqlite:///{normalized.as_posix()}"


def configure_standalone_runtime(mode: str) -> Path:
    """Configure runtime environment for packaged desktop apps.

    Both server/client executables intentionally point to one shared local DB.
    Existing environment variables win to preserve explicit operator overrides.
    """

    app_home = (
        Path(os.environ.get("OFFLINE_GIS_HOME", "")).expanduser()
        if os.environ.get("OFFLINE_GIS_HOME")
        else _default_app_home()
    )
    app_home = app_home.resolve()
    data_root = app_home / "data"
    logs_root = app_home / "logs"
    db_path = app_home / "offline_gis.db"

    app_home.mkdir(parents=True, exist_ok=True)
    data_root.mkdir(parents=True, exist_ok=True)
    logs_root.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("OFFLINE_GIS_HOME", str(app_home))
    os.environ.setdefault("DATA_ROOT", str(data_root))
    os.environ.setdefault("DATABASE_URL", _sqlite_url(db_path))
    os.environ.setdefault("API_PORT", "8000")
    os.environ.setdefault("TITILER_BASE_URL", "http://127.0.0.1:8081")

    api_port = os.environ.get("API_PORT", "8000")
    server_host = (
        os.environ.get("OFFLINE_GIS_SERVER_HOST", "127.0.0.1") or "127.0.0.1"
    ).strip()

    if mode == "server":
        # Server app is LAN-facing by default; still overridable via environment.
        os.environ.setdefault("API_HOST", "0.0.0.0")
        os.environ.setdefault("DEPLOYMENT_TOPOLOGY", "split-lan")
    else:
        os.environ.setdefault("API_HOST", "127.0.0.1")

    # Client app points to LAN/local server host via OFFLINE_GIS_SERVER_HOST.
    if mode == "client":
        os.environ.setdefault("DEPLOYMENT_TOPOLOGY", "split-lan")
        os.environ.setdefault("SERVER_API_BASE_URL", f"http://{server_host}:{api_port}")

    return app_home
