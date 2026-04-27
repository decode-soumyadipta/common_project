from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from rasterio.windows import Window


@dataclass(frozen=True)
class RasterChunk:
    """Single read window from a raster source."""

    band: int
    window: Window
    data: np.ndarray
