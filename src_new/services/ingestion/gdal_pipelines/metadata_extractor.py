"""GDAL-based raster metadata extractor.

Adapted from ``src/platform_core/ingestion/services/metadata_extractor.py``.

Extracts CRS, geographic bounds (EPSG:4326), pixel resolution, and band
information from GeoTIFF, JPEG2000, and MBTiles raster files using
Rasterio (primary) with a GDAL fallback.

GDAL environment variables (GDAL_DISABLE_READDIR_ON_OPEN,
GDAL_HTTP_MERGE_CONSECUTIVE_RANGES) are applied via
``settings.apply_gdal_env()`` before any GDAL/Rasterio call.

Requirements: 9.1, 9.2, 9.4
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from src_new.shared.config import settings
from src_new.shared.models.bounding_box import BoundingBox
from src_new.shared.models.raster_metadata import RasterKind, RasterMetadata
from src_new.shared.utils.coordinate_conversion import normalize_crs
from src_new.shared.utils.file_validation import Bounds

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- Public exception ---------------------------------------------------------------------------


class MetadataExtractorError(RuntimeError):
    """Raised when metadata extraction fails for a raster file."""


# --------------------------------------------------------------------------- Internal helpers — raster kind detection ---------------------------------------------------------------------------


def _detect_raster_kind(path: Path) -> RasterKind:
    """Detect the raster kind from file extension and GDAL band count.

    Mirrors the logic in ``src/platform_core/ingestion/services/file_kind.py``
    but returns ``src_new.shared.models.RasterKind`` values.
    """
    import re

    suffix = path.suffix.lower()
    stem_lower = path.stem.lower()

    def _name_suggests_dem(p: Path) -> bool:
        name = f"{p.stem} {p.parent.name}".lower()
        normalized = re.sub(r"[^a-z0-9]+", " ", name)
        return (
            re.search(
                r"(^| )(dem|dtm|dsm|elev|elevation|terrain|height)( |$)",
                normalized,
            )
            is not None
        )

    name_suggests_dem = _name_suggests_dem(path)

    if suffix == ".mbtiles":
        return RasterKind.MBTILES
    if suffix in {".jp2", ".j2k"}:
        return RasterKind.DEM if name_suggests_dem else RasterKind.JPEG2000

    if suffix in {".tif", ".tiff"}:
        try:
            from osgeo import gdal  # type: ignore[import]

            gdal.UseExceptions()
            ds = gdal.Open(str(path))
            if ds:
                if ds.RasterCount == 1 or name_suggests_dem:
                    return RasterKind.DEM
                return RasterKind.GEOTIFF
        except Exception:
            pass

    if name_suggests_dem or "dem" in stem_lower or "dtm" in stem_lower:
        return RasterKind.DEM

    if suffix in {".tif", ".tiff"}:
        return RasterKind.GEOTIFF

    return RasterKind.UNKNOWN


# --------------------------------------------------------------------------- Internal helpers — dataset I/O ---------------------------------------------------------------------------


def _read_with_rasterio(path: Path):
    """Open *path* with Rasterio and return the dataset context manager."""
    try:
        import rasterio  # type: ignore[import]
    except ImportError as exc:
        raise MetadataExtractorError(
            "rasterio is required for metadata extraction. Install geo extras."
        ) from exc
    return rasterio.open(path)


def _read_with_gdal(path: Path):
    """Open *path* with GDAL and return the dataset object."""
    try:
        from osgeo import gdal  # type: ignore[import]
    except Exception as exc:
        raise MetadataExtractorError(
            "GDAL is required for metadata extraction when rasterio is unavailable."
        ) from exc

    gdal.UseExceptions()
    dataset = gdal.Open(str(path))
    if dataset is None:
        raise MetadataExtractorError(f"GDAL could not open raster: {path}")
    return dataset


# --------------------------------------------------------------------------- Internal helpers — auxiliary CRS files ---------------------------------------------------------------------------


def _read_auxiliary_crs_and_log(path: Path, log: logging.Logger) -> str | None:
    """Check for sidecar .prj and world files; return external CRS WKT if found."""
    stems = [path.stem]
    if path.stem.lower().endswith(".cog"):
        stems.append(path.stem[:-4])

    prj_files = []
    world_files = []
    for stem in stems:
        parent = path.parent
        prj_files.append(parent / f"{stem}.prj")
        for ext in [".j2w", ".tfw", ".jgw", ".wld"]:
            world_files.append(parent / f"{stem}{ext}")

    external_crs: str | None = None
    for prj_file in prj_files:
        if prj_file.exists():
            log.info("✓ Found .prj file: %s", prj_file.name)
            try:
                prj_content = prj_file.read_text().strip()
                if prj_content:
                    external_crs = prj_content
                    log.info(
                        "  Projection from .prj: %s",
                        prj_content.split("[")[1].split(",")[0]
                        if "[" in prj_content
                        else "Found",
                    )
                    break
            except Exception:
                pass
    else:
        log.info("✗ No .prj file found")

    for wf in world_files:
        if wf.exists():
            log.info("✓ Found world file: %s", wf.name)
            try:
                wf_lines = wf.read_text().strip().split("\n")
                if len(wf_lines) >= 6:
                    pixel_x = float(wf_lines[0])
                    pixel_y = float(wf_lines[3])
                    origin_x = float(wf_lines[4])
                    origin_y = float(wf_lines[5])
                    log.info(
                        "  Pixel size: %.2f × %.2f units",
                        abs(pixel_x),
                        abs(pixel_y),
                    )
                    log.info("  Origin: (%.2f, %.2f)", origin_x, origin_y)
            except Exception:
                pass
            break

    return external_crs


# --------------------------------------------------------------------------- Internal helpers — bounds validation and transformation ---------------------------------------------------------------------------


def _is_valid_epsg4326_bounds(bounds: Bounds) -> bool:
    """Return True when *bounds* are plausible lon/lat coordinates in EPSG:4326."""
    return (
        -180.0 <= bounds.min_x <= 180.0
        and -180.0 <= bounds.max_x <= 180.0
        and -90.0 <= bounds.min_y <= 90.0
        and -90.0 <= bounds.max_y <= 90.0
        and bounds.min_x < bounds.max_x
        and bounds.min_y < bounds.max_y
    )


def _bounds_to_epsg4326(dataset, external_crs: str | None = None) -> Bounds:
    """Transform a Rasterio dataset's bounds to EPSG:4326.

    If the dataset does not carry an internal CRS, a sibling sidecar CRS such
    as .prj can be supplied via *external_crs* and will be used instead.
    """
    try:
        from rasterio.crs import CRS  # type: ignore[import]
        from rasterio.warp import transform_bounds  # type: ignore[import]
    except ImportError as exc:
        raise MetadataExtractorError(
            "rasterio.warp is required for CRS bounds transformation."
        ) from exc

    source_crs = dataset.crs
    if source_crs is None and external_crs:
        try:
            source_crs = CRS.from_user_input(external_crs)
        except Exception as exc:
            raise MetadataExtractorError(
                f"Invalid external CRS supplied for bounds transformation: {external_crs}"
            ) from exc

    if source_crs is None:
        raw_bounds = Bounds(
            min_x=float(dataset.bounds.left),
            min_y=float(dataset.bounds.bottom),
            max_x=float(dataset.bounds.right),
            max_y=float(dataset.bounds.top),
        )
        if not _is_valid_epsg4326_bounds(raw_bounds):
            raise MetadataExtractorError(
                "Raster CRS is missing and bounds are not valid EPSG:4326 lon/lat. "
                "Define a CRS before ingest."
            )
        return raw_bounds

    left, bottom, right, top = transform_bounds(
        source_crs,
        "EPSG:4326",
        dataset.bounds.left,
        dataset.bounds.bottom,
        dataset.bounds.right,
        dataset.bounds.top,
        densify_pts=21,
    )
    transformed_bounds = Bounds(
        min_x=float(left),
        min_y=float(bottom),
        max_x=float(right),
        max_y=float(top),
    )
    if not _is_valid_epsg4326_bounds(transformed_bounds):
        raise MetadataExtractorError(
            "Transformed bounds are invalid for EPSG:4326. "
            f"Verify source CRS metadata: {dataset.crs}."
        )
    return transformed_bounds


def _gdal_crs_text(dataset, external_crs: str | None) -> str:
    """Extract a normalized CRS string from a GDAL dataset."""
    try:
        from osgeo import osr  # type: ignore[import]
    except Exception:
        return normalize_crs(external_crs)

    wkt = dataset.GetProjection() or ""
    source_srs = osr.SpatialReference()
    has_srs = False

    if wkt:
        try:
            has_srs = source_srs.ImportFromWkt(wkt) == 0
        except Exception:
            has_srs = False

    if not has_srs and external_crs:
        try:
            has_srs = source_srs.SetFromUserInput(external_crs) == 0
        except Exception:
            has_srs = False

    if has_srs:
        auth = source_srs.GetAuthorityName(None)
        code = source_srs.GetAuthorityCode(None)
        if auth and code:
            return normalize_crs(f"{auth}:{code}")
        if wkt:
            return normalize_crs(wkt)

    if external_crs:
        return normalize_crs(external_crs)
    return ""


def _bounds_to_epsg4326_gdal(dataset, external_crs: str | None) -> Bounds:
    """Transform a GDAL dataset's corner coordinates to EPSG:4326."""
    try:
        from osgeo import osr  # type: ignore[import]
    except Exception as exc:
        raise MetadataExtractorError(
            "osgeo.osr is required for CRS bounds transformation."
        ) from exc

    gt = dataset.GetGeoTransform()
    if gt is None:
        raise MetadataExtractorError("Raster geotransform is missing.")

    width = int(dataset.RasterXSize)
    height = int(dataset.RasterYSize)

    corners = [(0, 0), (width, 0), (0, height), (width, height)]
    xs = []
    ys = []
    for px, py in corners:
        x = gt[0] + (px * gt[1]) + (py * gt[2])
        y = gt[3] + (px * gt[4]) + (py * gt[5])
        xs.append(float(x))
        ys.append(float(y))

    raw_bounds = Bounds(
        min_x=min(xs),
        min_y=min(ys),
        max_x=max(xs),
        max_y=max(ys),
    )

    wkt = dataset.GetProjection() or ""
    source_srs = osr.SpatialReference()
    has_srs = False
    if wkt:
        try:
            has_srs = source_srs.ImportFromWkt(wkt) == 0
        except Exception:
            has_srs = False

    if not has_srs and external_crs:
        try:
            has_srs = source_srs.SetFromUserInput(external_crs) == 0
        except Exception:
            has_srs = False

    if not has_srs:
        if not _is_valid_epsg4326_bounds(raw_bounds):
            raise MetadataExtractorError(
                "Raster CRS is missing and bounds are not valid EPSG:4326 lon/lat. "
                "Define a CRS before ingest."
            )
        return raw_bounds

    target_srs = osr.SpatialReference()
    target_srs.ImportFromEPSG(4326)
    transform = osr.CoordinateTransformation(source_srs, target_srs)

    transformed = []
    for x, y in zip(xs, ys, strict=False):
        lon, lat, _ = transform.TransformPoint(x, y)
        transformed.append((float(lon), float(lat)))

    min_x = min(pt[0] for pt in transformed)
    max_x = max(pt[0] for pt in transformed)
    min_y = min(pt[1] for pt in transformed)
    max_y = max(pt[1] for pt in transformed)

    transformed_bounds = Bounds(
        min_x=min_x,
        min_y=min_y,
        max_x=max_x,
        max_y=max_y,
    )
    if not _is_valid_epsg4326_bounds(transformed_bounds):
        raise MetadataExtractorError(
            "Transformed bounds are invalid for EPSG:4326. "
            f"Verify source CRS metadata: {source_srs.ExportToWkt()}."
        )
    return transformed_bounds


# --------------------------------------------------------------------------- Internal helpers — model construction ---------------------------------------------------------------------------


def _bounds_to_bbox(bounds: Bounds) -> BoundingBox:
    """Convert an internal ``Bounds`` object to a shared ``BoundingBox`` model."""
    return BoundingBox(
        min_lon=bounds.min_x,
        min_lat=bounds.min_y,
        max_lon=bounds.max_x,
        max_lat=bounds.max_y,
    )


# --------------------------------------------------------------------------- GDAL-path extraction ---------------------------------------------------------------------------


def _extract_metadata_with_gdal(path: Path) -> RasterMetadata:
    """Extract metadata using the GDAL API (fallback when Rasterio is unavailable)."""
    # Apply GDAL env vars from config before any GDAL call (Requirement 9.4)
    settings.apply_gdal_env()

    dataset = _read_with_gdal(path)
    try:
        from osgeo import gdal  # type: ignore[import]

        log = logging.getLogger("services.metadata")
        log.info("=" * 80)
        log.info("GEOSPATIAL METADATA EXTRACTION (GDAL): %s", path.name)
        log.info("=" * 80)

        external_crs = _read_auxiliary_crs_and_log(path, log)
        crs_text = _gdal_crs_text(dataset, external_crs)
        bounds = _bounds_to_epsg4326_gdal(dataset, external_crs)

        gt = dataset.GetGeoTransform()
        x_res = float(gt[1]) if gt else 0.0
        y_res = float(gt[5]) if gt else 0.0

        band_count = int(dataset.RasterCount)
        data_type = (
            gdal.GetDataTypeName(dataset.GetRasterBand(1).DataType)
            if band_count > 0
            else "Unknown"
        )

        log.info("")
        log.info("EXTRACTED METADATA:")
        log.info("  Source CRS: %s", crs_text)
        log.info(
            "  Dimensions: %d × %d pixels",
            dataset.RasterXSize,
            dataset.RasterYSize,
        )
        log.info(
            "  Resolution: %.6f × %.6f units/pixel",
            abs(x_res),
            abs(y_res),
        )
        log.info("  Bands: %d", band_count)
        log.info("  Data type: %s", data_type)
        log.info("")
        log.info("BOUNDS (EPSG:4326 - WGS84 Lat/Lon):")
        log.info("  West:  %.8f°", bounds.min_x)
        log.info("  South: %.8f°", bounds.min_y)
        log.info("  East:  %.8f°", bounds.max_x)
        log.info("  North: %.8f°", bounds.max_y)

        if (crs_text is None or crs_text == "") and external_crs:
            log.info("Applying external CRS from .prj file")
            crs_text = normalize_crs(external_crs)

        if crs_text is None or crs_text == "":
            log.warning("⚠ WARNING: No CRS defined! Assuming EPSG:4326")
            crs_text = "EPSG:4326"

        if abs(bounds.min_y) > 60 or abs(bounds.max_y) > 60:
            log.warning(
                "⚠ WARNING: High latitude data (>60°) — EPSG:3857 will have significant distortion"
            )

        log.info("=" * 80)

        return RasterMetadata(
            raster_id=str(uuid.uuid4()),
            file_path=str(path.resolve()),
            file_name=path.name,
            kind=_detect_raster_kind(path),
            crs=crs_text,
            bbox=_bounds_to_bbox(bounds),
            resolution_x=float(abs(x_res)),
            resolution_y=float(abs(y_res)),
            width=int(dataset.RasterXSize),
            height=int(dataset.RasterYSize),
        )
    finally:
        dataset = None


# --------------------------------------------------------------------------- Overview / pyramid hook ---------------------------------------------------------------------------


def ensure_overviews(path: Path) -> bool:
    """Ensure raster overviews exist for efficient tile serving.

    Delegates to a pyramiding service when available; returns False if the
    service is not yet wired in this deployment.

    This is a backward-compatible hook preserved from the original
    ``metadata_extractor.ensure_overviews``.
    """
    try:
        # Attempt to import the pyramiding service if it has been migrated
        from src_new.services.ingestion.gdal_pipelines.pyramiding_service import (  # type: ignore[import]
            RasterPyramidingService,
        )

        return RasterPyramidingService().ensure(path)
    except ImportError:
        logger.debug(
            "RasterPyramidingService not available; skipping overview generation for %s",
            path.name,
        )
        return False


# --------------------------------------------------------------------------- Public API ---------------------------------------------------------------------------


def extract_metadata(path: Path) -> RasterMetadata:
    """Extract geospatial metadata from a raster file.

    Supports GeoTIFF (.tif/.tiff), JPEG2000 (.jp2/.j2k), and MBTiles.
    Uses Rasterio as the primary reader with a GDAL fallback.

    GDAL environment variables are applied from ``settings`` before any
    GDAL/Rasterio operation (Requirement 9.4).

    Args:
        path: Path to the raster file.

    Returns:
        A populated :class:`~src_new.shared.models.RasterMetadata` instance
        with CRS, bounding box (EPSG:4326), resolution, and dimensions.

    Raises:
        FileNotFoundError: If *path* does not exist.
        MetadataExtractorError: If metadata cannot be extracted.
    """
    import time
    start_time = time.time()
    
    # Apply GDAL env vars from config before any GDAL/Rasterio call (Requirement 9.4)
    settings.apply_gdal_env()

    # Resolve JPEG2000 path aliases
    if path.suffix.lower() == ".j2k":
        jp2_candidate = path.with_suffix(".jp2")
        if jp2_candidate.exists():
            path = jp2_candidate

    if path.suffix.lower() in {".jp2", ".j2k"}:
        cog_candidate = path.with_name(f"{path.stem}.cog.tif")
        if cog_candidate.exists():
            path = cog_candidate

    if not path.exists():
        raise FileNotFoundError(f"Raster path does not exist: {path}")

    try:
        with _read_with_rasterio(path) as dataset:
            log = logging.getLogger("services.metadata")
            log.info("=" * 80)
            log.info("GEOSPATIAL METADATA EXTRACTION: %s", path.name)
            log.info("=" * 80)
            
            # Log GDAL operation start (Requirement 18.6)
            logger.info(
                "GDAL operation: metadata extraction — file=%s",
                path.name,
                extra={
                    "event": "gdal_operation_start",
                    "operation": "metadata_extraction",
                    "file_path": str(path),
                }
            )

            # Extract CRS. If the source lacks an embedded CRS, prefer a matching sidecar .prj / world-file CRS instead of assuming WGS84.
            crs_text = normalize_crs(
                dataset.crs.to_string() if dataset.crs else None
            )

            external_crs = _read_auxiliary_crs_and_log(path, log)
            if dataset.crs is None and external_crs:
                crs_text = normalize_crs(external_crs)

            # Extract bounds and transform to EPSG:4326
            bounds = _bounds_to_epsg4326(dataset, external_crs)
            x_res, y_res = dataset.res

            # Log extracted metadata
            log.info("")
            log.info("EXTRACTED METADATA:")
            log.info("  Source CRS: %s", crs_text)
            log.info("  Dimensions: %d × %d pixels", dataset.width, dataset.height)
            log.info(
                "  Resolution: %.6f × %.6f units/pixel",
                abs(x_res),
                abs(y_res),
            )
            log.info("  Bands: %d", dataset.count)
            log.info(
                "  Data type: %s",
                dataset.dtypes[0] if dataset.count > 0 else "Unknown",
            )
            log.info("")
            log.info("BOUNDS (EPSG:4326 - WGS84 Lat/Lon):")
            log.info("  West:  %.8f°", bounds.min_x)
            log.info("  South: %.8f°", bounds.min_y)
            log.info("  East:  %.8f°", bounds.max_x)
            log.info("  North: %.8f°", bounds.max_y)

            # Approximate coverage area
            width_deg = bounds.max_x - bounds.min_x
            height_deg = bounds.max_y - bounds.min_y
            km_per_deg_lon = (
                111.32 * abs(float(dataset.res[0])) * 0.001
                if dataset.res
                else 111.32
            )
            km_per_deg_lat = 110.57
            area_km2 = (width_deg * km_per_deg_lon) * (height_deg * km_per_deg_lat)
            log.info("  Coverage: ~%.2f km²", area_km2)
            log.info("")

            if crs_text is None or crs_text == "":
                log.warning("⚠ WARNING: No CRS defined! Assuming EPSG:4326")
                crs_text = "EPSG:4326"

            if abs(bounds.min_y) > 60 or abs(bounds.max_y) > 60:
                log.warning(
                    "⚠ WARNING: High latitude data (>60°) — EPSG:3857 will have significant distortion"
                )

            log.info("=" * 80)
            
            # Calculate duration and log completion (Requirement 18.6)
            duration_ms = (time.time() - start_time) * 1000
            logger.info(
                "GDAL operation complete: metadata extraction — file=%s duration=%.2fms",
                path.name,
                duration_ms,
                extra={
                    "event": "gdal_operation_complete",
                    "operation": "metadata_extraction",
                    "file_path": str(path),
                    "duration_ms": round(duration_ms, 2),
                }
            )

            return RasterMetadata(
                raster_id=str(uuid.uuid4()),
                file_path=str(path.resolve()),
                file_name=path.name,
                kind=_detect_raster_kind(path),
                crs=crs_text,
                bbox=_bounds_to_bbox(bounds),
                resolution_x=float(abs(x_res)),
                resolution_y=float(abs(y_res)),
                width=int(dataset.width),
                height=int(dataset.height),
            )

    except MetadataExtractorError:
        # Log error (Requirement 18.6)
        duration_ms = (time.time() - start_time) * 1000
        logger.error(
            "GDAL operation failed: metadata extraction — file=%s duration=%.2fms",
            path.name,
            duration_ms,
            extra={
                "event": "gdal_operation_failed",
                "operation": "metadata_extraction",
                "file_path": str(path),
                "duration_ms": round(duration_ms, 2),
            }
        )
        raise
    except Exception as exc:
        # Try GDAL fallback before propagating
        try:
            return _extract_metadata_with_gdal(path)
        except Exception:
            pass

        # Log error (Requirement 18.6)
        duration_ms = (time.time() - start_time) * 1000
        logger.error(
            "GDAL operation failed: metadata extraction — file=%s duration=%.2fms error=%s",
            path.name,
            duration_ms,
            str(exc),
            extra={
                "event": "gdal_operation_failed",
                "operation": "metadata_extraction",
                "file_path": str(path),
                "duration_ms": round(duration_ms, 2),
                "error": str(exc),
            }
        )

        msg = str(exc)
        msg_lower = msg.lower()
        if any(
            token in msg_lower
            for token in (
                "opj_get_decoded_file",
                "stream too short",
                "openjpeg",
                "jp2openjpeg",
                "jpeg2000",
            )
        ):
            raise MetadataExtractorError(
                f"JPEG2000 decode failed for {path.name}. The file may be incomplete, "
                "corrupted, or your GDAL JPEG2000 driver is missing. "
                "Verify the file copy is complete and try the .jp2 variant if available."
            ) from exc
        if "not recognized as being a supported file format" in msg:
            if path.suffix.lower() in {".jp2", ".j2k"}:
                raise MetadataExtractorError(
                    f"GDAL cannot read {path.name}. Your environment is likely missing the "
                    "JPEG2000 plugin (OpenJPEG/ECW). "
                    "Fix: Convert this file to COG (Cloud Optimized GeoTIFF) using the "
                    "'prepare_data.py' script before moving to the offline system."
                ) from exc
            raise MetadataExtractorError(
                f"GDAL does not recognize the format of {path.name}. "
                "Ensure the file is not corrupted and is a supported geospatial format."
            ) from exc
        raise


__all__ = [
    "MetadataExtractorError",
    "extract_metadata",
    "ensure_overviews",
]
