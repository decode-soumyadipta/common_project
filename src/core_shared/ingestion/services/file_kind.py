from pathlib import Path

from core_shared.db.models import RasterKind


def detect_raster_kind(path: Path) -> RasterKind:
    suffix = path.suffix.lower()
    if "dem" in path.stem.lower():
        return RasterKind.DEM
    if suffix in {".tif", ".tiff"}:
        return RasterKind.GEOTIFF
    if suffix in {".jp2", ".j2k"}:
        return RasterKind.JPEG2000
    if suffix == ".mbtiles":
        return RasterKind.MBTILES
    return RasterKind.UNKNOWN
