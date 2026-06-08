"""Data models for measurement tool results.

This module defines dataclasses for various measurement types including:
- Distance measurements (2D and 3D)
- Polygon area measurements
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DistanceMeasurement:
    """Result of a distance measurement between two points.

    Attributes:
        distance_m: 2D ellipsoidal distance in meters.
        azimuth_fwd_deg: Forward azimuth in degrees (0° = North).
        azimuth_back_deg: Back azimuth in degrees.
        dz_m: Elevation difference in meters (None if no DEM).
        distance_3d_m: 3D distance in meters (None if no DEM).

    """

    distance_m: float
    azimuth_fwd_deg: float
    azimuth_back_deg: float
    dz_m: float | None
    distance_3d_m: float | None


@dataclass
class PolygonAreaMeasurement:
    """Result of a polygon area measurement.

    Attributes:
        planimetric_area_m2: 2D ellipsoidal area in square meters.
        perimeter_m: Perimeter length in meters.
        compactness_index: Shape compactness (4π*area/perimeter²), 1.0 = circle.
        surface_area_m2: 3D surface area in square meters (None if no DEM).
        void_fraction: Fraction of area with no data (None if no DEM).

    """

    planimetric_area_m2: float
    perimeter_m: float
    compactness_index: float
    surface_area_m2: float | None
    void_fraction: float | None
