"""Custom tile-serving routes for the Tile Service.

This module defines a FastAPI ``APIRouter`` with four endpoints that sit
alongside (or replace) the default TiTiler routes:

    GET /tiles/{z}/{x}/{y}.png          — XYZ tile for a cataloged raster
    GET /preview/{raster_id}            — 512×512 preview thumbnail
    GET /metadata/{raster_id}           — bounds, zoom levels, center
    GET /health                         — service health check

All endpoints read raster files from ``settings.data_root`` and never
fetch remote URLs (air-gap / LAN security requirement 16.4).

Image manipulation query parameters (Requirement 11.6):
    contrast   — float multiplier applied to pixel values (default 1.0)
    brightness — float offset added after contrast (default 0.0)
    colormap   — named colormap string, e.g. "viridis" (default None)

Requirements: 11.1, 11.2, 11.4, 11.5, 11.6, 16.4
"""
from __future__ import annotations

import io
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from src_new.shared.config import settings
from src_new.shared.constants import TILE_SIZE, TILE_SIZE_PREVIEW

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tiles"])

# ---------------------------------------------------------------------------
# Optional heavy imports — rasterio / numpy / PIL are used for tile rendering.
# We guard them so the module can be imported in environments where they are
# not installed (e.g. lightweight CI).
# ---------------------------------------------------------------------------
try:
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_bounds
    from rasterio.warp import calculate_default_transform, reproject

    _RASTERIO_AVAILABLE = True
except ImportError:  # pragma: no cover
    _RASTERIO_AVAILABLE = False
    logger.warning(
        "rasterio is not installed. Tile rendering endpoints will return 503."
    )

try:
    from PIL import Image

    _PIL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PIL_AVAILABLE = False
    logger.warning("Pillow is not installed. PNG encoding will be unavailable.")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_raster_path(raster_id: str) -> Path:
    """Locate a raster file under ``settings.data_root`` by raster_id.

    The raster_id is treated as a relative path stem.  The function searches
    for files whose stem matches ``raster_id`` (case-sensitive) under
    ``settings.data_root``.  If no match is found a 404 is raised.

    This approach keeps the service stateless — no database lookup is needed
    for basic tile serving.  For production use, wire in the repository layer.

    Args:
        raster_id: Identifier string (UUID or filename stem).

    Returns:
        Absolute ``Path`` to the raster file.

    Raises:
        HTTPException(404): When no matching file is found.
        HTTPException(400): When ``raster_id`` contains path traversal characters.
    """
    # Security: reject path traversal attempts
    if ".." in raster_id or raster_id.startswith("/") or raster_id.startswith("\\"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid raster_id: '{raster_id}' contains illegal path characters.",
        )

    data_root = Path(settings.data_root)

    # 1. Exact match: raster_id is a relative path from data_root
    candidate = data_root / raster_id
    if candidate.is_file():
        resolved = candidate.resolve()
        cog_sibling = resolved.parent / f"{resolved.stem}.cog.tif"
        if cog_sibling.is_file():
            return cog_sibling.resolve()
        return resolved

    # 2. Stem match: search recursively for a file whose stem == raster_id
    for ext in (".tif", ".tiff", ".jp2", ".j2k", ".j2c", ".mbtiles"):
        stem_candidate = data_root / f"{raster_id}{ext}"
        if stem_candidate.is_file():
            resolved = stem_candidate.resolve()
            cog_sibling = resolved.parent / f"{resolved.stem}.cog.tif"
            if cog_sibling.is_file():
                return cog_sibling.resolve()
            return resolved

    # 3. Recursive search (slower, used as fallback)
    for found in data_root.rglob("*"):
        if found.is_file() and (found.stem == raster_id or found.name == raster_id):
            resolved = found.resolve()
            cog_sibling = resolved.parent / f"{resolved.stem}.cog.tif"
            if cog_sibling.is_file():
                return cog_sibling.resolve()
            return resolved

    raise HTTPException(
        status_code=404,
        detail=f"Raster '{raster_id}' not found under data_root '{data_root}'.",
    )


def _apply_contrast_brightness(
    array: "np.ndarray",  # type: ignore[name-defined]
    contrast: float,
    brightness: float,
) -> "np.ndarray":  # type: ignore[name-defined]
    """Apply contrast and brightness adjustments to a numpy array.

    Formula: ``output = clip(array * contrast + brightness, 0, 255)``

    Args:
        array: Input pixel array (float32 or uint8).
        contrast: Multiplicative factor (1.0 = no change).
        brightness: Additive offset in [0, 255] scale (0.0 = no change).

    Returns:
        uint8 numpy array with values clipped to [0, 255].
    """
    adjusted = array.astype("float32") * contrast + brightness
    return np.clip(adjusted, 0, 255).astype("uint8")


def _array_to_png(array: "np.ndarray") -> bytes:  # type: ignore[name-defined]
    """Encode a (bands, H, W) or (H, W) numpy array as PNG bytes.

    Args:
        array: Pixel data in (bands, H, W) or (H, W) shape.

    Returns:
        PNG-encoded bytes.

    Raises:
        HTTPException(503): When Pillow is not available.
    """
    if not _PIL_AVAILABLE:  # pragma: no cover
        raise HTTPException(
            status_code=503,
            detail="Pillow is not installed; PNG encoding is unavailable.",
        )

    if array.ndim == 3:
        # (bands, H, W) → (H, W, bands)
        array = np.transpose(array, (1, 2, 0))

    if array.ndim == 2:
        img = Image.fromarray(array, mode="L")
    elif array.shape[2] == 1:
        img = Image.fromarray(array[:, :, 0], mode="L")
    elif array.shape[2] == 3:
        img = Image.fromarray(array, mode="RGB")
    elif array.shape[2] == 4:
        img = Image.fromarray(array, mode="RGBA")
    else:
        # Flatten to grayscale for unusual band counts
        img = Image.fromarray(array[:, :, 0], mode="L")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _read_tile_from_raster(
    raster_path: Path,
    z: int,
    x: int,
    y: int,
    tile_size: int = TILE_SIZE,
) -> "np.ndarray":  # type: ignore[name-defined]
    """Read a single XYZ tile from a raster file using rasterio.

    Reprojects the raster to EPSG:3857 (Web Mercator) on the fly and
    resamples to ``tile_size × tile_size`` pixels.

    Args:
        raster_path: Absolute path to the raster file.
        z: Zoom level.
        x: Tile column.
        y: Tile row.
        tile_size: Output tile size in pixels.

    Returns:
        numpy array of shape (bands, tile_size, tile_size) with dtype uint8.

    Raises:
        HTTPException(404): When the tile is outside the raster's extent.
        HTTPException(503): When rasterio is not available.
    """
    if not _RASTERIO_AVAILABLE:  # pragma: no cover
        raise HTTPException(
            status_code=503,
            detail="rasterio is not installed; tile rendering is unavailable.",
        )

    # Convert XYZ tile coordinates to Web Mercator bounds
    # Tile bounds formula: https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames
    import math

    n = 2**z
    lon_min = x / n * 360.0 - 180.0
    lon_max = (x + 1) / n * 360.0 - 180.0
    lat_max_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat_min_rad = math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n)))
    lat_min = math.degrees(lat_min_rad)
    lat_max = math.degrees(lat_max_rad)

    # Convert to Web Mercator (EPSG:3857)
    from pyproj import Transformer  # type: ignore[import]

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    west, south = transformer.transform(lon_min, lat_min)
    east, north = transformer.transform(lon_max, lat_max)

    with rasterio.open(str(raster_path)) as src:
        # Reproject raster to EPSG:3857 and read the tile window
        dst_crs = "EPSG:3857"
        transform, width, height = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds
        )

        # Build output array
        bands = min(src.count, 4)  # cap at RGBA
        tile_data = np.zeros((bands, tile_size, tile_size), dtype="uint8")

        tile_transform = from_bounds(west, south, east, north, tile_size, tile_size)

        for band_idx in range(1, bands + 1):
            band_data = np.zeros((tile_size, tile_size), dtype="float32")
            reproject(
                source=rasterio.band(src, band_idx),
                destination=band_data,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=tile_transform,
                dst_crs=dst_crs,
                resampling=Resampling.bilinear,
            )
            # Normalize to uint8
            band_min = float(band_data.min())
            band_max = float(band_data.max())
            if band_max > band_min:
                normalized = (band_data - band_min) / (band_max - band_min) * 255
            else:
                normalized = band_data * 0
            tile_data[band_idx - 1] = normalized.astype("uint8")

    return tile_data


def _read_preview_from_raster(
    raster_path: Path,
    preview_size: int = TILE_SIZE_PREVIEW,
) -> "np.ndarray":  # type: ignore[name-defined]
    """Read a downsampled preview image from a raster file.

    Args:
        raster_path: Absolute path to the raster file.
        preview_size: Output image size in pixels (square).

    Returns:
        numpy array of shape (bands, preview_size, preview_size) with dtype uint8.

    Raises:
        HTTPException(503): When rasterio is not available.
    """
    if not _RASTERIO_AVAILABLE:  # pragma: no cover
        raise HTTPException(
            status_code=503,
            detail="rasterio is not installed; preview rendering is unavailable.",
        )

    with rasterio.open(str(raster_path)) as src:
        bands = min(src.count, 4)
        preview_data = np.zeros((bands, preview_size, preview_size), dtype="uint8")

        for band_idx in range(1, bands + 1):
            band_data = src.read(
                band_idx,
                out_shape=(preview_size, preview_size),
                resampling=Resampling.bilinear,
            ).astype("float32")

            band_min = float(band_data.min())
            band_max = float(band_data.max())
            if band_max > band_min:
                normalized = (band_data - band_min) / (band_max - band_min) * 255
            else:
                normalized = band_data * 0
            preview_data[band_idx - 1] = normalized.astype("uint8")

    return preview_data


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/tiles/{z}/{x}/{y}.png",
    response_class=Response,
    summary="Serve an XYZ map tile as PNG",
    description=(
        "Returns a {TILE_SIZE}×{TILE_SIZE} PNG tile for the given XYZ coordinates. "
        "The ``raster_id`` query parameter identifies the raster to serve. "
        "Optional ``contrast``, ``brightness``, and ``colormap`` parameters "
        "allow real-time image manipulation (Requirement 11.6)."
    ).format(TILE_SIZE=TILE_SIZE),
    responses={
        200: {"content": {"image/png": {}}, "description": "PNG tile"},
        404: {"description": "Raster not found or tile outside extent"},
        503: {"description": "Rendering dependencies not available"},
    },
)
async def get_tile(
    z: int,
    x: int,
    y: int,
    raster_id: str = Query(..., description="Raster identifier (UUID or filename stem)"),
    contrast: float = Query(
        default=1.0,
        ge=0.0,
        le=10.0,
        description="Contrast multiplier applied to pixel values (1.0 = no change).",
    ),
    brightness: float = Query(
        default=0.0,
        ge=-255.0,
        le=255.0,
        description="Brightness offset added after contrast (0.0 = no change).",
    ),
    colormap: Optional[str] = Query(
        default=None,
        description="Named colormap to apply, e.g. 'viridis', 'gray', 'terrain'.",
    ),
) -> Response:
    """Serve a single XYZ tile as PNG.

    Reads the raster from ``settings.data_root``, reprojects to Web Mercator,
    resamples to ``TILE_SIZE × TILE_SIZE``, applies contrast/brightness, and
    returns a PNG response.

    Requirements: 11.5, 11.6
    """
    raster_path = _resolve_raster_path(raster_id)
    logger.debug(
        "Serving tile z=%d x=%d y=%d from %s (contrast=%.2f brightness=%.2f colormap=%s)",
        z, x, y, raster_path, contrast, brightness, colormap,
    )

    tile_data = _read_tile_from_raster(raster_path, z, x, y, tile_size=TILE_SIZE)

    # Apply contrast / brightness
    if contrast != 1.0 or brightness != 0.0:
        tile_data = _apply_contrast_brightness(tile_data, contrast, brightness)

    # Apply colormap (single-band only; multi-band colormaps are ignored)
    if colormap is not None and _PIL_AVAILABLE and _RASTERIO_AVAILABLE:
        try:
            import matplotlib.cm as _cm  # type: ignore[import]
            import matplotlib.colors as _mcolors  # type: ignore[import]

            cmap = _cm.get_cmap(colormap)
            # Use first band for colormap application
            band = tile_data[0].astype("float32") / 255.0
            rgba = (_mcolors.to_rgba_array(cmap(band.ravel())) * 255).astype("uint8")
            rgba = rgba.reshape(tile_data.shape[1], tile_data.shape[2], 4)
            tile_data = np.transpose(rgba, (2, 0, 1))
        except Exception as exc:
            logger.warning("Failed to apply colormap '%s': %s", colormap, exc)

    png_bytes = _array_to_png(tile_data)
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=3600",
            "X-Raster-Id": raster_id,
        },
    )


@router.get(
    "/preview/{raster_id}",
    response_class=Response,
    summary="Serve a preview thumbnail for a raster",
    description=(
        f"Returns a {TILE_SIZE_PREVIEW}×{TILE_SIZE_PREVIEW} PNG thumbnail "
        "for the specified raster. Supports the same ``contrast``, "
        "``brightness``, and ``colormap`` query parameters as the tile endpoint."
    ),
    responses={
        200: {"content": {"image/png": {}}, "description": "PNG preview"},
        404: {"description": "Raster not found"},
        503: {"description": "Rendering dependencies not available"},
    },
)
async def get_preview(
    raster_id: str,
    contrast: float = Query(
        default=1.0,
        ge=0.0,
        le=10.0,
        description="Contrast multiplier (1.0 = no change).",
    ),
    brightness: float = Query(
        default=0.0,
        ge=-255.0,
        le=255.0,
        description="Brightness offset (0.0 = no change).",
    ),
    colormap: Optional[str] = Query(
        default=None,
        description="Named colormap to apply, e.g. 'viridis'.",
    ),
) -> Response:
    """Return a downsampled preview image for a cataloged raster.

    The preview is always ``TILE_SIZE_PREVIEW × TILE_SIZE_PREVIEW`` pixels
    (512×512 by default) regardless of the raster's native resolution.

    Requirements: 11.5, 11.6
    """
    raster_path = _resolve_raster_path(raster_id)
    logger.debug(
        "Serving preview for raster_id=%s from %s", raster_id, raster_path
    )

    preview_data = _read_preview_from_raster(raster_path, preview_size=TILE_SIZE_PREVIEW)

    if contrast != 1.0 or brightness != 0.0:
        preview_data = _apply_contrast_brightness(preview_data, contrast, brightness)

    if colormap is not None and _PIL_AVAILABLE and _RASTERIO_AVAILABLE:
        try:
            import matplotlib.cm as _cm  # type: ignore[import]
            import matplotlib.colors as _mcolors  # type: ignore[import]

            cmap = _cm.get_cmap(colormap)
            band = preview_data[0].astype("float32") / 255.0
            rgba = (_mcolors.to_rgba_array(cmap(band.ravel())) * 255).astype("uint8")
            rgba = rgba.reshape(preview_data.shape[1], preview_data.shape[2], 4)
            preview_data = np.transpose(rgba, (2, 0, 1))
        except Exception as exc:
            logger.warning("Failed to apply colormap '%s': %s", colormap, exc)

    png_bytes = _array_to_png(preview_data)
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Raster-Id": raster_id,
        },
    )


@router.get(
    "/metadata/{raster_id}",
    summary="Return tile metadata for a raster",
    description=(
        "Returns geographic bounds, min/max zoom levels, and center point "
        "for the specified raster. Used by CesiumJS to configure imagery layers."
    ),
    responses={
        200: {"description": "Tile metadata JSON"},
        404: {"description": "Raster not found"},
        503: {"description": "rasterio not available"},
    },
)
async def get_metadata(raster_id: str) -> dict:
    """Return tile metadata for a cataloged raster.

    Response schema::

        {
            "raster_id": "...",
            "bounds": {
                "min_lon": float, "min_lat": float,
                "max_lon": float, "max_lat": float
            },
            "minzoom": int,
            "maxzoom": int,
            "center": [lon, lat],
            "crs": "EPSG:...",
            "width": int,
            "height": int,
            "bands": int
        }

    Requirements: 11.5
    """
    if not _RASTERIO_AVAILABLE:  # pragma: no cover
        raise HTTPException(
            status_code=503,
            detail="rasterio is not installed; metadata endpoint is unavailable.",
        )

    raster_path = _resolve_raster_path(raster_id)
    logger.debug("Reading metadata for raster_id=%s from %s", raster_id, raster_path)

    with rasterio.open(str(raster_path)) as src:
        # Reproject bounds to WGS 84 for the response
        from rasterio.warp import transform_bounds  # type: ignore[import]

        try:
            bounds_wgs84 = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
        except Exception:
            # If reprojection fails, return native bounds
            bounds_wgs84 = src.bounds

        min_lon, min_lat, max_lon, max_lat = bounds_wgs84
        center_lon = (min_lon + max_lon) / 2.0
        center_lat = (min_lat + max_lat) / 2.0

        # Estimate zoom levels from resolution
        import math

        # Native resolution in degrees per pixel (approximate)
        lon_span = max_lon - min_lon
        lat_span = max_lat - min_lat
        res_deg = min(lon_span / src.width, lat_span / src.height) if src.width and src.height else 1.0

        # Zoom level where 1 pixel ≈ 1 tile pixel
        # At zoom 0, the whole world (360°) fits in TILE_SIZE pixels
        # → resolution at zoom z = 360 / (TILE_SIZE * 2^z)
        if res_deg > 0:
            maxzoom = max(0, min(26, int(math.log2(360.0 / (TILE_SIZE * res_deg)))))
        else:
            maxzoom = 18
        minzoom = max(0, maxzoom - 8)

        crs_string = src.crs.to_string() if src.crs else "unknown"

    return {
        "raster_id": raster_id,
        "bounds": {
            "min_lon": min_lon,
            "min_lat": min_lat,
            "max_lon": max_lon,
            "max_lat": max_lat,
        },
        "minzoom": minzoom,
        "maxzoom": maxzoom,
        "center": [center_lon, center_lat],
        "crs": crs_string,
        "width": src.width if _RASTERIO_AVAILABLE else 0,
        "height": src.height if _RASTERIO_AVAILABLE else 0,
        "bands": src.count if _RASTERIO_AVAILABLE else 0,
    }


@router.get(
    "/health",
    summary="Tile Service health check",
    description="Returns the operational status of the Tile Service.",
    responses={
        200: {"description": "Service is healthy"},
        503: {"description": "Service is degraded"},
    },
)
async def health_check() -> dict:
    """Return the health status of the Tile Service.

    Checks:
    - Whether rasterio is available (required for tile rendering)
    - Whether Pillow is available (required for PNG encoding)
    - Whether ``settings.data_root`` exists and is readable

    Requirements: 11.5
    """
    data_root = Path(settings.data_root)
    data_root_ok = data_root.is_dir() and os.access(str(data_root), os.R_OK)

    status = "healthy"
    issues: list[str] = []

    if not _RASTERIO_AVAILABLE:
        issues.append("rasterio not installed")
        status = "degraded"

    if not _PIL_AVAILABLE:
        issues.append("Pillow not installed")
        status = "degraded"

    if not data_root_ok:
        issues.append(f"data_root '{data_root}' is not accessible")
        status = "degraded"

    return {
        "status": status,
        "rasterio_available": _RASTERIO_AVAILABLE,
        "pillow_available": _PIL_AVAILABLE,
        "data_root": str(data_root),
        "data_root_accessible": data_root_ok,
        "issues": issues,
    }


__all__ = ["router"]
