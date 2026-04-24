"""Data models for measurement tool results.

This module defines dataclasses for various measurement types including:
- Distance measurements (2D and 3D)
- Polygon area measurements
- Slope and aspect analysis
- Volume calculations
- Viewshed analysis
- Shadow height estimation
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


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
    dz_m: Optional[float]
    distance_3d_m: Optional[float]


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
    surface_area_m2: Optional[float]
    void_fraction: Optional[float]


@dataclass
class SlopeAspectMeasurement:
    """Result of slope and aspect analysis.
    
    Attributes:
        mean_slope_deg: Mean slope in degrees.
        std_slope_deg: Standard deviation of slope in degrees.
        max_slope_deg: Maximum slope in degrees.
        area_by_class_m2: Dictionary mapping slope class names to areas in m².

    """

    mean_slope_deg: float
    std_slope_deg: float
    max_slope_deg: float
    area_by_class_m2: dict[str, float]


@dataclass
class VolumeMeasurement:
    """Result of volume cut/fill calculation.
    
    Attributes:
        cut_volume_m3: Volume of material to cut in cubic meters.
        fill_volume_m3: Volume of material to fill in cubic meters.
        net_volume_m3: Net volume (cut - fill) in cubic meters.
        reference_elevation_m: Reference elevation used for calculation.
        void_fraction: Fraction of area with no data.

    """

    cut_volume_m3: float
    fill_volume_m3: float
    net_volume_m3: float
    reference_elevation_m: float
    void_fraction: float


@dataclass
class ViewshedMeasurement:
    """Result of viewshed analysis.
    
    Attributes:
        visible_area_m2: Area visible from observer point in square meters.
        total_area_m2: Total analysis area in square meters.
        visible_fraction: Fraction of area that is visible (0.0 to 1.0).
        max_visible_distance_m: Maximum visible distance in meters.

    """

    visible_area_m2: float
    total_area_m2: float
    visible_fraction: float
    max_visible_distance_m: float


@dataclass
class ShadowHeightMeasurement:
    """Result of shadow-based height estimation.
    
    Attributes:
        estimated_height_m: Estimated object height in meters.
        corrected_height_m: Height corrected for terrain slope (None if unavailable).
        solar_elevation_deg: Solar elevation angle in degrees.
        solar_azimuth_deg: Solar azimuth angle in degrees.
        uncertainty_m: Estimated uncertainty in meters.
        reliable: Whether the measurement is considered reliable.
        warning: Optional warning message about measurement quality.

    """

    estimated_height_m: float
    corrected_height_m: Optional[float]
    solar_elevation_deg: float
    solar_azimuth_deg: float
    uncertainty_m: float
    reliable: bool
    warning: Optional[str]
