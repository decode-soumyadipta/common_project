from pathlib import Path

from platform_core.ingestion.services.file_kind import detect_raster_kind
from platform_core.ingestion.services.metadata_models import RasterMetadata
from platform_core.ingestion.services.pyramiding_service import (
    RasterPyramidingService,
)
from platform_core.utils.crs import normalize_crs
from platform_core.utils.geometry import Bounds


class MetadataExtractorError(RuntimeError):
    pass


def _read_with_rasterio(path: Path):
    try:
        import rasterio  # type: ignore
    except ImportError as exc:
        raise MetadataExtractorError(
            "rasterio is required for metadata extraction. Install geo extras."
        ) from exc
    return rasterio.open(path)


def _read_with_gdal(path: Path):
    try:
        from osgeo import gdal
    except Exception as exc:  # noqa: BLE001
        raise MetadataExtractorError(
            "GDAL is required for metadata extraction when rasterio is unavailable."
        ) from exc

    gdal.UseExceptions()
    dataset = gdal.Open(str(path))
    if dataset is None:
        raise MetadataExtractorError(f"GDAL could not open raster: {path}")
    return dataset


def _read_auxiliary_crs_and_log(path: Path, logger) -> str | None:
    prj_file = path.with_suffix(".prj")
    world_files = [
        path.with_suffix(".j2w"),
        path.with_suffix(".tfw"),
        path.with_suffix(".jgw"),
    ]

    external_crs = None
    if prj_file.exists():
        logger.info(f"✓ Found .prj file: {prj_file.name}")
        try:
            prj_content = prj_file.read_text().strip()
            if prj_content:
                external_crs = prj_content
                logger.info(
                    "  Projection from .prj: %s",
                    prj_content.split("[")[1].split(",")[0]
                    if "[" in prj_content
                    else "Found",
                )
        except Exception:
            pass
    else:
        logger.info("✗ No .prj file found")

    for wf in world_files:
        if wf.exists():
            logger.info(f"✓ Found world file: {wf.name}")
            try:
                wf_lines = wf.read_text().strip().split("\n")
                if len(wf_lines) >= 6:
                    pixel_x = float(wf_lines[0])
                    pixel_y = float(wf_lines[3])
                    origin_x = float(wf_lines[4])
                    origin_y = float(wf_lines[5])
                    logger.info(
                        "  Pixel size: %.2f × %.2f units",
                        abs(pixel_x),
                        abs(pixel_y),
                    )
                    logger.info("  Origin: (%.2f, %.2f)", origin_x, origin_y)
            except Exception:
                pass
            break

    return external_crs


def ensure_overviews(path: Path) -> bool:
    """Backward-compatible overview hook delegated to pyramiding service."""
    return RasterPyramidingService().ensure(path)


def _is_valid_epsg4326_bounds(bounds: Bounds) -> bool:
    """Return True when bounds are plausible lon/lat coordinates in EPSG:4326."""
    return (
        -180.0 <= bounds.min_x <= 180.0
        and -180.0 <= bounds.max_x <= 180.0
        and -90.0 <= bounds.min_y <= 90.0
        and -90.0 <= bounds.max_y <= 90.0
        and bounds.min_x < bounds.max_x
        and bounds.min_y < bounds.max_y
    )


def _bounds_to_epsg4326(dataset) -> Bounds:
    try:
        from rasterio.warp import transform_bounds  # type: ignore
    except ImportError as exc:
        raise MetadataExtractorError(
            "rasterio.warp is required for CRS bounds transformation."
        ) from exc

    if dataset.crs is None:
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
        dataset.crs,
        "EPSG:4326",
        dataset.bounds.left,
        dataset.bounds.bottom,
        dataset.bounds.right,
        dataset.bounds.top,
        densify_pts=21,
    )
    transformed_bounds = Bounds(
        min_x=float(left), min_y=float(bottom), max_x=float(right), max_y=float(top)
    )
    if not _is_valid_epsg4326_bounds(transformed_bounds):
        raise MetadataExtractorError(
            "Transformed bounds are invalid for EPSG:4326. "
            f"Verify source CRS metadata: {dataset.crs}."
        )
    return transformed_bounds


def _gdal_crs_text(dataset, external_crs: str | None) -> str:
    try:
        from osgeo import osr
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
    try:
        from osgeo import osr
    except Exception as exc:  # noqa: BLE001
        raise MetadataExtractorError(
            "osgeo.osr is required for CRS bounds transformation."
        ) from exc

    gt = dataset.GetGeoTransform()
    if gt is None:
        raise MetadataExtractorError("Raster geotransform is missing.")

    width = int(dataset.RasterXSize)
    height = int(dataset.RasterYSize)

    corners = [
        (0, 0),
        (width, 0),
        (0, height),
        (width, height),
    ]

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


def _extract_metadata_with_gdal(path: Path) -> RasterMetadata:
    dataset = _read_with_gdal(path)
    try:
        import logging
        from osgeo import gdal

        logger = logging.getLogger("services.metadata")
        logger.info("=" * 80)
        logger.info(f"GEOSPATIAL METADATA EXTRACTION (GDAL): {path.name}")
        logger.info("=" * 80)

        external_crs = _read_auxiliary_crs_and_log(path, logger)
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

        logger.info("")
        logger.info("EXTRACTED METADATA:")
        logger.info(f"  Source CRS: {crs_text}")
        logger.info(f"  Dimensions: {dataset.RasterXSize} × {dataset.RasterYSize} pixels")
        logger.info(
            "  Resolution: %.6f × %.6f units/pixel",
            abs(x_res),
            abs(y_res),
        )
        logger.info(f"  Bands: {band_count}")
        logger.info(f"  Data type: {data_type}")
        logger.info("")
        logger.info("BOUNDS (EPSG:4326 - WGS84 Lat/Lon):")
        logger.info(f"  West:  {bounds.min_x:.8f}°")
        logger.info(f"  South: {bounds.min_y:.8f}°")
        logger.info(f"  East:  {bounds.max_x:.8f}°")
        logger.info(f"  North: {bounds.max_y:.8f}°")

        if (crs_text is None or crs_text == "") and external_crs:
            logger.info("Applying external CRS from .prj file")
            crs_text = normalize_crs(external_crs)

        if crs_text is None or crs_text == "":
            logger.warning("⚠ WARNING: No CRS defined! Assuming EPSG:4326")
            crs_text = "EPSG:4326"

        if abs(bounds.min_y) > 60 or abs(bounds.max_y) > 60:
            logger.warning(
                "⚠ WARNING: High latitude data (>60°) - EPSG:3857 will have significant distortion"
            )

        logger.info("=" * 80)

        return RasterMetadata(
            file_path=path.resolve(),
            file_name=path.name,
            kind=detect_raster_kind(path),
            crs=crs_text,
            bounds=bounds,
            resolution_x=float(abs(x_res)),
            resolution_y=float(abs(y_res)),
            width=int(dataset.RasterXSize),
            height=int(dataset.RasterYSize),
        )
    finally:
        dataset = None


def extract_metadata(path: Path) -> RasterMetadata:
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
            # Extract CRS information
            crs_text = normalize_crs(dataset.crs.to_string() if dataset.crs else None)

            # Log geospatial information extraction
            import logging

            logger = logging.getLogger("services.metadata")
            logger.info(f"=" * 80)
            logger.info(f"GEOSPATIAL METADATA EXTRACTION: {path.name}")
            logger.info(f"=" * 80)

            external_crs = _read_auxiliary_crs_and_log(path, logger)

            # Extract bounds and transform to EPSG:4326
            bounds = _bounds_to_epsg4326(dataset)
            x_res, y_res = dataset.res

            # Log extracted metadata
            logger.info(f"")
            logger.info(f"EXTRACTED METADATA:")
            logger.info(f"  Source CRS: {crs_text}")
            logger.info(f"  Dimensions: {dataset.width} × {dataset.height} pixels")
            logger.info(f"  Resolution: {abs(x_res):.6f} × {abs(y_res):.6f} units/pixel")
            logger.info(f"  Bands: {dataset.count}")
            logger.info(
                f"  Data type: {dataset.dtypes[0] if dataset.count > 0 else 'Unknown'}"
            )
            logger.info(f"")
            logger.info(f"BOUNDS (EPSG:4326 - WGS84 Lat/Lon):")
            logger.info(f"  West:  {bounds.min_x:.8f}°")
            logger.info(f"  South: {bounds.min_y:.8f}°")
            logger.info(f"  East:  {bounds.max_x:.8f}°")
            logger.info(f"  North: {bounds.max_y:.8f}°")

            # Calculate coverage area (approximate)
            width_deg = bounds.max_x - bounds.min_x
            height_deg = bounds.max_y - bounds.min_y
            # Approximate area in km² (rough calculation)
            lat_center = (bounds.min_y + bounds.max_y) / 2
            km_per_deg_lon = (
                111.32 * abs(float(dataset.res[0])) * 0.001 if dataset.res else 111.32
            )
            km_per_deg_lat = 110.57
            area_km2 = (width_deg * km_per_deg_lon) * (height_deg * km_per_deg_lat)
            logger.info(f"  Coverage: ~{area_km2:.2f} km²")
            logger.info(f"")

            # Finalize CRS: Prefer .prj if internal CRS is missing or generic
            if (crs_text is None or crs_text == "") and external_crs:
                logger.info(f"Applying external CRS from .prj file")
                crs_text = normalize_crs(external_crs)

            # Accuracy warnings
            if crs_text is None or crs_text == "":
                logger.warning(f"⚠ WARNING: No CRS defined! Assuming EPSG:4326")
                crs_text = "EPSG:4326"

            if abs(bounds.min_y) > 60 or abs(bounds.max_y) > 60:
                logger.warning(
                    f"⚠ WARNING: High latitude data (>{60}°) - EPSG:3857 will have significant distortion"
                )

            logger.info(f"=" * 80)

            return RasterMetadata(
                file_path=path.resolve(),
                file_name=path.name,
                kind=detect_raster_kind(path),
                crs=crs_text,
                bounds=bounds,
                resolution_x=float(x_res),
                resolution_y=float(y_res),
                width=int(dataset.width),
                height=int(dataset.height),
            )
    except Exception as exc:
        try:
            return _extract_metadata_with_gdal(path)
        except Exception:
            pass
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
                    f"GDAL cannot read {path.name}. Your environment is likely missing the JPEG2000 plugin (OpenJPEG/ECW). "
                    "Fix: Convert this file to COG (Cloud Optimized GeoTIFF) using the 'prepare_data.py' script before moving to the offline system."
                ) from exc
            raise MetadataExtractorError(
                f"GDAL does not recognize the format of {path.name}. Ensure the file is not corrupted and is a supported geospatial format."
            ) from exc
        raise
