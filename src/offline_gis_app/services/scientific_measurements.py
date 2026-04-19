from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
from numpy.typing import NDArray
from pyproj import Geod, Transformer
from rasterio.features import rasterize
from rasterio.transform import rowcol
from rasterio.windows import Window, from_bounds
from shapely.geometry import Polygon

try:
    import rasterio
    from rasterio.enums import Resampling
except Exception:  # pragma: no cover - optional runtime dependency
    rasterio = None
    Resampling = None

try:
    from pysolar.solar import get_altitude, get_azimuth
except Exception:  # pragma: no cover - optional runtime dependency
    get_altitude = None
    get_azimuth = None


GEOD_WGS84 = Geod(ellps="WGS84")
EARTH_RADIUS_M = 6_371_000.0


@dataclass
class DistanceMeasurement:
    distance_m: float
    azimuth_fwd_deg: float
    azimuth_back_deg: float
    dz_m: Optional[float]
    distance_3d_m: Optional[float]


@dataclass
class PolygonAreaMeasurement:
    planimetric_area_m2: float
    perimeter_m: float
    compactness_index: float
    surface_area_m2: Optional[float]
    void_fraction: Optional[float]


@dataclass
class SlopeAspectMeasurement:
    mean_slope_deg: float
    std_slope_deg: float
    max_slope_deg: float
    area_by_class_m2: dict[str, float]


@dataclass
class VolumeMeasurement:
    cut_volume_m3: float
    fill_volume_m3: float
    net_volume_m3: float
    reference_elevation_m: float
    void_fraction: float


@dataclass
class ViewshedMeasurement:
    visible_area_m2: float
    total_area_m2: float
    visible_fraction: float
    max_visible_distance_m: float


@dataclass
class ShadowHeightMeasurement:
    estimated_height_m: float
    corrected_height_m: Optional[float]
    solar_elevation_deg: float
    solar_azimuth_deg: float
    uncertainty_m: float
    reliable: bool
    warning: Optional[str]


def vincenty_distance(lon1: float, lat1: float, lon2: float, lat2: float) -> tuple[float, float, float]:
    az_fwd, az_back, dist = GEOD_WGS84.inv(lon1, lat1, lon2, lat2)
    return float(dist), float(az_fwd % 360.0), float(az_back % 360.0)


def _utm_epsg_for_lon_lat(lon: float, lat: float) -> int:
    zone = int((lon + 180.0) // 6.0) + 1
    return 32600 + zone if lat >= 0 else 32700 + zone


def _to_projected_polygon(lon_lat_points: list[tuple[float, float]], epsg: int) -> Polygon:
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    projected = [transformer.transform(lon, lat) for lon, lat in lon_lat_points]
    poly = Polygon(projected)
    return poly if poly.is_valid else poly.buffer(0)


def _read_dem_window(
    dem_path: str,
    bounds: tuple[float, float, float, float],
) -> tuple[NDArray[np.float64], object, float]:
    if rasterio is None:
        raise RuntimeError("rasterio is not available")
    with rasterio.open(dem_path) as src:
        win = from_bounds(*bounds, transform=src.transform)
        data = src.read(1, window=win, resampling=Resampling.bilinear).astype(np.float64)
        nodata = src.nodata
        if nodata is not None:
            data = np.where(data == nodata, np.nan, data)
        transform = src.window_transform(win)
        res = float(src.res[0])
    return data, transform, res


def _horn_gradient(dem: NDArray[np.float64], res: float) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    nan_mask = np.isnan(dem)
    fill = np.where(nan_mask, np.nanmean(dem), dem)

    kx = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float64) / (8.0 * res)
    ky = np.array([[1, 2, 1], [0, 0, 0], [-1, -2, -1]], dtype=np.float64) / (8.0 * res)

    dz_dx = _convolve3x3_nearest(fill, kx)
    dz_dy = _convolve3x3_nearest(fill, ky)
    dz_dx[nan_mask] = np.nan
    dz_dy[nan_mask] = np.nan
    return dz_dx, dz_dy


def _convolve3x3_nearest(arr: NDArray[np.float64], kernel: NDArray[np.float64]) -> NDArray[np.float64]:
    """Vectorized 3x3 convolution with nearest-edge padding, SciPy-free."""
    padded = np.pad(arr, pad_width=1, mode="edge")
    out = np.zeros_like(arr, dtype=np.float64)
    for r in range(3):
        for c in range(3):
            out += kernel[r, c] * padded[r : r + arr.shape[0], c : c + arr.shape[1]]
    return out


def _sample_dem_height(dem_path: str, lon: float, lat: float) -> float:
    if rasterio is None:
        return float("nan")
    with rasterio.open(dem_path) as src:
        transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        x, y = transformer.transform(lon, lat)
        r, c = rowcol(src.transform, x, y)
        win = Window(int(c) - 1, int(r) - 1, 3, 3)
        try:
            data = src.read(1, window=win).astype(np.float64)
            nodata = src.nodata
            if nodata is not None:
                data = np.where(data == nodata, np.nan, data)
            return float(data[1, 1])
        except Exception:
            return float("nan")


def measure_distance(
    lon1: float,
    lat1: float,
    lon2: float,
    lat2: float,
    dem_path: Optional[str] = None,
) -> DistanceMeasurement:
    dist, az_fwd, az_back = vincenty_distance(lon1, lat1, lon2, lat2)
    dz = None
    dist_3d = None
    if dem_path:
        z1 = _sample_dem_height(dem_path, lon1, lat1)
        z2 = _sample_dem_height(dem_path, lon2, lat2)
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


def measure_polygon_area(
    lon_lat_points: list[tuple[float, float]],
    dem_path: Optional[str] = None,
) -> PolygonAreaMeasurement:
    if len(lon_lat_points) < 3:
        raise ValueError("At least 3 vertices are required")
    if lon_lat_points[0] != lon_lat_points[-1]:
        lon_lat_points = lon_lat_points + [lon_lat_points[0]]

    lon_c = float(np.mean([p[0] for p in lon_lat_points]))
    lat_c = float(np.mean([p[1] for p in lon_lat_points]))
    utm_epsg = _utm_epsg_for_lon_lat(lon_c, lat_c)
    poly = _to_projected_polygon(lon_lat_points, utm_epsg)

    perimeter = 0.0
    coords = list(poly.exterior.coords)
    back_transform = Transformer.from_crs(f"EPSG:{utm_epsg}", "EPSG:4326", always_xy=True)
    for i in range(len(coords) - 1):
        lon1, lat1 = back_transform.transform(coords[i][0], coords[i][1])
        lon2, lat2 = back_transform.transform(coords[i + 1][0], coords[i + 1][1])
        d, _, _ = vincenty_distance(lon1, lat1, lon2, lat2)
        perimeter += d

    compactness = (4.0 * math.pi * poly.area) / (perimeter * perimeter) if perimeter > 0 else 0.0

    surface_area = None
    void_fraction = None
    if dem_path and rasterio is not None:
        with rasterio.open(dem_path) as src:
            to_dem = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
            poly_dem = Polygon([to_dem.transform(lon, lat) for lon, lat in lon_lat_points])
            poly_dem = poly_dem if poly_dem.is_valid else poly_dem.buffer(0)

        dem, transform, res = _read_dem_window(dem_path, poly_dem.bounds)
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

        dz_dx, dz_dy = _horn_gradient(dem, res)
        slope = np.arctan(np.sqrt(dz_dx * dz_dx + dz_dy * dz_dy))
        cos_slope = np.clip(np.cos(slope), 1e-6, 1.0)
        pixel_surface = (res * res) / cos_slope
        valid = inside & ~np.isnan(dem)
        surface_area = float(np.sum(pixel_surface[valid]))

    return PolygonAreaMeasurement(
        planimetric_area_m2=float(poly.area),
        perimeter_m=float(perimeter),
        compactness_index=float(compactness),
        surface_area_m2=surface_area,
        void_fraction=void_fraction,
    )


def compute_slope_aspect(
    lon_lat_points: list[tuple[float, float]],
    dem_path: str,
) -> SlopeAspectMeasurement:
    if rasterio is None:
        raise RuntimeError("rasterio is not available")
    if len(lon_lat_points) < 3:
        raise ValueError("At least 3 polygon vertices are required")
    with rasterio.open(dem_path) as src:
        to_dem = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        poly_dem = Polygon([to_dem.transform(lon, lat) for lon, lat in lon_lat_points])
        poly_dem = poly_dem if poly_dem.is_valid else poly_dem.buffer(0)

    dem, transform, res = _read_dem_window(dem_path, poly_dem.bounds)
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

    dz_dx, dz_dy = _horn_gradient(dem, res)
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


def compute_volume(
    lon_lat_points: list[tuple[float, float]],
    dem_path: str,
) -> VolumeMeasurement:
    if rasterio is None:
        raise RuntimeError("rasterio is not available")
    if len(lon_lat_points) < 3:
        raise ValueError("At least 3 polygon vertices are required")

    with rasterio.open(dem_path) as src:
        to_dem = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        poly_dem = Polygon([to_dem.transform(lon, lat) for lon, lat in lon_lat_points])
        poly_dem = poly_dem if poly_dem.is_valid else poly_dem.buffer(0)

    dem, transform, res = _read_dem_window(dem_path, poly_dem.bounds)
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


def compute_viewshed(
    observer_lon: float,
    observer_lat: float,
    dem_path: str,
    observer_height_m: float = 1.8,
    target_height_m: float = 0.0,
    max_radius_m: float = 400.0,
    apply_refraction: bool = True,
    refraction_k: float = 0.13,
) -> ViewshedMeasurement:
    if rasterio is None:
        raise RuntimeError("rasterio is not available")

    with rasterio.open(dem_path) as src:
        to_dem = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        obs_x, obs_y = to_dem.transform(observer_lon, observer_lat)

    bounds = (obs_x - max_radius_m, obs_y - max_radius_m, obs_x + max_radius_m, obs_y + max_radius_m)
    dem, affine_transform, res = _read_dem_window(dem_path, bounds)
    h, w = dem.shape

    obs_row, obs_col = rowcol(affine_transform, obs_x, obs_y)
    obs_row = int(np.clip(obs_row, 0, h - 1))
    obs_col = int(np.clip(obs_col, 0, w - 1))

    z_obs = dem[obs_row, obs_col]
    if np.isnan(z_obs):
        z_obs = float(np.nanmean(dem))
    z_obs += observer_height_m

    visibility = np.zeros((h, w), dtype=np.bool_)

    for tgt_row in range(h):
        for tgt_col in range(w):
            dr = tgt_row - obs_row
            dc = tgt_col - obs_col
            dist_px = math.sqrt(dr * dr + dc * dc)
            dist_m = dist_px * res
            if dist_m > max_radius_m or dist_m < 1e-6:
                continue

            z_tgt = dem[tgt_row, tgt_col]
            if np.isnan(z_tgt):
                continue
            z_tgt += target_height_m

            n_steps = max(2, int(dist_px))
            visible = True
            for step in range(1, n_steps):
                t = step / n_steps
                r_i = int(round(obs_row + t * dr))
                c_i = int(round(obs_col + t * dc))
                r_i = int(np.clip(r_i, 0, h - 1))
                c_i = int(np.clip(c_i, 0, w - 1))
                z_terrain = dem[r_i, c_i]
                if np.isnan(z_terrain):
                    continue
                d_step = t * dist_m
                if apply_refraction and d_step > 100.0:
                    z_terrain -= refraction_k * (d_step * d_step) / (2.0 * EARTH_RADIUS_M)
                z_ray = z_obs + t * (z_tgt - z_obs)
                if z_terrain > z_ray:
                    visible = False
                    break
            visibility[tgt_row, tgt_col] = visible

    pixel_area = res * res
    visible_pixels = int(np.sum(visibility))
    total_pixels = int(np.sum(~np.isnan(dem)))

    rows, cols = np.where(visibility)
    if rows.size:
        dists = np.sqrt((rows - obs_row) ** 2 + (cols - obs_col) ** 2) * res
        max_dist = float(np.max(dists))
    else:
        max_dist = 0.0

    return ViewshedMeasurement(
        visible_area_m2=visible_pixels * pixel_area,
        total_area_m2=total_pixels * pixel_area,
        visible_fraction=(visible_pixels / total_pixels) if total_pixels > 0 else 0.0,
        max_visible_distance_m=max_dist,
    )


def measure_shadow_height(
    base_lon: float,
    base_lat: float,
    tip_lon: float,
    tip_lat: float,
    acquisition_datetime_utc: dt.datetime,
    dem_path: Optional[str] = None,
    imagery_resolution_m: float = 0.05,
) -> ShadowHeightMeasurement:
    def _solar_position_noaa(lat: float, lon: float, when_utc: dt.datetime) -> tuple[float, float]:
        """Return (solar_elevation_deg, solar_azimuth_deg) using NOAA approximation."""
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
        cos_zenith = (
            math.sin(lat_rad) * math.sin(decl)
            + math.cos(lat_rad) * math.cos(decl) * math.cos(ha_rad)
        )
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

    if get_altitude is not None and get_azimuth is not None:
        solar_az = float(get_azimuth(base_lat, base_lon, acquisition_datetime_utc))
        solar_el = float(get_altitude(base_lat, base_lon, acquisition_datetime_utc))
    else:
        solar_el, solar_az = _solar_position_noaa(base_lat, base_lon, acquisition_datetime_utc)

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
        z_base = _sample_dem_height(dem_path, base_lon, base_lat)
        z_tip = _sample_dem_height(dem_path, tip_lon, tip_lat)
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
