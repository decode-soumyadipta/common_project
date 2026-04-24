"""Slope and aspect analysis for terrain characterization.

This module provides slope statistics computation using Horn's algorithm,
matching GDAL's implementation for consistency with QGIS.
"""
from __future__ import annotations

import numpy as np

try:
    import rasterio
    from rasterio.features import rasterize
    from pyproj import Transformer
    from shapely.geometry import Polygon
except ImportError:
    rasterio = None
    rasterize = None
    Transformer = None
    Polygon = None

from offline_gis_app.client_backend.measurement_tools.models import (
    SlopeAspectMeasurement,
)
from offline_gis_app.client_backend.measurement_tools.dem_utils import (
    horn_gradient,
    read_dem_window,
)


def compute_slope_aspect(
    lon_lat_points: list[tuple[float, float]],
    dem_path: str,
) -> SlopeAspectMeasurement:
    """Compute slope statistics inside a polygon using Horn's algorithm.
    
    Args:
        lon_lat_points: List of (longitude, latitude) tuples defining the polygon.
        dem_path: Path to the DEM raster file.
        
    Returns:
        SlopeAspectMeasurement containing slope statistics and area by class.
        
    Raises:
        RuntimeError: If rasterio is not available.
        ValueError: If fewer than 3 vertices are provided.

    """
    if rasterio is None:
        raise RuntimeError("rasterio is not available")
    if len(lon_lat_points) < 3:
        raise ValueError("At least 3 polygon vertices are required")

    with rasterio.open(dem_path) as src:
        to_dem = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        poly_dem = Polygon([to_dem.transform(lon, lat) for lon, lat in lon_lat_points])
        poly_dem = poly_dem if poly_dem.is_valid else poly_dem.buffer(0)

    dem, transform, res = read_dem_window(dem_path, poly_dem.bounds)
    mask = rasterize(
        [poly_dem.__geo_interface__],
        out_shape=dem.shape,
        transform=transform,
        fill=0,
        default_value=1,
        dtype=np.uint8,
        all_touched=False,
    )
    inside = (mask == 1) & ~np.isnan(dem)

    dz_dx, dz_dy = horn_gradient(dem, res)
    slope_deg = np.degrees(np.arctan(np.sqrt(dz_dx * dz_dx + dz_dy * dz_dy)))
    slope_in = slope_deg[inside]
    pixel_area = res * res

    classes = {
        "0-5": slope_in < 5,
        "5-15": (slope_in >= 5) & (slope_in < 15),
        "15-30": (slope_in >= 15) & (slope_in < 30),
        "30-45": (slope_in >= 30) & (slope_in < 45),
        ">45": slope_in >= 45,
    }
    area_by_class = {k: float(np.sum(v) * pixel_area) for k, v in classes.items()}

    return SlopeAspectMeasurement(
        mean_slope_deg=float(np.nanmean(slope_in)) if slope_in.size else 0.0,
        std_slope_deg=float(np.nanstd(slope_in)) if slope_in.size else 0.0,
        max_slope_deg=float(np.nanmax(slope_in)) if slope_in.size else 0.0,
        area_by_class_m2=area_by_class,
    )
