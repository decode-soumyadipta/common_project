"""DEM profile sampling utilities for elevation extraction along a line."""

from pathlib import Path

import numpy as np

from offline_gis_app.server_ingestion.services.metadata_extractor import (
    _read_with_rasterio,
)


def _transform_line_points_to_dataset_crs(
    dataset,
    line_points: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Transform incoming EPSG:4326 lon/lat points into dataset CRS coordinates."""
    if dataset.crs is None:
        raise ValueError("Raster CRS is missing; cannot align profile coordinates.")

    source_crs = "EPSG:4326"
    target_crs = str(dataset.crs)
    if target_crs.upper().replace("::", ":") == source_crs:
        return [(float(lon), float(lat)) for lon, lat in line_points]

    try:
        from rasterio.warp import transform  # type: ignore
    except ImportError as exc:
        raise ValueError(
            "rasterio.warp is required for CRS profile transformation."
        ) from exc

    lons = [float(lon) for lon, _lat in line_points]
    lats = [float(lat) for _lon, lat in line_points]
    xs, ys = transform(source_crs, dataset.crs, lons, lats)
    return [(float(x), float(y)) for x, y in zip(xs, ys)]


def sample_profile(
    path: Path, line_points: list[tuple[float, float]], samples: int
) -> list[float]:
    """Sample raster elevation values between the first and last supplied points."""
    if samples < 2:
        raise ValueError("samples must be at least 2")
    if len(line_points) < 2:
        raise ValueError("line_points must include at least two points")

    start = np.array(line_points[0], dtype=float)
    end = np.array(line_points[-1], dtype=float)
    fractions = np.linspace(0.0, 1.0, samples)
    world_points = [tuple(start + (end - start) * t) for t in fractions]

    with _read_with_rasterio(path) as ds:
        dataset_points = _transform_line_points_to_dataset_crs(ds, world_points)
        values: list[float] = []
        for x, y in dataset_points:
            row, col = ds.index(x, y)
            if row < 0 or col < 0 or row >= ds.height or col >= ds.width:
                values.append(float("nan"))
                continue
            pixel = ds.read(1, window=((row, row + 1), (col, col + 1)))
            if pixel.size == 0:
                values.append(float("nan"))
                continue
            values.append(float(pixel[0, 0]))
        if all(np.isnan(value) for value in values):
            raise ValueError("Profile transect falls outside raster extent.")
    return values
