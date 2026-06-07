"""MBTiles format handler.

Provides ``validate`` and ``extract_metadata`` for MBTiles files.

MBTiles is an SQLite database containing pre-rendered map tiles.
Metadata is stored in the ``metadata`` table; tile bounds and zoom levels
are read from there rather than via GDAL (GDAL support for MBTiles is
limited and not always available).

Format detection logic adapted from:
- ``src/platform_core/ingestion/services/file_kind.py``
- ``src/platform_core/ingestion/services/file_grouping_service.py``

Requirement 9.3: Format-specific parsers for GeoTIFF, JPEG2000, and MBTiles.
Requirement 9.4: All GDAL operations use environment variables from Configuration_Manager.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict

from src_new.shared.config import settings
from src_new.shared.utils.file_validation import is_mbtiles

logger = logging.getLogger(__name__)

# Required tables in a valid MBTiles database
_REQUIRED_TABLES = {"tiles", "metadata"}


class MBTilesValidationError(ValueError):
    """Raised when a file fails MBTiles validation."""


def validate(path: Path) -> bool:
    """Return True if *path* is a valid MBTiles SQLite database.

    Checks:
    1. Magic bytes confirm SQLite format.
    2. The database contains the required ``tiles`` and ``metadata`` tables.
    3. Optionally, GDAL can open the dataset (non-fatal if GDAL MBTiles driver
       is unavailable — SQLite checks are sufficient for validation).

    Args:
        path: Path to the candidate file.

    Returns:
        True if the file is a valid MBTiles database, False otherwise.
    """
    settings.apply_gdal_env()

    if not path.exists() or not path.is_file():
        logger.debug("MBTiles validate: path does not exist or is not a file: %s", path)
        return False

    # Fast magic-byte check (SQLite header)
    if not is_mbtiles(path):
        logger.debug("MBTiles validate: magic bytes mismatch for %s", path)
        return False

    # Confirm required tables exist
    try:
        conn = sqlite3.connect(str(path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0].lower() for row in cursor.fetchall()}
        conn.close()

        missing = _REQUIRED_TABLES - tables
        if missing:
            logger.debug(
                "MBTiles validate: missing required tables %s in %s", missing, path
            )
            return False
        return True
    except sqlite3.Error as exc:
        logger.warning("MBTiles validate: SQLite error for %s: %s", path, exc)
        return False


def extract_metadata(path: Path) -> Dict[str, Any]:
    """Extract metadata from an MBTiles file.

    Reads the ``metadata`` table for bounds, zoom levels, and tile format.
    Falls back to GDAL if the metadata table is incomplete.

    Args:
        path: Path to a valid MBTiles file.

    Returns:
        Dictionary with keys:
            - ``crs``          (str)  : Always "EPSG:3857" (Web Mercator, MBTiles spec).
            - ``bounds``       (dict) : {"min_lon", "min_lat", "max_lon", "max_lat"} in EPSG:4326.
            - ``resolution``   (float): Approximate pixel size at max zoom (metres/pixel).
            - ``resolution_x`` (float): Same as ``resolution``.
            - ``resolution_y`` (float): Same as ``resolution``.
            - ``width``        (int)  : Tile width in pixels (always 256 per MBTiles spec).
            - ``height``       (int)  : Tile height in pixels (always 256 per MBTiles spec).
            - ``min_zoom``     (int)  : Minimum zoom level.
            - ``max_zoom``     (int)  : Maximum zoom level.
            - ``tile_format``  (str)  : Tile image format ("png", "jpg", "webp", etc.).
            - ``name``         (str)  : Dataset name from metadata table.
            - ``description``  (str)  : Dataset description from metadata table.
            - ``driver``       (str)  : Always "MBTiles".
            - ``file_path``    (str)  : Absolute path to the file.

    Raises:
        MBTilesValidationError: If the file cannot be opened or metadata extraction fails.
    """
    settings.apply_gdal_env()

    try:
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row

        # Read all key-value pairs from the metadata table
        cursor = conn.execute("SELECT name, value FROM metadata")
        meta: Dict[str, str] = {row["name"]: row["value"] for row in cursor.fetchall()}

        # --- Bounds ---
        bounds_4326 = _parse_bounds(meta.get("bounds", ""))

        # --- Zoom levels ---
        min_zoom = int(meta.get("minzoom", 0))
        max_zoom = int(meta.get("maxzoom", 0))

        # --- Tile format ---
        tile_format = meta.get("format", "png").lower()

        # --- Name / description ---
        name = meta.get("name", path.stem)
        description = meta.get("description", "")

        conn.close()

        # --- Resolution: approximate metres/pixel at max zoom --- Web Mercator circumference ≈ 40_075_016.686 m; tile is 256 px wide
        resolution = _zoom_to_resolution(max_zoom)

        return {
            "crs": "EPSG:3857",
            "bounds": bounds_4326,
            "resolution": resolution,
            "resolution_x": resolution,
            "resolution_y": resolution,
            "width": 256,
            "height": 256,
            "min_zoom": min_zoom,
            "max_zoom": max_zoom,
            "tile_format": tile_format,
            "name": name,
            "description": description,
            "driver": "MBTiles",
            "file_path": str(path.resolve()),
        }

    except MBTilesValidationError:
        raise
    except Exception as exc:
        logger.error(
            "MBTiles extract_metadata: error for %s: %s",
            path,
            exc,
            exc_info=True,
        )
        raise MBTilesValidationError(
            f"Failed to extract metadata from MBTiles '{path}': {exc}"
        ) from exc


# --------------------------------------------------------------------------- Internal helpers ---------------------------------------------------------------------------


def _parse_bounds(bounds_str: str) -> Dict[str, float]:
    """Parse an MBTiles bounds string "min_lon,min_lat,max_lon,max_lat".

    Falls back to world bounds if the string is missing or malformed.
    """
    try:
        parts = [float(v.strip()) for v in bounds_str.split(",")]
        if len(parts) == 4:
            min_lon, min_lat, max_lon, max_lat = parts
            return {
                "min_lon": min_lon,
                "min_lat": min_lat,
                "max_lon": max_lon,
                "max_lat": max_lat,
            }
    except (ValueError, AttributeError) as exc:
        logger.warning(
            "MBTiles: could not parse bounds string %r (%s); using world bounds",
            bounds_str,
            exc,
        )
    # Default: full Web Mercator extent in WGS 84
    return {
        "min_lon": -180.0,
        "min_lat": -85.051129,
        "max_lon": 180.0,
        "max_lat": 85.051129,
    }


def _zoom_to_resolution(zoom: int) -> float:
    """Return approximate ground resolution in metres/pixel at *zoom* level.

    Formula: 40_075_016.686 / (256 * 2^zoom)
    """
    if zoom < 0:
        zoom = 0
    return 40_075_016.686 / (256 * (2 ** zoom))


__all__ = ["MBTilesValidationError", "validate", "extract_metadata"]
