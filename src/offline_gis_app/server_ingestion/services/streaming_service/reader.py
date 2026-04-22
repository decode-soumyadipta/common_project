from __future__ import annotations

from pathlib import Path
import numpy as np

from rasterio.windows import Window

from offline_gis_app.config.settings import settings
from offline_gis_app.server_ingestion.services.streaming_service.contracts import RasterChunk


def estimate_raster_memory_mb(path: Path, band_count: int = 1) -> int:
    """Estimate full-raster in-memory footprint to guide chunked processing."""
    try:
        import rasterio  # type: ignore
    except Exception:
        return 0

    with rasterio.open(path) as dataset:
        bytes_per_pixel = max(1, int(np.dtype(dataset.dtypes[0]).itemsize))
        total_bytes = int(dataset.width) * int(dataset.height) * int(max(1, band_count)) * bytes_per_pixel
    return int(total_bytes / (1024 * 1024))


def iter_raster_chunks(path: Path, *, band: int = 1, chunk_size: int | None = None):
    """Yield raster chunks using bounded windows for large-file safety."""
    try:
        import rasterio  # type: ignore
    except Exception as exc:
        raise RuntimeError("rasterio is required for chunked raster streaming") from exc

    size = int(chunk_size or settings.ingest_window_chunk_size)
    if size <= 0:
        raise ValueError("chunk_size must be greater than zero")

    with rasterio.open(path) as dataset:
        for row_off in range(0, dataset.height, size):
            height = min(size, dataset.height - row_off)
            for col_off in range(0, dataset.width, size):
                width = min(size, dataset.width - col_off)
                window = Window(col_off=col_off, row_off=row_off, width=width, height=height)
                data = dataset.read(band, window=window)
                yield RasterChunk(band=band, window=window, data=data)
