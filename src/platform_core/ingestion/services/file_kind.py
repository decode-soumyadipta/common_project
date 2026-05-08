from pathlib import Path
import re

from platform_core.db.models import RasterKind


def _name_suggests_dem(path: Path) -> bool:
    name = f"{path.stem} {path.parent.name}".lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", name)
    return (
        re.search(
            r"(^| )(dem|dtm|dsm|elev|elevation|terrain|height)( |$)",
            normalized,
        )
        is not None
    )


def detect_raster_kind(path: Path) -> RasterKind:
    """
    Detect the kind of raster asset based on naming hints and file properties.
    Prioritizes file content (e.g. band count) over naming when possible.
    """
    suffix = path.suffix.lower()
    stem_lower = path.stem.lower()
    name_suggests_dem = _name_suggests_dem(path)

    # 1. MBTiles and JPEG2000 are distinct by suffix
    if suffix == ".mbtiles":
        return RasterKind.MBTILES
    if suffix in {".jp2", ".j2k"}:
        return RasterKind.DEM if name_suggests_dem else RasterKind.JPEG2000

    # 2. For TIFF files, use GDAL to distinguish between Imagery and Elevation (DEM/DTM)
    if suffix in {".tif", ".tiff"}:
        try:
            from osgeo import gdal
            gdal.UseExceptions()
            ds = gdal.Open(str(path))
            if ds:
                # Typically DEMs/DTMs are single-band (height data)
                # while Orthophotos/Imagery are 3-4 bands (RGB/RGBA)
                if ds.RasterCount == 1 or name_suggests_dem:
                    return RasterKind.DEM
                return RasterKind.GEOTIFF
        except Exception:
            # Fallback to naming if GDAL fails
            pass

    # 3. First level check/Confirmation: Naming hints
    if name_suggests_dem or "dem" in stem_lower or "dtm" in stem_lower:
        return RasterKind.DEM

    # 4. Fallback for TIFFs if GDAL was skipped or failed
    if suffix in {".tif", ".tiff"}:
        return RasterKind.GEOTIFF

    return RasterKind.UNKNOWN
