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

    # ── GDAL / PROJ data paths (critical on Windows with conda) ──────────────
    # Without these, rasterio/GDAL cannot find projection definitions and every
    # COG tile request fails with "Failed to obtain image tile".
    _configure_gdal_proj_paths()

    # ── GDAL performance / compatibility settings ─────────────────────────────
    # These fix "Read failed" errors on Windows with non-COG GeoTIFFs.
    os.environ.setdefault("GDAL_NUM_THREADS", "1")
    os.environ.setdefault("VSI_CACHE", "TRUE")
    os.environ.setdefault("VSI_CACHE_SIZE", "10000000")
    os.environ.setdefault("GDAL_CACHEMAX", "512")
    os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")

    api_port = os.environ.get("API_PORT", "8000")
    server_host = (
        os.environ.get("OFFLINE_GIS_SERVER_HOST", "127.0.0.1") or "127.0.0.1"
    ).strip()

    if mode == "server":
        os.environ.setdefault("API_HOST", "0.0.0.0")
        os.environ.setdefault("DEPLOYMENT_TOPOLOGY", "split-lan")
    else:
        os.environ.setdefault("API_HOST", "127.0.0.1")

    if mode == "client":
        os.environ.setdefault("DEPLOYMENT_TOPOLOGY", "split-lan")
        os.environ.setdefault("SERVER_API_BASE_URL", f"http://{server_host}:{api_port}")

    return app_home


def _configure_gdal_proj_paths() -> None:
    """Set GDAL_DATA and PROJ_DATA/PROJ_LIB if not already set.

    On Windows with conda the env vars are only set inside an activated shell.
    When the app is launched via a shortcut or double-click they are absent,
    causing rasterio/GDAL to fail silently on every tile request.
    """
    import sys
    from pathlib import Path as _Path

    python_exe = _Path(sys.executable).resolve()
    env_root = python_exe.parent  # conda env root on Windows; bin/ parent on Unix

    # conda on Windows: <env>\Library\share\gdal  and  <env>\Library\share\proj
    gdal_candidate = env_root / "Library" / "share" / "gdal"
    proj_candidate = env_root / "Library" / "share" / "proj"

    # conda on macOS/Linux: <env>/share/gdal  and  <env>/share/proj
    if not gdal_candidate.exists():
        gdal_candidate = env_root.parent / "share" / "gdal"
    if not proj_candidate.exists():
        proj_candidate = env_root.parent / "share" / "proj"

    # pyproj bundled data (venv / pip install)
    if not proj_candidate.exists():
        try:
            import pyproj
            proj_candidate = _Path(pyproj.datadir.get_data_dir())
        except Exception:
            pass

    # rasterio bundled gdal_data (venv / pip install)
    if not gdal_candidate.exists():
        try:
            import rasterio
            gdal_candidate = _Path(rasterio.__file__).parent / "gdal_data"
        except Exception:
            pass

    if gdal_candidate.exists():
        os.environ.setdefault("GDAL_DATA", str(gdal_candidate))
    if proj_candidate.exists():
        os.environ.setdefault("PROJ_DATA", str(proj_candidate))
        os.environ.setdefault("PROJ_LIB",  str(proj_candidate))
