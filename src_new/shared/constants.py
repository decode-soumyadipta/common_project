"""System-wide constants for the geospatial microservices platform.

All services and clients import constants from this module.
No magic numbers or hardcoded strings should appear elsewhere.

Requirement 12.5: src_new/shared/constants.py defining SUPPORTED_FORMATS,
EPSG codes, TILE_SIZE, MAX_UPLOAD_SIZE_DEFAULT.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Supported geospatial file formats
# ---------------------------------------------------------------------------

SUPPORTED_FORMATS: frozenset[str] = frozenset({"tif", "jp2", "mbtiles"})
"""Normalized (lowercase, no dot) file extensions accepted by the ingestion service."""

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".tif", ".tiff", ".jp2", ".j2k", ".j2c", ".mbtiles"})
"""Raw file extensions (with dot) accepted by the ingestion service."""

FORMAT_MIME_TYPES: dict[str, str] = {
    "tif": "image/tiff",
    "jp2": "image/jp2",
    "mbtiles": "application/x-sqlite3",
}
"""MIME types for each supported format."""

# ---------------------------------------------------------------------------
# EPSG / CRS codes
# ---------------------------------------------------------------------------

EPSG_WGS84: int = 4326
"""WGS 84 geographic coordinate system — standard for GPS and web maps."""

EPSG_WEB_MERCATOR: int = 3857
"""Web Mercator projection — used by TiTiler and CesiumJS tile layers."""

EPSG_UTM_ZONE_44N: int = 32644
"""UTM Zone 44N — common projection for South Asian aerial imagery."""

EPSG_UTM_ZONE_45N: int = 32645
"""UTM Zone 45N — common projection for eastern South Asian imagery."""

DEFAULT_CRS: str = f"EPSG:{EPSG_WGS84}"
"""Default CRS string used when no CRS is specified."""

TILE_CRS: str = f"EPSG:{EPSG_WEB_MERCATOR}"
"""CRS used for tile serving (Web Mercator)."""

# ---------------------------------------------------------------------------
# Tile dimensions
# ---------------------------------------------------------------------------

TILE_SIZE: int = 256
"""Standard tile size in pixels (width and height). Used by TiTiler and CesiumJS."""

TILE_SIZE_PREVIEW: int = 512
"""Tile size for preview/thumbnail images."""

TILE_MIN_ZOOM: int = 0
"""Minimum zoom level for tile pyramid."""

TILE_MAX_ZOOM: int = 22
"""Maximum zoom level for tile pyramid."""

# ---------------------------------------------------------------------------
# Upload / file size limits
# ---------------------------------------------------------------------------

MAX_UPLOAD_SIZE_DEFAULT: int = 10 * 1024 * 1024 * 1024  # 10 GB
"""Default maximum upload size in bytes (10 GB). Override with MAX_UPLOAD_SIZE env var."""

MAX_UPLOAD_SIZE_SMALL: int = 100 * 1024 * 1024  # 100 MB
"""Small upload limit for testing and development environments."""

# ---------------------------------------------------------------------------
# Database / PostGIS
# ---------------------------------------------------------------------------

POSTGIS_SRID: int = EPSG_WGS84
"""Default SRID for PostGIS geometry columns."""

SPATIAL_INDEX_TYPE: str = "GIST"
"""PostGIS spatial index type used for geometry columns."""

# ---------------------------------------------------------------------------
# Ingestion pipeline
# ---------------------------------------------------------------------------

COG_BLOCKSIZE: int = 512
"""Default COG tile block size in pixels."""

COG_COMPRESSION: str = "LZW"
"""Default COG compression algorithm."""

COG_OVERVIEW_RESAMPLING: str = "average"
"""Default resampling algorithm for COG overview levels."""

INGEST_STATUS_QUEUED: str = "queued"
INGEST_STATUS_PROCESSING: str = "processing"
INGEST_STATUS_CATALOGED: str = "cataloged"
INGEST_STATUS_FAILED: str = "failed"

INGEST_STATUSES: frozenset[str] = frozenset(
    {INGEST_STATUS_QUEUED, INGEST_STATUS_PROCESSING, INGEST_STATUS_CATALOGED, INGEST_STATUS_FAILED}
)

# ---------------------------------------------------------------------------
# API / service defaults
# ---------------------------------------------------------------------------

DEFAULT_API_HOST: str = "127.0.0.1"
DEFAULT_INGESTION_SERVICE_PORT: int = 8001
DEFAULT_TILE_SERVICE_PORT: int = 8002
DEFAULT_QUERY_SERVICE_PORT: int = 8003

API_VERSION: str = "v1"
API_PREFIX: str = f"/api/{API_VERSION}"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

DEFAULT_LOG_LEVEL: str = "INFO"
DEFAULT_LOG_FORMAT: str = "text"

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

LOCALHOST_ADDRESSES: frozenset[str] = frozenset({"127.0.0.1", "::1", "localhost"})
"""IP addresses always considered local/trusted."""

__all__ = [
    # Formats
    "SUPPORTED_FORMATS",
    "SUPPORTED_EXTENSIONS",
    "FORMAT_MIME_TYPES",
    # EPSG codes
    "EPSG_WGS84",
    "EPSG_WEB_MERCATOR",
    "EPSG_UTM_ZONE_44N",
    "EPSG_UTM_ZONE_45N",
    "DEFAULT_CRS",
    "TILE_CRS",
    # Tile dimensions
    "TILE_SIZE",
    "TILE_SIZE_PREVIEW",
    "TILE_MIN_ZOOM",
    "TILE_MAX_ZOOM",
    # Upload limits
    "MAX_UPLOAD_SIZE_DEFAULT",
    "MAX_UPLOAD_SIZE_SMALL",
    # Database
    "POSTGIS_SRID",
    "SPATIAL_INDEX_TYPE",
    # Ingestion
    "COG_BLOCKSIZE",
    "COG_COMPRESSION",
    "COG_OVERVIEW_RESAMPLING",
    "INGEST_STATUS_QUEUED",
    "INGEST_STATUS_PROCESSING",
    "INGEST_STATUS_CATALOGED",
    "INGEST_STATUS_FAILED",
    "INGEST_STATUSES",
    # API
    "DEFAULT_API_HOST",
    "DEFAULT_INGESTION_SERVICE_PORT",
    "DEFAULT_TILE_SERVICE_PORT",
    "DEFAULT_QUERY_SERVICE_PORT",
    "API_VERSION",
    "API_PREFIX",
    # Logging
    "DEFAULT_LOG_LEVEL",
    "DEFAULT_LOG_FORMAT",
    # Security
    "LOCALHOST_ADDRESSES",
]
