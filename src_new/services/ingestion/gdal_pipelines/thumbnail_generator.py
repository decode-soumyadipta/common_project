"""Thumbnail / preview image generation for the Ingestion Service.

Generates a square PNG preview image from any GDAL-readable raster.
The default output size is ``TILE_SIZE_PREVIEW`` (512 × 512 pixels) as
defined in ``src_new/shared/constants.py``.

All GDAL operations are preceded by ``settings.apply_gdal_env()`` to ensure
the environment variables defined in ``src_new/shared/config.py`` are applied
before any GDAL call.

Requirements: 9.1, 9.2
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src_new.shared.config import settings
from src_new.shared.constants import TILE_SIZE_PREVIEW

LOGGER = logging.getLogger("services.ingestion.thumbnail_generator")


# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThumbnailResult:
    """Outcome of a thumbnail generation operation.

    Attributes:
        source_path: Original input raster path.
        output_path: Path to the generated PNG thumbnail.
        width: Width of the thumbnail in pixels.
        height: Height of the thumbnail in pixels.
        band_count: Number of bands written to the PNG.
    """

    source_path: Path
    output_path: Path
    width: int
    height: int
    band_count: int


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize_band_to_uint8(data, nodata=None):  # type: ignore[return]
    """Stretch *data* to the 0–255 range and return a ``numpy.ndarray`` of dtype uint8.

    Uses a 2 %–98 % percentile stretch to avoid outliers dominating the scale.
    Pixels equal to *nodata* are set to 0 in the output.
    """
    import numpy as np  # type: ignore

    arr = data.astype(np.float32)

    # Mask nodata
    if nodata is not None:
        mask = arr == float(nodata)
        arr[mask] = np.nan

    valid = arr[~np.isnan(arr)]
    if valid.size == 0:
        return np.zeros(data.shape, dtype=np.uint8)

    p2, p98 = float(np.nanpercentile(arr, 2)), float(np.nanpercentile(arr, 98))
    if p98 == p2:
        # Flat image — map everything to mid-grey
        result = np.full(data.shape, 128, dtype=np.uint8)
    else:
        stretched = (arr - p2) / (p98 - p2) * 255.0
        stretched = np.clip(stretched, 0, 255)
        result = stretched.astype(np.uint8)

    # Zero out nodata pixels
    if nodata is not None:
        result[mask] = 0

    return result


def _select_rgb_bands(band_count: int) -> list[int]:
    """Return a list of 1-based band indices to use for an RGB(A) preview.

    For single-band rasters the same band is replicated three times so the
    output is always a valid RGB PNG.
    """
    if band_count >= 3:
        return [1, 2, 3]
    if band_count == 2:
        return [1, 1, 2]  # grey + alpha-like
    return [1, 1, 1]  # single band → greyscale RGB


# ---------------------------------------------------------------------------
# Rasterio implementation (preferred)
# ---------------------------------------------------------------------------


def _generate_with_rasterio(
    input_path: Path,
    output_path: Path,
    size: int,
) -> ThumbnailResult:
    """Generate a thumbnail using Rasterio (preferred path)."""
    import numpy as np  # type: ignore
    import rasterio  # type: ignore
    from rasterio.enums import Resampling  # type: ignore
    from PIL import Image  # type: ignore

    with rasterio.open(input_path) as src:
        band_count = src.count

        # Compute resampled dimensions preserving aspect ratio
        orig_w, orig_h = src.width, src.height
        if orig_w >= orig_h:
            out_w = size
            out_h = max(1, int(size * orig_h / orig_w))
        else:
            out_h = size
            out_w = max(1, int(size * orig_w / orig_h))

        band_indices = _select_rgb_bands(band_count)
        channels: list = []

        for idx in band_indices:
            band = src.read(
                idx,
                out_shape=(out_h, out_w),
                resampling=Resampling.bilinear,
            )
            nodata = src.nodata
            channels.append(_normalize_band_to_uint8(band, nodata))

        # Stack into H×W×3 array
        rgb = np.stack(channels, axis=-1)
        img = Image.fromarray(rgb, mode="RGB")

        # Pad to exact square if needed
        if img.width != size or img.height != size:
            canvas = Image.new("RGB", (size, size), (0, 0, 0))
            canvas.paste(img, (0, 0))
            img = canvas

        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(output_path), format="PNG", optimize=True)

    return ThumbnailResult(
        source_path=input_path,
        output_path=output_path,
        width=size,
        height=size,
        band_count=len(band_indices),
    )


# ---------------------------------------------------------------------------
# GDAL fallback implementation
# ---------------------------------------------------------------------------


def _generate_with_gdal(
    input_path: Path,
    output_path: Path,
    size: int,
) -> ThumbnailResult:
    """Generate a thumbnail using GDAL (fallback when Rasterio/Pillow unavailable)."""
    from osgeo import gdal  # type: ignore
    import numpy as np  # type: ignore

    gdal.UseExceptions()

    src_ds = gdal.Open(str(input_path))
    if src_ds is None:
        raise RuntimeError(f"GDAL could not open raster: {input_path}")

    band_count = src_ds.RasterCount
    orig_w = src_ds.RasterXSize
    orig_h = src_ds.RasterYSize

    # Compute output dimensions preserving aspect ratio
    if orig_w >= orig_h:
        out_w = size
        out_h = max(1, int(size * orig_h / orig_w))
    else:
        out_h = size
        out_w = max(1, int(size * orig_w / orig_h))

    band_indices = _select_rgb_bands(band_count)
    channels: list = []

    for idx in band_indices:
        band_obj = src_ds.GetRasterBand(idx)
        nodata = band_obj.GetNoDataValue()
        # ReadAsArray with buf_xsize/buf_ysize triggers GDAL resampling
        data = band_obj.ReadAsArray(buf_xsize=out_w, buf_ysize=out_h)
        if data is None:
            raise RuntimeError(
                f"GDAL ReadAsArray failed for band {idx} of {input_path}"
            )
        channels.append(_normalize_band_to_uint8(data, nodata))

    src_ds = None

    # Write PNG via GDAL MEM → PNG driver
    import numpy as np  # noqa: F811 (already imported above)

    rgb = np.stack(channels, axis=-1)  # H×W×3

    # Pad to exact square
    canvas = np.zeros((size, size, 3), dtype=np.uint8)
    canvas[:out_h, :out_w, :] = rgb

    # Create in-memory GDAL dataset and write PNG
    mem_driver = gdal.GetDriverByName("MEM")
    mem_ds = mem_driver.Create("", size, size, 3, gdal.GDT_Byte)
    for i in range(3):
        mem_ds.GetRasterBand(i + 1).WriteArray(canvas[:, :, i])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    png_driver = gdal.GetDriverByName("PNG")
    png_driver.CreateCopy(str(output_path), mem_ds, strict=0)
    mem_ds = None

    return ThumbnailResult(
        source_path=input_path,
        output_path=output_path,
        width=size,
        height=size,
        band_count=len(band_indices),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_thumbnail(
    input_path: Path,
    output_path: Optional[Path] = None,
    size: int = TILE_SIZE_PREVIEW,
) -> ThumbnailResult:
    """Generate a square PNG preview image from *input_path*.

    The function first tries Rasterio + Pillow for the best quality output.
    If either library is unavailable it falls back to a pure-GDAL
    implementation.

    Args:
        input_path: Path to the source raster (GeoTIFF, JPEG2000, etc.).
        output_path: Destination path for the PNG thumbnail.  When ``None``,
            the thumbnail is placed next to the source with a ``_preview.png``
            suffix (e.g. ``raster_preview.png``).
        size: Side length of the square output image in pixels.  Defaults to
            ``TILE_SIZE_PREVIEW`` (512).

    Returns:
        :class:`ThumbnailResult` describing the generated thumbnail.

    Raises:
        FileNotFoundError: When *input_path* does not exist.
        RuntimeError: When both Rasterio and GDAL fail to generate the thumbnail.
        ImportError: When neither Rasterio nor GDAL is installed.
    """
    # Apply GDAL environment variables from centralized config before any GDAL call.
    settings.apply_gdal_env()

    input_path = Path(input_path).resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input raster not found: {input_path}")

    if output_path is None:
        output_path = input_path.parent / f"{input_path.stem}_preview.png"
    else:
        output_path = Path(output_path).resolve()

    if size < 1:
        raise ValueError(f"size must be a positive integer, got {size}")

    LOGGER.info("=" * 80)
    LOGGER.info("THUMBNAIL GENERATION: %s", input_path.name)
    LOGGER.info("  Output size : %d × %d px", size, size)
    LOGGER.info("  Output path : %s", output_path.name)
    LOGGER.info("=" * 80)

    # Try Rasterio + Pillow first (better resampling quality)
    rasterio_available = False
    pillow_available = False
    try:
        import rasterio  # type: ignore  # noqa: F401

        rasterio_available = True
    except ImportError:
        LOGGER.debug("rasterio not available — will try GDAL fallback")

    try:
        from PIL import Image  # type: ignore  # noqa: F401

        pillow_available = True
    except ImportError:
        LOGGER.debug("Pillow not available — will try GDAL fallback")

    if rasterio_available and pillow_available:
        try:
            result = _generate_with_rasterio(input_path, output_path, size)
            LOGGER.info(
                "✓ Thumbnail generated via Rasterio — %s (%d × %d px)",
                output_path.name,
                result.width,
                result.height,
            )
            return result
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning(
                "Rasterio thumbnail generation failed for %s: %s — trying GDAL fallback",
                input_path.name,
                exc,
            )

    # GDAL fallback
    try:
        from osgeo import gdal  # type: ignore  # noqa: F401
        import numpy as np  # type: ignore  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "Neither Rasterio+Pillow nor GDAL+NumPy are available. "
            "Install at least one of: rasterio+Pillow or gdal+numpy."
        ) from exc

    result = _generate_with_gdal(input_path, output_path, size)
    LOGGER.info(
        "✓ Thumbnail generated via GDAL — %s (%d × %d px)",
        output_path.name,
        result.width,
        result.height,
    )
    return result


__all__ = [
    "ThumbnailResult",
    "generate_thumbnail",
]
