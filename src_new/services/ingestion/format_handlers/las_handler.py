"""LAS/LAZ point-cloud format handler.

Validates LAS/LAZ files and extracts geographic metadata so they can be
cataloged and visualised like raster layers.

Metadata extraction strategy
-----------------------------
1. ``laspy`` is used (when available) for fast header-level parsing that avoids
   reading the full point record.  Only the header bounding box, point count and
   CRS are accessed, which is O(1) for any file size.
2. If ``laspy`` is not installed a pure-Python fallback parses the first 375
   bytes of the LAS 1.x header according to the ASPRS LAS specification.

The returned metadata dictionary uses the same schema as the raster handlers so
the ingestion pipeline can treat LAS assets uniformly.

Requirement: point-cloud (LAS/LAZ) support for upload and cataloging.
"""
from __future__ import annotations

import logging
import struct
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# LAS file signature bytes (first 4 bytes of every valid LAS file)
_LAS_SIGNATURE = b"LASF"

# Minimal LAS 1.x header size in bytes (spec: 227 bytes for 1.0–1.3, 375 for 1.4)
_LAS_MIN_HEADER_BYTES = 227


class LASValidationError(ValueError):
    """Raised when a file fails LAS validation."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate(path: Path) -> bool:
    """Return True if *path* is a valid LAS/LAZ file.

    Checks:
    1. Magic bytes ``LASF`` at byte offset 0.
    2. File size is at least 227 bytes (minimum LAS 1.0 header).
    3. Optionally, ``laspy`` can open the header without error.

    Args:
        path: Path to the candidate file.

    Returns:
        True if the file appears to be a valid LAS/LAZ file.
    """
    if not path.exists() or not path.is_file():
        logger.debug("LAS validate: path does not exist or is not a file: %s", path)
        return False

    # Fast magic-byte check
    try:
        with path.open("rb") as fh:
            magic = fh.read(4)
    except OSError as exc:
        logger.debug("LAS validate: cannot read magic bytes for %s: %s", path, exc)
        return False

    if magic != _LAS_SIGNATURE:
        logger.debug("LAS validate: bad magic bytes for %s (got %r)", path, magic)
        return False

    if path.stat().st_size < _LAS_MIN_HEADER_BYTES:
        logger.debug("LAS validate: file too small to be a valid LAS: %s", path)
        return False

    # Try laspy for a deeper check (non-fatal if unavailable)
    try:
        import laspy  # noqa: PLC0415

        with laspy.open(str(path)) as las_reader:
            _hdr = las_reader.header  # header-only read
        return True
    except ImportError:
        # laspy not installed – magic-byte check is sufficient
        return True
    except Exception as exc:
        logger.warning("LAS validate: laspy header read failed for %s: %s", path, exc)
        return False


def extract_metadata(path: Path) -> dict[str, Any]:
    """Extract point-cloud metadata from a LAS/LAZ file.

    The returned dict follows the same schema as the raster handlers:
        - ``crs``        (str)   : Authority string, e.g. ``"EPSG:4326"``.
        - ``bounds``     (dict)  : ``{min_lon, min_lat, max_lon, max_lat}`` in WGS-84.
        - ``resolution`` (float) : Always 0.0 for point clouds (no pixel size concept).
        - ``width``      (int)   : Total point count (used in place of pixel width).
        - ``height``     (int)   : Always 1 for point clouds.
        - ``band_count`` (int)   : Always 1.
        - ``driver``     (str)   : ``"LAS"`` or ``"LAZ"``.
        - ``file_path``  (str)   : Absolute path to the file.
        - ``point_count`` (int)  : Number of points in the file.

    Args:
        path: Path to a valid LAS/LAZ file.

    Returns:
        Metadata dictionary.

    Raises:
        LASValidationError: If the file cannot be read or parsed.
    """
    try:
        import laspy  # noqa: PLC0415
        return _extract_with_laspy(path)
    except ImportError:
        logger.debug("laspy not available; using fallback LAS header parser for %s", path)
        return _extract_fallback(path)
    except LASValidationError:
        raise
    except Exception as exc:
        logger.error("LAS extract_metadata: error for %s: %s", path, exc, exc_info=True)
        raise LASValidationError(
            f"Failed to extract metadata from LAS file '{path}': {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_with_laspy(path: Path) -> dict[str, Any]:
    """Extract metadata using laspy (preferred path)."""
    import laspy  # noqa: PLC0415

    with laspy.open(str(path)) as las_reader:
        header = las_reader.header

    # --- Bounding box ---
    # laspy exposes header.offsets, header.mins and header.maxs (in native CRS units)
    try:
        min_x = float(header.mins[0])
        min_y = float(header.mins[1])
        max_x = float(header.maxs[0])
        max_y = float(header.maxs[1])
    except (AttributeError, IndexError, TypeError):
        # Older laspy API
        min_x = float(header.x_min)
        min_y = float(header.y_min)
        max_x = float(header.x_max)
        max_y = float(header.y_max)

    # --- Point count ---
    try:
        point_count = int(header.point_count)
    except AttributeError:
        try:
            point_count = int(header.legacy_point_count)
        except AttributeError:
            point_count = 0

    # --- CRS ---
    crs_str = _extract_crs_from_header(header)

    # --- Reproject bounds to EPSG:4326 if needed ---
    bounds_4326 = _reproject_bounds_to_4326(min_x, min_y, max_x, max_y, crs_str)

    driver = "LAZ" if path.suffix.lower() == ".laz" else "LAS"

    return {
        "crs": crs_str,
        "bounds": bounds_4326,
        "resolution": 0.0,
        "resolution_x": 0.0,
        "resolution_y": 0.0,
        "width": point_count,
        "height": 1,
        "band_count": 1,
        "driver": driver,
        "file_path": str(path.resolve()),
        "point_count": point_count,
    }


def _extract_fallback(path: Path) -> dict[str, Any]:
    """Pure-Python fallback: parse LAS 1.x header without laspy.

    LAS 1.0–1.3 header layout (fixed part, 227 bytes):
      Offset  Size  Field
       0       4    File Signature ("LASF")
       4       2    File Source ID
       6       2    Global Encoding
       8       4    Project ID-1
      12       4    Project ID-2
      16       2    Project ID-3
      18       8    Project ID-4
      26       1    Version Major
      27       1    Version Minor
      28      32    System Identifier
      60      32    Generating Software
      92       2    File Creation Day of Year
      94       2    File Creation Year
      96       2    Header Size
      98       4    Offset to Point Data
     102       4    Number of Variable Length Records
     106       1    Point Data Format ID
     107       2    Point Data Record Length
     109       4    Legacy Number of Point Records
     113      20    Legacy Number of Points by Return (5 × 4)
     133       8    X Scale Factor
     141       8    Y Scale Factor
     149       8    Z Scale Factor
     157       8    X Offset
     165       8    Y Offset
     173       8    Z Offset
     181       8    Max X
     189       8    Min X
     197       8    Max Y
     205       8    Min Y
     213       8    Max Z
     221       8    Min Z
    """
    try:
        with path.open("rb") as fh:
            raw = fh.read(229)  # 227 bytes + 2 spare

        if len(raw) < _LAS_MIN_HEADER_BYTES:
            raise LASValidationError(f"LAS file too small: {path}")

        point_count = struct.unpack_from("<I", raw, 109)[0]
        max_x = struct.unpack_from("<d", raw, 181)[0]
        min_x = struct.unpack_from("<d", raw, 189)[0]
        max_y = struct.unpack_from("<d", raw, 197)[0]
        min_y = struct.unpack_from("<d", raw, 205)[0]

        # Assume WGS-84 geographic coords if the range looks degree-like
        crs_str = "EPSG:4326"
        if abs(max_x) > 180 or abs(max_y) > 90:
            # Likely a projected CRS – keep raw bounds and note unknown CRS
            crs_str = "UNKNOWN"

        bounds_4326: dict[str, float]
        if crs_str == "EPSG:4326":
            bounds_4326 = {
                "min_lon": min_x,
                "min_lat": min_y,
                "max_lon": max_x,
                "max_lat": max_y,
            }
        else:
            bounds_4326 = {
                "min_lon": min_x,
                "min_lat": min_y,
                "max_lon": max_x,
                "max_lat": max_y,
            }

        driver = "LAZ" if path.suffix.lower() == ".laz" else "LAS"

        return {
            "crs": crs_str,
            "bounds": bounds_4326,
            "resolution": 0.0,
            "resolution_x": 0.0,
            "resolution_y": 0.0,
            "width": point_count,
            "height": 1,
            "band_count": 1,
            "driver": driver,
            "file_path": str(path.resolve()),
            "point_count": point_count,
        }
    except LASValidationError:
        raise
    except Exception as exc:
        raise LASValidationError(
            f"Fallback LAS header parse failed for '{path}': {exc}"
        ) from exc


def _extract_crs_from_header(header: Any) -> str:
    """Try to extract a CRS string from a laspy header object."""
    # laspy ≥ 2.0: header.parse_crs() returns a pyproj.CRS
    try:
        if hasattr(header, "parse_crs"):
            crs_obj = header.parse_crs()
            if crs_obj is not None:
                auth = crs_obj.to_authority()
                if auth:
                    return f"{auth[0]}:{auth[1]}"
                return crs_obj.to_wkt()
    except Exception:
        pass

    # Try legacy .vlrs attribute (WKT1 stored in VLR record_id=2112)
    try:
        for vlr in getattr(header, "vlrs", []):
            if getattr(vlr, "record_id", None) == 2112:
                raw_wkt = vlr.parsed_body
                if raw_wkt and isinstance(raw_wkt, (str, bytes)):
                    wkt_str = raw_wkt if isinstance(raw_wkt, str) else raw_wkt.decode("utf-8", errors="ignore")
                    return _wkt_to_authority(wkt_str)
    except Exception:
        pass

    return "EPSG:4326"


def _wkt_to_authority(wkt: str) -> str:
    """Convert WKT CRS to an authority string like 'EPSG:4326'."""
    try:
        from osgeo import osr  # noqa: PLC0415

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
    min_x: float, min_y: float, max_x: float, max_y: float, crs_str: str
) -> dict[str, float]:
    """Reproject bounding box to EPSG:4326.  Falls back to native if anything fails."""
    if crs_str in {"EPSG:4326", "WGS84", "WGS 84"}:
        return {"min_lon": min_x, "min_lat": min_y, "max_lon": max_x, "max_lat": max_y}

    try:
        from osgeo import osr  # noqa: PLC0415

        src_srs = osr.SpatialReference()
        if crs_str.upper().startswith("EPSG:"):
            src_srs.ImportFromEPSG(int(crs_str.split(":")[1]))
        else:
            src_srs.ImportFromWkt(crs_str)

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
            "LAS: could not reproject bounds to EPSG:4326 (%s); returning native coords", exc
        )
        return {"min_lon": min_x, "min_lat": min_y, "max_lon": max_x, "max_lat": max_y}


__all__ = ["LASValidationError", "extract_metadata", "validate"]
