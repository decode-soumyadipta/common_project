from pathlib import Path

from offline_gis_app.server_ingestion.services.file_kind import detect_raster_kind
from offline_gis_app.server_ingestion.services.metadata_models import RasterMetadata
from offline_gis_app.utils.crs import normalize_crs
from offline_gis_app.utils.geometry import Bounds


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
    """Build internal overviews when absent to improve TiTiler performance.

    This is a best-effort optimization and should never block ingest.
    """
    try:
        import rasterio  # type: ignore
        from rasterio.enums import Resampling  # type: ignore
    except ImportError:
        return False

    try:
        with rasterio.open(path, "r+") as ds:
            if ds.count < 1:
                return False
            if ds.overviews(1):
                return False
            min_dim = min(int(ds.width), int(ds.height))
            factors: list[int] = []
            factor = 2
            while min_dim // factor >= 256:
                factors.append(factor)
                factor *= 2
            if not factors:
                return False
            ds.build_overviews(factors, Resampling.average)
            ds.update_tags(ns="rio_overview", resampling="average")
            return True
    except Exception:
        return False


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
    transformed_bounds = Bounds(min_x=float(left), min_y=float(bottom), max_x=float(right), max_y=float(top))
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
        bounds = _bounds_to_epsg4326(dataset)
        x_res, y_res = dataset.res
        crs_text = normalize_crs(dataset.crs.to_string() if dataset.crs else None)
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
