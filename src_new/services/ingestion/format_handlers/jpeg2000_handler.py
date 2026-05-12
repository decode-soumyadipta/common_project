"""JPEG2000 format handler.

Provides ``validate`` and ``extract_metadata`` for JPEG2000 files
(.jp2 / .j2k / .j2c codestreams).

Format detection logic adapted from:
- ``src/platform_core/ingestion/services/file_kind.py``
- ``src/platform_core/ingestion/services/file_grouping_service.py``

Requirement 9.3: Format-specific parsers for GeoTIFF, JPEG2000, and MBTiles.
Requirement 9.4: All GDAL operations use environment variables from Configuration_Manager.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from src_new.shared.config import settings
from src_new.shared.utils.file_validation import is_jpeg2000

logger = logging.getLogger(__name__)

# GDAL driver names that indicate a JPEG2000 dataset
_JP2_DRIVERS = {"JP2OpenJPEG", "JP2ECW", "JP2KAK", "JP2MrSID", "JPEG2000", "JP2Lura"}


class JPEG2000ValidationError(ValueError):
    """Raised when a file fails JPEG2000 validation."""


def validate(path: Path) -> bool:
    """Return True if *path* is a valid JPEG2000 file that GDAL can open.

    Checks:
    1. Magic bytes confirm JP2 container or raw J2K codestream.
    2. GDAL can open the dataset using a JPEG2000-family driver.

    Args:
        path: Path to the candidate file.

    Returns:
        True if the file is a valid JPEG2000, False otherwise.
    """
    settings.apply_gdal_env()

    if not path.exists() or not path.is_file():
        logger.debug("JPEG2000 validate: path does not exist or is not a file: %s", path)
        return False

    # Fast magic-byte check first
    if not is_jpeg2000(path):
        logger.debug("JPEG2000 validate: magic bytes mismatch for %s", path)
        return False

    # Confirm GDAL can open the dataset with a JP2 driver
    try:
        from osgeo import gdal

        gdal.UseExceptions()
        ds = gdal.Open(str(path), gdal.GA_ReadOnly)
        if ds is None:
            logger.debug("JPEG2000 validate: GDAL returned None for %s", path)
            return False
        driver_name = ds.GetDriver().ShortName if ds.GetDriver() else ""
        ds = None  # Close dataset
        valid = driver_name in _JP2_DRIVERS
        if not valid:
            logger.debug(
                "JPEG2000 validate: unexpected GDAL driver '%s' for %s",
                driver_name,
                path,
            )
        return valid
    except Exception as exc:
        logger.warning("JPEG2000 validate: GDAL error for %s: %s", path, exc)
        return False


def extract_metadata(path: Path) -> Dict[str, Any]:
    """Extract raster metadata from a JPEG2000 file using GDAL.

    Args:
        path: Path to a valid JPEG2000 file.

    Returns:
        Dictionary with keys:
            - ``crs``          (str)  : Authority string, e.g. "EPSG:32644".
            - ``bounds``       (dict) : {"min_lon", "min_lat", "max_lon", "max_lat"} in EPSG:4326.
            - ``resolution``   (float): Pixel size in native CRS units (x-direction).
            - ``resolution_x`` (float): Pixel width in native CRS units.
            - ``resolution_y`` (float): Pixel height in native CRS units (positive).
            - ``width``        (int)  : Raster width in pixels.
            - ``height``       (int)  : Raster height in pixels.
            - ``band_count``   (int)  : Number of raster bands.
            - ``driver``       (str)  : GDAL driver short name.
            - ``file_path``    (str)  : Absolute path to the file.

    Raises:
        JPEG2000ValidationError: If GDAL cannot open the file or metadata extraction fails.
    """
    settings.apply_gdal_env()

    try:
        from osgeo import gdal, osr

        gdal.UseExceptions()
        ds = gdal.Open(str(path), gdal.GA_ReadOnly)
        if ds is None:
            raise JPEG2000ValidationError(f"GDAL could not open file: {path}")

        width: int = ds.RasterXSize
        height: int = ds.RasterYSize
        band_count: int = ds.RasterCount
        driver: str = ds.GetDriver().ShortName if ds.GetDriver() else "JPEG2000"

        # --- CRS ---
        wkt = ds.GetProjection()
        crs_str = _wkt_to_authority(wkt) if wkt else "EPSG:4326"

        # --- Geotransform → bounds in native CRS ---
        gt = ds.GetGeoTransform()
        origin_x: float = gt[0]
        pixel_width: float = gt[1]
        pixel_height: float = abs(gt[5])  # Always positive
        origin_y: float = gt[3]

        native_min_x = origin_x
        native_max_x = origin_x + pixel_width * width
        native_max_y = origin_y
        native_min_y = origin_y + gt[5] * height  # gt[5] is negative for north-up

        ds = None  # Close dataset

        # --- Reproject bounds to EPSG:4326 ---
        bounds_4326 = _reproject_bounds_to_4326(
            native_min_x, native_min_y, native_max_x, native_max_y, wkt
        )

        return {
            "crs": crs_str,
            "bounds": bounds_4326,
            "resolution": pixel_width,
            "resolution_x": pixel_width,
            "resolution_y": pixel_height,
            "width": width,
            "height": height,
            "band_count": band_count,
            "driver": driver,
            "file_path": str(path.resolve()),
        }

    except JPEG2000ValidationError:
        raise
    except Exception as exc:
        logger.error(
            "JPEG2000 extract_metadata: GDAL error for %s: %s",
            path,
            exc,
            exc_info=True,
        )
        raise JPEG2000ValidationError(
            f"Failed to extract metadata from JPEG2000 '{path}': {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _wkt_to_authority(wkt: str) -> str:
    """Convert a WKT CRS string to an authority string like 'EPSG:32644'.

    Falls back to the raw WKT if no authority code is found.
    """
    try:
        from osgeo import osr

        srs = osr.SpatialReference()
        srs.ImportFromWkt(wkt)
        srs.AutoIdentifyEPSG()
        code = srs.GetAuthorityCode(None)
        name = srs.GetAuthorityName(None)
        if code and name:
            return f"{name}:{code}"
    except Exception:
        pass
    return wkt or "UNKNOWN"


def _reproject_bounds_to_4326(
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
    src_wkt: Optional[str],
) -> Dict[str, float]:
    """Reproject bounding box corners from *src_wkt* CRS to EPSG:4326.

    Returns a dict with keys min_lon, min_lat, max_lon, max_lat.
    Falls back to the native coordinates if reprojection fails.
    """
    try:
        from osgeo import osr

        if not src_wkt:
            raise ValueError("No source WKT provided")

        src_srs = osr.SpatialReference()
        src_srs.ImportFromWkt(src_wkt)

        dst_srs = osr.SpatialReference()
        dst_srs.ImportFromEPSG(4326)
        dst_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

        transform = osr.CoordinateTransformation(src_srs, dst_srs)

        corners = [
            transform.TransformPoint(min_x, min_y),
            transform.TransformPoint(max_x, min_y),
            transform.TransformPoint(max_x, max_y),
            transform.TransformPoint(min_x, max_y),
        ]
        lons = [c[0] for c in corners]
        lats = [c[1] for c in corners]
        return {
            "min_lon": min(lons),
            "min_lat": min(lats),
            "max_lon": max(lons),
            "max_lat": max(lats),
        }
    except Exception as exc:
        logger.warning(
            "JPEG2000: could not reproject bounds to EPSG:4326 (%s); "
            "returning native coordinates",
            exc,
        )
        return {
            "min_lon": min_x,
            "min_lat": min_y,
            "max_lon": max_x,
            "max_lat": max_y,
        }


__all__ = ["JPEG2000ValidationError", "validate", "extract_metadata"]
