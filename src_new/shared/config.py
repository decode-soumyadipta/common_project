"""Centralized configuration manager for the geospatial microservices system.

Loads all settings from a .env file at the project root using python-dotenv.
All services and clients import from this module — no hardcoded values elsewhere.

Usage:
    from src_new.shared.config import settings

    db_url = settings.database_url
    data_root = settings.data_root
"""
from __future__ import annotations

import contextlib
import logging
import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve the project root as the directory two levels above this file: src_new/shared/config.py → src_new/ → project_root/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Load .env from the project root before Pydantic reads env vars. This ensures variables are available even when the process is started from a different working directory.
load_dotenv(_PROJECT_ROOT / ".env", override=False)

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Full system configuration loaded from environment variables / .env.

    Requirement 4: Centralized Configuration Management.
    All configurable parameters are defined here with documented defaults.
    When a variable is missing, the default is used and a warning is logged.
    """

    # ------------------------------------------------------------------------- 1. Data storage -------------------------------------------------------------------------
    data_root: Path = Path().resolve()
    """Root directory for all geospatial data files (COGs, MBTiles, etc.)."""

    # ------------------------------------------------------------------------- 2. Database -------------------------------------------------------------------------
    database_url: str = f"sqlite:///{_PROJECT_ROOT.as_posix()}/offline_gis.db"
    """SQLAlchemy-compatible database URL. Use postgresql+psycopg2:// for PostGIS."""

    # ------------------------------------------------------------------------- 3. API / service binding -------------------------------------------------------------------------
    api_host: str = "127.0.0.1"
    """Host interface for all services. Set to LAN IP for multi-machine deployment."""

    api_port: int = 8000
    """Default API port (used when a service-specific port is not set)."""

    # ------------------------------------------------------------------------- 4. Service URLs (used by clients and inter-service communication) -------------------------------------------------------------------------
    titiler_base_url: str = "http://127.0.0.1:8002"
    """Base URL of the TiTiler tile service."""

    cesium_base_url: str = "http://127.0.0.1:8000/cesium"
    """Base URL for offline CesiumJS assets served by the tile service."""

    ingestion_service_url: str = "http://127.0.0.1:8001"
    """Base URL of the Ingestion Service (Server 1)."""

    query_service_url: str = "http://127.0.0.1:8003"
    """Base URL of the Query Service (Server 2)."""

    tile_service_url: str = "http://127.0.0.1:8002"
    """Base URL of the Tile Service (Server 1)."""

    # ------------------------------------------------------------------------- 5. Service ports (used by service entry points) -------------------------------------------------------------------------
    ingestion_service_port: int = 8001
    """Port for the Ingestion Service."""

    tile_service_port: int = 8002
    """Port for the Tile Service."""

    query_service_port: int = 8003
    """Port for the Query Service."""

    # ------------------------------------------------------------------------- 6. Upload / tile limits -------------------------------------------------------------------------
    max_upload_size: int = 10 * 1024 * 1024 * 1024  # 10 GB
    """Maximum allowed upload size in bytes."""

    tile_cache_size: int = 512
    """Maximum number of tiles to keep in the in-memory LRU cache."""

    # ------------------------------------------------------------------------- 7. GDAL performance tuning -------------------------------------------------------------------------
    gdal_disable_readdir_on_open: str = "EMPTY_DIR"
    """GDAL_DISABLE_READDIR_ON_OPEN value. Speeds up COG access."""

    gdal_http_merge_consecutive_ranges: str = "YES"
    """GDAL_HTTP_MERGE_CONSECUTIVE_RANGES value. Reduces HTTP round-trips."""

    gdal_cachemax: int = 1024
    """GDAL raster block cache size in MB. Increase on machines with more RAM."""

    gdal_use_opencl: bool = False
    """Enable GDAL OpenCL GPU acceleration for warp operations (NVIDIA/AMD). Set GDAL_USE_OPENCL=true in .env on Windows with CUDA-capable GDAL builds."""

    # ------------------------------------------------------------------------- 8. Security / network -------------------------------------------------------------------------
    allowed_hosts: str = "127.0.0.1"
    """Comma-separated list of allowed client IP addresses for LAN security."""

    bind_all_interfaces: bool = False
    """When True, services bind to 0.0.0.0 instead of api_host. Use with caution."""

    # ------------------------------------------------------------------------- 9. Logging -------------------------------------------------------------------------
    log_level: str = "INFO"
    """Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL."""

    log_format: str = "text"
    """Log output format: 'text' for human-readable, 'json' for structured logs."""

    log_output_path: str = ""
    """Path to log file. Empty string means stdout only."""

    # ------------------------------------------------------------------------- 10. Deployment topology (legacy compat) -------------------------------------------------------------------------
    deployment_topology: Literal["same-machine", "split-lan", "hybrid", "distributed"] = (
        "same-machine"
    )

    # ------------------------------------------------------------------------- 11. Ingestion performance (preserved from existing settings) -------------------------------------------------------------------------
    max_ingest_workers: int = 5
    ingest_checkpoint_interval: int = 1
    ingest_item_max_retries: int = 3
    ingest_memory_budget_mb: int = 512
    ingest_window_chunk_size: int = 1024
    ingest_enable_cog_conversion: bool = True
    ingest_cog_overwrite: bool = False

    # ------------------------------------------------------------------------- 12. COG / GDAL output settings -------------------------------------------------------------------------
    cog_blocksize: int = 512
    cog_compression: str = "LZW"
    cog_overview_resampling: str = "average"
    ingest_organize_outputs: bool = True
    ingest_output_base_dir: str = "processed_outputs"

    # ------------------------------------------------------------------------- 13. TiTiler tile matrix -------------------------------------------------------------------------
    titiler_tile_matrix_set_id: str = "WebMercatorQuad"

    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_prefix="",
        case_sensitive=False,
        extra="ignore",  # Ignore unknown env vars without crashing
    )

    def get_allowed_hosts_list(self) -> list[str]:
        """Return ALLOWED_HOSTS as a parsed list of IP strings."""
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]

    def apply_gdal_env(self) -> None:
        """Set GDAL environment variables from config.

        Call this before any GDAL/Rasterio operation to ensure consistent
        performance tuning across all services.
        """
        import platform
        import sys

        prefix = sys.prefix
        is_windows = platform.system() == "Windows"

        if is_windows:
            gdal_bin = os.path.join(prefix, "Library", "bin")
            gdal_plugins = os.path.join(prefix, "Library", "lib", "gdalplugins")
            gdal_data = os.path.join(prefix, "Library", "share", "gdal")
            proj_data = os.path.join(prefix, "Library", "share", "proj")
        else:
            gdal_bin = ""
            gdal_plugins = os.path.join(prefix, "lib", "gdalplugins")
            gdal_data = os.path.join(prefix, "share", "gdal")
            proj_data = os.path.join(prefix, "share", "proj")

        # 1. Apply Windows DLL dependencies path
        if is_windows and gdal_bin and os.path.exists(gdal_bin):
            if gdal_bin not in os.environ.get("PATH", ""):
                os.environ["PATH"] = gdal_bin + os.pathsep + os.environ.get("PATH", "")
            if hasattr(os, "add_dll_directory"):
                with contextlib.suppress(Exception):
                    os.add_dll_directory(gdal_bin)

        # 2. Set GDAL driver path if plugins exist
        if gdal_plugins and os.path.exists(gdal_plugins):
            os.environ.setdefault("GDAL_DRIVER_PATH", gdal_plugins)

        # 3. Set GDAL data path if it exists
        if gdal_data and os.path.exists(gdal_data):
            os.environ.setdefault("GDAL_DATA", gdal_data)

        # 4. Set PROJ data paths if they exist
        if proj_data and os.path.exists(proj_data):
            os.environ.setdefault("PROJ_DATA", proj_data)
            os.environ.setdefault("PROJ_LIB", proj_data)  # compat legacy

        # 5. Apply general performance variables
        os.environ["GDAL_CACHEMAX"] = str(self.gdal_cachemax)
        os.environ["GDAL_NUM_THREADS"] = "ALL_CPUS"

        # 5b. GPU acceleration (Windows NVIDIA / AMD OpenCL)
        if self.gdal_use_opencl:
            os.environ["GDAL_USE_OPENCL"] = "YES"
        os.environ.setdefault(
            "GDAL_DISABLE_READDIR_ON_OPEN", self.gdal_disable_readdir_on_open
        )
        os.environ.setdefault(
            "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", self.gdal_http_merge_consecutive_ranges
        )

        # 6. Monkeypatch rasterio.open to support sidecar .prj files by writing .aux.xml sidecars
        try:
            import rasterio
            if getattr(rasterio.open, "__module__", "") == "rasterio" and not getattr(rasterio, "_patched_for_sidecar_prj", False):
                _orig_open = rasterio.open
                from pathlib import Path

                def custom_open(fp, mode="r", *args, **kwargs):
                    if mode == "r" and (isinstance(fp, (str, Path)) or hasattr(fp, "__fspath__")):
                        try:
                            p = Path(fp)
                            if p.suffix.lower() in {".j2k", ".jp2"}:
                                prj = p.with_suffix(".prj")
                                aux = p.with_name(p.name + ".aux.xml")
                                if not aux.exists():
                                    wkt = ""
                                    if prj.exists():
                                        prj_text = prj.read_text().strip()
                                        if "|||" in prj_text:
                                            prj_text = prj_text.split("|||")[0].strip()
                                        if prj_text:
                                            wkt = prj_text
                                    if not wkt:
                                        from rasterio.crs import CRS
                                        wkt = CRS.from_epsg(4326).to_wkt()
                                    if wkt:
                                        xml_content = f'<PAMDataset>\n  <SRS dataAxisToSRSAxisMapping="1,2">{wkt}</SRS>\n</PAMDataset>\n'
                                        aux.write_text(xml_content, encoding="utf-8")
                                
                                # Temporarily change GDAL_DISABLE_READDIR_ON_OPEN so GDAL scans for our aux.xml file
                                old_val = os.environ.get("GDAL_DISABLE_READDIR_ON_OPEN")
                                os.environ["GDAL_DISABLE_READDIR_ON_OPEN"] = "NO"
                                try:
                                    return _orig_open(fp, mode, *args, **kwargs)
                                finally:
                                    if old_val is not None:
                                        os.environ["GDAL_DISABLE_READDIR_ON_OPEN"] = old_val
                                    else:
                                        os.environ.pop("GDAL_DISABLE_READDIR_ON_OPEN", None)
                        except Exception:
                            pass
                    return _orig_open(fp, mode, *args, **kwargs)

                rasterio.open = custom_open
                rasterio._patched_for_sidecar_prj = True
        except ImportError:
            pass



def _build_settings() -> Settings:
    """Construct Settings, logging a warning for any missing required variables."""
    instance = Settings()
    # Warn if critical variables are still at their defaults (likely not set in .env)
    if instance.database_url == "sqlite:///./offline_gis.db":
        logger.debug(
            "DATABASE_URL not set in .env; using SQLite default. "
            "Set DATABASE_URL for PostGIS in production."
        )
    return instance


settings: Settings = _build_settings()

__all__ = ["Settings", "settings"]
