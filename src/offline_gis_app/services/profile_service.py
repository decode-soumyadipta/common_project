from pathlib import Path

import numpy as np

from offline_gis_app.services.metadata_extractor import _read_with_rasterio


def sample_profile(path: Path, line_points: list[tuple[float, float]], samples: int) -> list[float]:
    if samples < 2:
        raise ValueError("samples must be at least 2")
    if len(line_points) < 2:
        raise ValueError("line_points must include at least two points")

    start = np.array(line_points[0], dtype=float)
    end = np.array(line_points[-1], dtype=float)
    fractions = np.linspace(0.0, 1.0, samples)
    world_points = [tuple(start + (end - start) * t) for t in fractions]

    with _read_with_rasterio(path) as ds:
        values: list[float] = []
        for x, y in world_points:
            row, col = ds.index(x, y)
            pixel = ds.read(1, window=((row, row + 1), (col, col + 1)))
            values.append(float(pixel[0, 0]))
    return values

