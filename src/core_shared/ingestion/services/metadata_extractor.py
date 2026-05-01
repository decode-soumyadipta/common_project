from pathlib import Path

from core_shared.ingestion.services.file_kind import detect_raster_kind
from core_shared.ingestion.services.metadata_models import RasterMetadata
from core_shared.ingestion.services.pyramiding_service import (
    RasterPyramidingService,
)
from core_shared.utils.crs import normalize_crs
from core_shared.utils.geometry import Bounds


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


def extract_metadata(path: Path) -> RasterMetadata:
    if not path.exists():
        raise FileNotFoundError(f"Raster path does not exist: {path}")

    with _read_with_rasterio(path) as dataset:
        # Extract CRS information
        crs_text = normalize_crs(dataset.crs.to_string() if dataset.crs else None)
        
        # Log geospatial information extraction
        import logging
        logger = logging.getLogger("services.metadata")
        logger.info(f"=" * 80)
        logger.info(f"GEOSPATIAL METADATA EXTRACTION: {path.name}")
        logger.info(f"=" * 80)
        
        # Check for auxiliary files
        prj_file = path.with_suffix('.prj')
        world_files = [
            path.with_suffix('.j2w'),  # JPEG2000 world file
            path.with_suffix('.tfw'),  # TIFF world file
            path.with_suffix('.jgw'),  # JPEG world file
        ]
        
        if prj_file.exists():
            logger.info(f"✓ Found .prj file: {prj_file.name}")
            try:
                prj_content = prj_file.read_text()[:200]  # First 200 chars
                logger.info(f"  Projection: {prj_content.split('[')[1].split(',')[0] if '[' in prj_content else 'Unknown'}")
            except Exception:
                pass
        else:
            logger.info(f"✗ No .prj file found")
        
        for wf in world_files:
            if wf.exists():
                logger.info(f"✓ Found world file: {wf.name}")
                try:
                    wf_lines = wf.read_text().strip().split('\n')
                    if len(wf_lines) >= 6:
                        pixel_x = float(wf_lines[0])
                        pixel_y = float(wf_lines[3])
                        origin_x = float(wf_lines[4])
                        origin_y = float(wf_lines[5])
                        logger.info(f"  Pixel size: {abs(pixel_x):.2f} × {abs(pixel_y):.2f} units")
                        logger.info(f"  Origin: ({origin_x:.2f}, {origin_y:.2f})")
                except Exception:
                    pass
                break
        
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
        logger.info(f"  Data type: {dataset.dtypes[0] if dataset.count > 0 else 'Unknown'}")
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
        km_per_deg_lon = 111.32 * abs(float(dataset.res[0])) * 0.001 if dataset.res else 111.32
        km_per_deg_lat = 110.57
        area_km2 = (width_deg * km_per_deg_lon) * (height_deg * km_per_deg_lat)
        logger.info(f"  Coverage: ~{area_km2:.2f} km²")
        logger.info(f"")
        
        # Accuracy warnings
        if crs_text is None or crs_text == "":
            logger.warning(f"⚠ WARNING: No CRS defined! Assuming EPSG:4326")
        
        if abs(bounds.min_y) > 60 or abs(bounds.max_y) > 60:
            logger.warning(f"⚠ WARNING: High latitude data (>{60}°) - EPSG:3857 will have significant distortion")
        
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
