from __future__ import annotations

import datetime as dt
import math
from typing import Optional

try:
    from pysolar.solar import get_altitude, get_azimuth
except ImportError:
    get_altitude = None
    get_azimuth = None

from desktop_client.client_backend.measurement_tools.models import (
    ShadowHeightMeasurement,
)
from desktop_client.client_backend.measurement_tools.dem_utils import sample_dem_height
from desktop_client.client_backend.measurement_tools.distance import vincenty_distance


def _solar_position_noaa(
    lat: float, lon: float, when_utc: dt.datetime
) -> tuple[float, float]:
    """Return (solar_elevation_deg, solar_azimuth_deg) using NOAA approximation if pysolar is absent."""
    if when_utc.tzinfo is None:
        when_utc = when_utc.replace(tzinfo=dt.timezone.utc)
    utc = when_utc.astimezone(dt.timezone.utc)
    day_of_year = utc.timetuple().tm_yday
    hour = utc.hour + (utc.minute / 60.0) + (utc.second / 3600.0)

    gamma = (2.0 * math.pi / 365.0) * (day_of_year - 1 + (hour - 12.0) / 24.0)
    eq_time = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2.0 * gamma)
        - 0.040849 * math.sin(2.0 * gamma)
    )
    decl = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2.0 * gamma)
        + 0.000907 * math.sin(2.0 * gamma)
        - 0.002697 * math.cos(3.0 * gamma)
        + 0.00148 * math.sin(3.0 * gamma)
    )

    true_solar_time = (hour * 60.0 + eq_time + 4.0 * lon) % 1440.0
    hour_angle = true_solar_time / 4.0 - 180.0
    if hour_angle < -180.0:
        hour_angle += 360.0

    ha_rad = math.radians(hour_angle)
    lat_rad = math.radians(lat)
    cos_zenith = math.sin(lat_rad) * math.sin(decl) + math.cos(lat_rad) * math.cos(
        decl
    ) * math.cos(ha_rad)
    cos_zenith = max(-1.0, min(1.0, cos_zenith))
    zenith = math.acos(cos_zenith)
    solar_elevation = 90.0 - math.degrees(zenith)

    sin_zenith = max(1e-8, math.sin(zenith))
    sin_az = -(math.sin(ha_rad) * math.cos(decl)) / sin_zenith
    cos_az = (math.sin(decl) - math.sin(lat_rad) * math.cos(zenith)) / (
        max(1e-8, math.cos(lat_rad)) * sin_zenith
    )
    solar_azimuth = (math.degrees(math.atan2(sin_az, cos_az)) + 360.0) % 360.0
    return float(solar_elevation), float(solar_azimuth)


def measure_shadow_height(
    base_lon: float,
    base_lat: float,
    tip_lon: float,
    tip_lat: float,
    acquisition_datetime_utc: dt.datetime,
    dem_path: Optional[str] = None,
    imagery_resolution_m: float = 0.05,
) -> ShadowHeightMeasurement:
    """Calculates object height based on shadow length and solar angle."""
    if get_altitude is not None and get_azimuth is not None:
        solar_az = float(get_azimuth(base_lat, base_lon, acquisition_datetime_utc))
        solar_el = float(get_altitude(base_lat, base_lon, acquisition_datetime_utc))
    else:
        solar_el, solar_az = _solar_position_noaa(
            base_lat, base_lon, acquisition_datetime_utc
        )

    warning = None
    reliable = True
    if solar_el < 10.0:
        reliable = False
        warning = "Low solar elevation (<10 deg): estimate is less reliable."

    shadow_len, shadow_az, _ = vincenty_distance(base_lon, base_lat, tip_lon, tip_lat)
    expected_az = (solar_az + 180.0) % 360.0
    angle_diff = abs(shadow_az - expected_az)
    if angle_diff > 180.0:
        angle_diff = 360.0 - angle_diff
    if angle_diff > 30.0:
        reliable = False
        warning = (
            f"Shadow direction differs from solar expectation by {angle_diff:.1f} deg."
        )

    if solar_el <= 0.1:
        return ShadowHeightMeasurement(
            estimated_height_m=0.0,
            corrected_height_m=None,
            solar_elevation_deg=solar_el,
            solar_azimuth_deg=solar_az,
            uncertainty_m=999.0,
            reliable=False,
            warning="Sun below horizon; cannot compute shadow height.",
        )

    h = shadow_len * math.tan(math.radians(solar_el))
    uncertainty = imagery_resolution_m / math.tan(math.radians(solar_el))

    corrected = None
    if dem_path:
        z_base = sample_dem_height(dem_path, base_lon, base_lat)
        z_tip = sample_dem_height(dem_path, tip_lon, tip_lat)
        if not (math.isnan(z_base) or math.isnan(z_tip)):
            corrected = h - (z_tip - z_base)

    return ShadowHeightMeasurement(
        estimated_height_m=float(h),
        corrected_height_m=None if corrected is None else float(corrected),
        solar_elevation_deg=solar_el,
        solar_azimuth_deg=solar_az,
        uncertainty_m=float(uncertainty),
        reliable=reliable,
        warning=warning,
    )
