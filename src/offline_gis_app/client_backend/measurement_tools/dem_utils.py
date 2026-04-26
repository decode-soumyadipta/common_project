"""DEM utility functions for reading and processing elevation data.

This module provides utilities for:
- Reading DEM windows with bounds
- Sampling elevation at points
- Computing gradients using Horn's algorithm
- 3x3 convolution operations
"""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

try:
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import rowcol
    from rasterio.windows import Window, from_bounds
except ImportError:
    rasterio = None
    Resampling = None
    rowcol = None
    Window = None
    from_bounds = None


def read_dem_window(
    dem_path: str,
    bounds: tuple[float, float, float, float],
) -> tuple[NDArray[np.float64], object, float]:
    """Read a window of DEM data given geographic bounds.
    
    Args:
        dem_path: Path to the DEM raster file.
        bounds: Geographic bounds as (minx, miny, maxx, maxy).
        
    Returns:
        Tuple of (data array, transform, resolution).
        
    Raises:
        RuntimeError: If rasterio is not available.

    """
    if rasterio is None:
        raise RuntimeError("rasterio is not available")
    
    with rasterio.open(dem_path) as src:
        # Clip requested bounds to DEM bounds to avoid reading outside the raster
        dem_bounds = src.bounds
        clipped_bounds = (
            max(bounds[0], dem_bounds.left),
            max(bounds[1], dem_bounds.bottom),
            min(bounds[2], dem_bounds.right),
            min(bounds[3], dem_bounds.top),
        )
        
        # Check if there's any overlap
        if (clipped_bounds[0] >= clipped_bounds[2] or 
            clipped_bounds[1] >= clipped_bounds[3]):
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Requested bounds {bounds} do not overlap with DEM bounds {dem_bounds}")
            return np.empty((0, 0), dtype=np.float64), src.transform, float(src.res[0])
        
        win = from_bounds(*clipped_bounds, transform=src.transform)

        # Prevent OOM bus errors on massive windows
        max_dim = 4000
        h, w = int(win.height), int(win.width)
        if h <= 0 or w <= 0:
            return np.empty((0, 0), dtype=np.float64), src.transform, float(src.res[0])

        if h > max_dim or w > max_dim:
            scale = max_dim / max(h, w)
            out_shape = (1, int(h * scale), int(w * scale))
            data = src.read(
                1, window=win, out_shape=out_shape[1:], resampling=Resampling.bilinear
            ).astype(np.float64)
            transform = src.window_transform(win) * rasterio.Affine.scale(
                1 / scale, 1 / scale
            )
            res = float(src.res[0]) / scale
        else:
            data = src.read(1, window=win, resampling=Resampling.bilinear).astype(
                np.float64
            )
            transform = src.window_transform(win)
            res = float(src.res[0])

        nodata = src.nodata
        if nodata is not None:
            data = np.where(data == nodata, np.nan, data)

    return data, transform, res


def sample_dem_height(dem_path: str, lon: float, lat: float) -> float:
    """Sample the elevation at a single geographic point.
    
    Args:
        dem_path: Path to the DEM raster file.
        lon: Longitude in degrees.
        lat: Latitude in degrees.
        
    Returns:
        Elevation in meters, or NaN if unavailable.

    """
    if rasterio is None:
        return float("nan")

    from pyproj import Transformer

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


def convolve3x3_nearest(
    arr: NDArray[np.float64], kernel: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Vectorized 3x3 convolution with nearest-edge padding.
    
    Args:
        arr: Input array to convolve.
        kernel: 3x3 convolution kernel.
        
    Returns:
        Convolved array with same shape as input.

    """
    padded = np.pad(arr, pad_width=1, mode="edge")
    out = np.zeros_like(arr, dtype=np.float64)
    for r in range(3):
        for c in range(3):
            out += kernel[r, c] * padded[r : r + arr.shape[0], c : c + arr.shape[1]]
    return out


def horn_gradient(
    dem: NDArray[np.float64], res: float
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Compute gradients using Horn's algorithm (as used in GDAL).
    
    Args:
        dem: DEM elevation array.
        res: Pixel resolution in meters.
        
    Returns:
        Tuple of (dz_dx, dz_dy) gradient arrays.

    """
    nan_mask = np.isnan(dem)
    fill = np.where(nan_mask, np.nanmean(dem), dem)

    kx = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float64) / (8.0 * res)
    ky = np.array([[1, 2, 1], [0, 0, 0], [-1, -2, -1]], dtype=np.float64) / (8.0 * res)

    dz_dx = convolve3x3_nearest(fill, kx)
    dz_dy = convolve3x3_nearest(fill, ky)
    dz_dx[nan_mask] = np.nan
    dz_dy[nan_mask] = np.nan
    return dz_dx, dz_dy
