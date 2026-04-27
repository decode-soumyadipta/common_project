"""Distance measurement with ellipsoidal and 3D calculations.

This module provides accurate distance measurements using GeographicLib,
matching QGIS QgsDistanceArea implementation. Optionally computes 3D distance
when a DEM is provided.
"""
from __future__ import annotations

import math
from typing import Optional

from pyproj import Geod

from desktop_client.client_backend.measurement_tools.models import DistanceMeasurement
from desktop_client.client_backend.measurement_tools.dem_utils import sample_dem_height


def vincenty_distance(
    lon1: float, lat1: float, lon2: float, lat2: float
) -> tuple[float, float, float]:
    """Compute exact ellipsoidal distance and azimuths between two points.
    
    Uses GeographicLib / PROJ underneath, identical to QGIS QgsDistanceArea::measureLine.

    Args:
        lon1: Longitude of first point in degrees.
        lat1: Latitude of first point in degrees.
        lon2: Longitude of second point in degrees.
        lat2: Latitude of second point in degrees.

    Returns:
        Tuple of (distance_m, azimuth_fwd_deg, azimuth_back_deg).

    """
    geod = Geod(ellps="WGS84")
    az_fwd, az_back, dist = geod.inv(lon1, lat1, lon2, lat2)
    return float(dist), float(az_fwd % 360.0), float(az_back % 360.0)


def measure_distance(
    lon1: float,
    lat1: float,
    lon2: float,
    lat2: float,
    dem_path: Optional[str] = None,
) -> DistanceMeasurement:
    """Measure the 2D ellipsoidal distance and optionally the 3D distance.
    
    Args:
        lon1: Longitude of first point in degrees.
        lat1: Latitude of first point in degrees.
        lon2: Longitude of second point in degrees.
        lat2: Latitude of second point in degrees.
        dem_path: Optional path to DEM file for 3D distance calculation.
        
    Returns:
        DistanceMeasurement containing 2D distance, azimuths, and optionally
        elevation difference and 3D distance.

    """
    dist, az_fwd, az_back = vincenty_distance(lon1, lat1, lon2, lat2)

    dz = None
    dist_3d = None
    if dem_path:
        z1 = sample_dem_height(dem_path, lon1, lat1)
        z2 = sample_dem_height(dem_path, lon2, lat2)
        if not (math.isnan(z1) or math.isnan(z2)):
            dz = z2 - z1
            dist_3d = math.sqrt(dist * dist + dz * dz)

    return DistanceMeasurement(
        distance_m=dist,
        azimuth_fwd_deg=az_fwd,
        azimuth_back_deg=az_back,
        dz_m=dz,
        distance_3d_m=dist_3d,
    )
