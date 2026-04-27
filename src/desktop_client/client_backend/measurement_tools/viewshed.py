from __future__ import annotations

import math
import numpy as np

try:
    import rasterio
    from rasterio.transform import rowcol
    from pyproj import Transformer
except ImportError:
    rasterio = None
    rowcol = None
    Transformer = None

from desktop_client.client_backend.measurement_tools.models import ViewshedMeasurement
from desktop_client.client_backend.measurement_tools.dem_utils import read_dem_window

EARTH_RADIUS_M = 6_371_000.0


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
    """Computes a Viewshed / Line-Of-Sight area from a central observer point."""
    if rasterio is None:
        raise RuntimeError("rasterio is not available")

    with rasterio.open(dem_path) as src:
        to_dem = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        obs_x, obs_y = to_dem.transform(observer_lon, observer_lat)

    bounds = (
        obs_x - max_radius_m,
        obs_y - max_radius_m,
        obs_x + max_radius_m,
        obs_y + max_radius_m,
    )
    dem, affine_transform, res = read_dem_window(dem_path, bounds)
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
                    z_terrain -= (
                        refraction_k * (d_step * d_step) / (2.0 * EARTH_RADIUS_M)
                    )
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
