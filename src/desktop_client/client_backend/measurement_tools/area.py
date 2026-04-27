"""Polygon area measurement with ellipsoidal and surface area calculations.

This module provides accurate area and perimeter measurements using GeographicLib,
matching QGIS QgsDistanceArea implementation. Optionally computes 3D surface area
when a DEM is provided.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
from pyproj import Geod

try:
    from shapely.geometry import Polygon
    from pyproj import Transformer
    import rasterio
    from rasterio.features import rasterize
except ImportError:
    rasterio = None
    rasterize = None
    Transformer = None
    Polygon = None

from desktop_client.client_backend.measurement_tools.models import (
    PolygonAreaMeasurement,
)
from desktop_client.client_backend.measurement_tools.dem_utils import (
    horn_gradient,
    read_dem_window,
)


def measure_polygon_area(
    lon_lat_points: list[tuple[float, float]],
    dem_path: Optional[str] = None,
) -> PolygonAreaMeasurement:
    """Compute exact ellipsoidal area and perimeter of a polygon.
    
    Uses GeographicLib / PROJ underneath, identical to QGIS QgsDistanceArea::measurePolygon.
    Also computes surface area and void fraction if a DEM is provided.
    
    Args:
        lon_lat_points: List of (longitude, latitude) tuples defining the polygon.
        dem_path: Optional path to DEM file for surface area calculation.
        
    Returns:
        PolygonAreaMeasurement containing planimetric area, perimeter, compactness,
        and optionally surface area and void fraction.
        
    Raises:
        ValueError: If fewer than 3 vertices are provided.

    """
    if len(lon_lat_points) < 3:
        raise ValueError("At least 3 vertices are required")

    # Ensure polygon is closed for exact area
    if lon_lat_points[0] != lon_lat_points[-1]:
        lon_lat_points = lon_lat_points + [lon_lat_points[0]]

    # Exact ellipsoidal area via GeographicLib (matches QGIS geod_polygon_compute)
    lons = [p[0] for p in lon_lat_points]
    lats = [p[1] for p in lon_lat_points]

    geod = Geod(ellps="WGS84")
    # geometry_area_perimeter returns (area, perimeter)
    planimetric_area, perimeter = geod.polygon_area_perimeter(lons, lats)
    planimetric_area = abs(
        planimetric_area
    )  # Area can be negative depending on winding order

    compactness = (
        (4.0 * math.pi * planimetric_area) / (perimeter * perimeter)
        if perimeter > 0
        else 0.0
    )

    surface_area = None
    void_fraction = None

    if dem_path and rasterio is not None and Polygon is not None:
        with rasterio.open(dem_path) as src:
            to_dem = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
            poly_dem = Polygon(
                [to_dem.transform(lon, lat) for lon, lat in lon_lat_points]
            )
            poly_dem = poly_dem if poly_dem.is_valid else poly_dem.buffer(0)

        dem, transform, res = read_dem_window(dem_path, poly_dem.bounds)
        mask_arr = rasterize(
            [poly_dem.__geo_interface__],
            out_shape=dem.shape,
            transform=transform,
            fill=0,
            default_value=1,
            dtype=np.uint8,
            all_touched=False,
        )
        inside = mask_arr == 1
        total_inside = int(np.sum(inside))
        nan_inside = int(np.sum(np.isnan(dem) & inside))
        void_fraction = (nan_inside / total_inside) if total_inside > 0 else 0.0

        dz_dx, dz_dy = horn_gradient(dem, res)
        slope = np.arctan(np.sqrt(dz_dx * dz_dx + dz_dy * dz_dy))
        cos_slope = np.clip(np.cos(slope), 1e-6, 1.0)
        pixel_surface = (res * res) / cos_slope
        valid = inside & ~np.isnan(dem)
        surface_area = float(np.sum(pixel_surface[valid]))

    return PolygonAreaMeasurement(
        planimetric_area_m2=float(planimetric_area),
        perimeter_m=float(perimeter),
        compactness_index=float(compactness),
        surface_area_m2=surface_area,
        void_fraction=void_fraction,
    )
