"""Volume calculation for cut/fill analysis.

This module provides volume computation for polygons relative to a reference
elevation (typically the mean elevation within the polygon).
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

from offline_gis_app.client_backend.measurement_tools.models import VolumeMeasurement
from offline_gis_app.client_backend.measurement_tools.dem_utils import read_dem_window


def compute_volume(
    lon_lat_points: list[tuple[float, float]],
    dem_path: str,
) -> VolumeMeasurement:
    """Compute cut/fill volume inside a polygon relative to mean elevation.
    
    Args:
        lon_lat_points: List of (longitude, latitude) tuples defining the polygon.
        dem_path: Path to the DEM raster file.
        
    Returns:
        VolumeMeasurement containing cut, fill, and net volumes.
        
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

    inside = mask == 1
    valid = inside & ~np.isnan(dem)
    z_vals = dem[valid]

    total_inside = int(np.sum(inside))
    void_inside = int(np.sum(np.isnan(dem) & inside))
    void_fraction = (void_inside / total_inside) if total_inside > 0 else 0.0

    ref = float(np.nanmean(z_vals)) if z_vals.size else 0.0
    dz = z_vals - ref
    px_area = res * res

    cut = float(np.sum(dz[dz > 0]) * px_area)
    fill = float(np.sum(-dz[dz < 0]) * px_area)

    return VolumeMeasurement(
        cut_volume_m3=cut,
        fill_volume_m3=fill,
        net_volume_m3=cut - fill,
        reference_elevation_m=ref,
        void_fraction=void_fraction,
    )
