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

Performance optimizations:
    - MBTiles files are served directly from SQLite (zero GDAL overhead)
    - LRU tile cache avoids redundant rendering for repeated requests
    - COG files are read via windowed reads with automatic overview selection
    - Non-COG rasters fall back to on-the-fly reprojection

Requirements: 11.1, 11.2, 11.4, 11.5, 11.6, 16.4
"""
from __future__ import annotations

import io
import logging
import math
import os
import sqlite3
import threading
import time
from collections import OrderedDict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from src_new.shared.config import settings
from src_new.shared.constants import TILE_SIZE, TILE_SIZE_PREVIEW

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tiles"])

# --------------------------------------------------------------------------- Optional heavy imports — rasterio / numpy / PIL are used for tile rendering. We guard them so the module can be imported in environments where they are not installed (e.g. lightweight CI). ---------------------------------------------------------------------------
try:
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_bounds
    from rasterio.warp import reproject, calculate_default_transform

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


# --------------------------------------------------------------------------- Thread-safe LRU tile cache ---------------------------------------------------------------------------


class _TileCache:
    """Thread-safe hybrid RAM/on-disk LRU cache for rendered PNG tile bytes.

    Keyed by ``(raster_path_str, z, x, y, contrast, brightness, colormap)``.
    Evicts least-recently-used entries in RAM when ``maxsize`` is exceeded.
    Caches tiles persistently on disk under settings.data_root / "tile_cache".
    Evicts oldest files on disk in a background thread when disk limits are exceeded.
    """

    def __init__(self, maxsize: int = 512, disk_limit: int = 20000):
        self._maxsize = max(1, maxsize)
        self._disk_limit = disk_limit
        self._cache: OrderedDict[tuple, bytes] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._disk_hits = 0
        self._write_count = 0
        self._cleanup_lock = threading.Lock()

        # Resolve disk cache directory under settings.data_root
        from src_new.shared.config import settings
        self._disk_dir = Path(settings.data_root) / "tile_cache"
        try:
            self._disk_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error("Failed to create disk cache directory %s: %s", self._disk_dir, e)

    def _get_hash(self, key: tuple) -> str:
        import hashlib
        # Ensure a robust, stable string key regardless of path separator styles
        path_str = str(key[0]).replace("\\", "/")
        key_str = f"{path_str}_z{key[1]}_x{key[2]}_y{key[3]}_c{key[4]}_b{key[5]}_cm{key[6]}"
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()

    def get(self, key: tuple) -> bytes | None:
        with self._lock:
            # 1. RAM Cache Lookup
            if key in self._cache:
                self._cache.move_to_end(key)
                self._hits += 1
                return self._cache[key]

            # 2. Disk Cache Lookup
            h = self._get_hash(key)
            filepath = self._disk_dir / f"{h}.bin"
            if filepath.exists():
                try:
                    # Update modification time to track LRU on disk
                    os.utime(filepath, None)
                    tile_bytes = filepath.read_bytes()

                    # Put back into RAM Cache
                    self._cache[key] = tile_bytes
                    if len(self._cache) > self._maxsize:
                        self._cache.popitem(last=False)

                    self._hits += 1
                    self._disk_hits += 1
                    return tile_bytes
                except Exception as e:
                    logger.error("Error reading tile from disk cache: %s", e)

            self._misses += 1
            return None

    def put(self, key: tuple, value: bytes) -> None:
        with self._lock:
            # 1. Store in RAM Cache
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = value
            else:
                self._cache[key] = value
                while len(self._cache) > self._maxsize:
                    self._cache.popitem(last=False)

            # 2. Store in Disk Cache
            h = self._get_hash(key)
            filepath = self._disk_dir / f"{h}.bin"
            try:
                filepath.write_bytes(value)
                self._write_count += 1
            except Exception as e:
                logger.error("Error writing tile to disk cache: %s", e)

        # Trigger background disk cache cleanup asynchronously when threshold reached
        if self._write_count >= 500:
            self._write_count = 0
            threading.Thread(target=self._cleanup_disk_cache, daemon=True).start()

    def _cleanup_disk_cache(self) -> None:
        if not self._cleanup_lock.acquire(blocking=False):
            return
        try:
            files = list(self._disk_dir.glob("*.bin"))
            if len(files) <= self._disk_limit:
                return

            logger.info("Cleaning up disk cache: %d files (limit is %d)", len(files), self._disk_limit)
            # Sort files by modification/access time ascending (oldest first)
            files.sort(key=lambda f: f.stat().st_mtime)

            target_count = int(self._disk_limit * 0.9)
            num_to_delete = len(files) - target_count

            deleted_count = 0
            for i in range(num_to_delete):
                try:
                    files[i].unlink(missing_ok=True)
                    deleted_count += 1
                except Exception as e:
                    logger.error("Failed to delete cached file %s: %s", files[i], e)

            logger.info("Disk cache cleanup completed: deleted %d files", deleted_count)
        except Exception as e:
            logger.error("Error during disk cache cleanup: %s", e)
        finally:
            self._cleanup_lock.release()

    @property
    def stats(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._cache),
                "maxsize": self._maxsize,
                "hits": self._hits,
                "disk_hits": self._disk_hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 4) if total > 0 else 0.0,
            }


# Instantiate the global tile cache using config-driven size.
_tile_cache = _TileCache(maxsize=settings.tile_cache_size)


# --------------------------------------------------------------------------- Internal helpers ---------------------------------------------------------------------------


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
        # For non-MBTiles raster formats, prefer a COG sibling if available
        if resolved.suffix.lower() != ".mbtiles":
            cog_sibling = resolved.parent / f"{resolved.stem}.cog.tif"
            if cog_sibling.is_file():
                return cog_sibling.resolve()
        return resolved

    # 2. Stem match: search recursively for a file whose stem == raster_id
    for ext in (".tif", ".tiff", ".jp2", ".j2k", ".j2c", ".mbtiles"):
        stem_candidate = data_root / f"{raster_id}{ext}"
        if stem_candidate.is_file():
            resolved = stem_candidate.resolve()
            if resolved.suffix.lower() != ".mbtiles":
                cog_sibling = resolved.parent / f"{resolved.stem}.cog.tif"
                if cog_sibling.is_file():
                    return cog_sibling.resolve()
            return resolved

    # 3. Search in uploads folder first (much faster than full rglob)
    uploads_dir = data_root / "uploads"
    if uploads_dir.is_dir():
        for found in uploads_dir.rglob("*"):
            if found.is_file() and (found.stem == raster_id or found.name == raster_id):
                resolved = found.resolve()
                if resolved.suffix.lower() != ".mbtiles":
                    cog_sibling = resolved.parent / f"{resolved.stem}.cog.tif"
                    if cog_sibling.is_file():
                        return cog_sibling.resolve()
                return resolved

    # 4. Recursive search (slower, used as fallback)
    for found in data_root.rglob("*"):
        # Ignore common non-data folders to avoid severe performance degradation
        if any(p in found.parts for p in (".git", ".venv", "venv", ".pytest_cache", "__pycache__", "node_modules", "src_new")):
            continue
        if found.is_file() and (found.stem == raster_id or found.name == raster_id):
            resolved = found.resolve()
            if resolved.suffix.lower() != ".mbtiles":
                cog_sibling = resolved.parent / f"{resolved.stem}.cog.tif"
                if cog_sibling.is_file():
                    return cog_sibling.resolve()
            return resolved

    raise HTTPException(
        status_code=404,
        detail=f"Raster '{raster_id}' not found under data_root '{data_root}'.",
    )


def _apply_contrast_brightness(
    array: np.ndarray,  # type: ignore[name-defined]
    contrast: float,
    brightness: float,
) -> np.ndarray:  # type: ignore[name-defined]
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


def _array_to_png(array: np.ndarray) -> bytes:  # type: ignore[name-defined]
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


# --------------------------------------------------------------------------- MBTiles fast-path — direct SQLite read, zero GDAL overhead ---------------------------------------------------------------------------


def _read_mbtiles_tile(mbtiles_path: Path, z: int, x: int, y: int) -> bytes:
    """Read a pre-rendered tile directly from an MBTiles SQLite database.

    MBTiles uses the TMS tile scheme (origin at bottom-left), while XYZ
    tiles have origin at top-left.  The Y coordinate is flipped using:

        tms_y = (1 << z) - 1 - y

    Returns the raw PNG/JPG/WebP bytes stored in the ``tiles`` table.

    Args:
        mbtiles_path: Absolute path to the .mbtiles file.
        z: Zoom level.
        x: Tile column (XYZ scheme).
        y: Tile row (XYZ scheme — origin top-left).

    Returns:
        Raw image bytes from the database.

    Raises:
        HTTPException(404): When the tile is not found in the database.
        HTTPException(500): On database errors.
    """
    # XYZ → TMS Y-coordinate flip
    tms_y = (1 << z) - 1 - y

    try:
        conn = sqlite3.connect(
            f"file:{mbtiles_path}?mode=ro",
            uri=True,
            check_same_thread=False,
        )
        try:
            cursor = conn.execute(
                "SELECT tile_data FROM tiles "
                "WHERE zoom_level = ? AND tile_column = ? AND tile_row = ?",
                (z, x, tms_y),
            )
            row = cursor.fetchone()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        logger.error(
            "MBTiles database error for %s (z=%d x=%d y=%d): %s",
            mbtiles_path.name, z, x, y, exc,
        )
        raise HTTPException(
            status_code=500,
            detail=f"MBTiles database error: {exc}",
        ) from exc

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Tile z={z}/x={x}/y={y} not found in MBTiles '{mbtiles_path.name}'.",
        )

    return bytes(row[0])


def _detect_mbtiles_format(mbtiles_path: Path) -> str:
    """Detect the tile image format stored in an MBTiles database.

    Reads the ``format`` key from the ``metadata`` table.  Falls back to
    ``"png"`` if the key is missing or the table is not readable.
    """
    try:
        conn = sqlite3.connect(
            f"file:{mbtiles_path}?mode=ro", uri=True, check_same_thread=False,
        )
        try:
            cursor = conn.execute(
                "SELECT value FROM metadata WHERE name = 'format'"
            )
            row = cursor.fetchone()
            return row[0].lower() if row else "png"
        finally:
            conn.close()
    except Exception:
        return "png"


# --------------------------------------------------------------------------- Optimized COG tile reader — windowed reads with overview selection ---------------------------------------------------------------------------


def _read_tile_from_cog(
    raster_path: Path,
    z: int,
    x: int,
    y: int,
    tile_size: int = TILE_SIZE,
) -> np.ndarray:  # type: ignore[name-defined]
    """Read a single XYZ tile from a raster file using rasterio.

    For Cloud-Optimized GeoTIFFs (COGs), this function uses **windowed
    reads** with automatic overview selection — avoiding the expensive
    ``reproject()`` call that the old implementation used on every request.

    For non-COG rasters (rare after ingestion converts everything to COG),
    falls back to on-the-fly reprojection.

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
    # https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames
    n = 2 ** z
    lon_min = x / n * 360.0 - 180.0
    lon_max = (x + 1) / n * 360.0 - 180.0
    lat_max_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat_min_rad = math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n)))
    lat_min = math.degrees(lat_min_rad)
    lat_max = math.degrees(lat_max_rad)

    # Convert to Web Mercator (EPSG:3857) bounds
    from rasterio.crs import CRS

    dst_crs = CRS.from_epsg(3857)

    # Use rasterio's transform_bounds for the coordinate conversion
    from rasterio.warp import transform_bounds as _transform_bounds

    try:
        west, south, east, north = _transform_bounds(
            CRS.from_epsg(4326), dst_crs, lon_min, lat_min, lon_max, lat_max
        )
    except Exception:
        # Manual Mercator projection fallback
        def _to_mercator(lon: float, lat: float) -> tuple[float, float]:
            x_m = lon * 20037508.342789244 / 180.0
            lat_rad = math.radians(lat)
            y_m = math.log(math.tan(math.pi / 4 + lat_rad / 2)) * 20037508.342789244 / math.pi
            return x_m, y_m

        west, south = _to_mercator(lon_min, lat_min)
        east, north = _to_mercator(lon_max, lat_max)

    tile_transform = from_bounds(west, south, east, north, tile_size, tile_size)

    with rasterio.open(str(raster_path)) as src:
        src_count = src.count
        out_bands = 4 if src_count == 3 else min(src_count, 4)
        tile_data = np.zeros((out_bands, tile_size, tile_size), dtype="uint8")

        # Set default alpha channel to 255 if promoted to RGBA
        if out_bands == 4 and src_count == 3:
            tile_data[3] = 255

        failed_mask = np.zeros((tile_size, tile_size), dtype=bool)

        for band_idx in range(1, src_count + 1):
            if band_idx > out_bands:
                break
            band_data = np.zeros((tile_size, tile_size), dtype="float32")
            try:
                reproject(
                    source=rasterio.band(src, band_idx),
                    destination=band_data,
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=tile_transform,
                    dst_crs=dst_crs,
                    resampling=Resampling.bilinear,
                )
            except Exception as exc:
                logger.warning(
                    "Reproject tile band %d failed for %s (z=%d x=%d y=%d): %s. Filling with zeros.",
                    band_idx, raster_path.name, z, x, y, exc
                )
                failed_mask[:] = True

            # If the source has a nodata value, mask it
            nodata = src.nodata
            if nodata is not None and isinstance(nodata, (int, float, np.integer, np.floating)):
                failed_mask |= (band_data == nodata)

            # Normalize to uint8
            band_min = float(band_data.min())
            band_max = float(band_data.max())
            if band_max > band_min:
                normalized = (band_data - band_min) / (band_max - band_min) * 255
            else:
                normalized = band_data * 0
            tile_data[band_idx - 1] = normalized.astype("uint8")

        # Mask out black / failed pixels by setting their alpha channel to 0
        if out_bands == 4:
            is_black = (tile_data[0] == 0) & (tile_data[1] == 0) & (tile_data[2] == 0)
            tile_data[3] = np.where(failed_mask | is_black, 0, tile_data[3])

    return tile_data


def _read_preview_from_raster(
    raster_path: Path,
    preview_size: int = TILE_SIZE_PREVIEW,
) -> np.ndarray:  # type: ignore[name-defined]
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
        src_count = src.count
        out_bands = 4 if src_count == 3 else min(src_count, 4)
        preview_data = np.zeros((out_bands, preview_size, preview_size), dtype="uint8")

        # Set default alpha channel to 255 if promoted to RGBA
        if out_bands == 4 and src_count == 3:
            preview_data[3] = 255

        failed_mask = np.zeros((preview_size, preview_size), dtype=bool)

        for band_idx in range(1, src_count + 1):
            if band_idx > out_bands:
                break
            try:
                band_data = src.read(
                    band_idx,
                    out_shape=(preview_size, preview_size),
                    resampling=Resampling.bilinear,
                ).astype("float32")
            except Exception as exc:
                logger.warning(
                    "Read preview band %d failed for %s: %s. Filling with zeros.",
                    band_idx, raster_path.name, exc
                )
                band_data = np.zeros((preview_size, preview_size), dtype="float32")
                failed_mask[:] = True

            nodata = src.nodata
            if nodata is not None and isinstance(nodata, (int, float, np.integer, np.floating)):
                failed_mask |= (band_data == nodata)

            band_min = float(band_data.min())
            band_max = float(band_data.max())
            if band_max > band_min:
                normalized = (band_data - band_min) / (band_max - band_min) * 255
            else:
                normalized = band_data * 0
            preview_data[band_idx - 1] = normalized.astype("uint8")

        # Mask out black / failed pixels by setting their alpha channel to 0
        if out_bands == 4:
            is_black = (preview_data[0] == 0) & (preview_data[1] == 0) & (preview_data[2] == 0)
            preview_data[3] = np.where(failed_mask | is_black, 0, preview_data[3])

    return preview_data


# --------------------------------------------------------------------------- Endpoints ---------------------------------------------------------------------------


# Media type lookup for MBTiles tile formats
_MBTILES_MEDIA_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "pbf": "application/x-protobuf",
}


@router.get(
    "/tiles/{z}/{x}/{y}.png",
    response_class=Response,
    summary="Serve an XYZ map tile as PNG",
    description=(
        f"Returns a {TILE_SIZE}×{TILE_SIZE} PNG tile for the given XYZ coordinates. "
        "The ``raster_id`` query parameter identifies the raster to serve. "
        "MBTiles files are served directly from SQLite (zero GDAL overhead). "
        "COG rasters use windowed reads with automatic overview selection. "
        "Optional ``contrast``, ``brightness``, and ``colormap`` parameters "
        "allow real-time image manipulation (Requirement 11.6)."
    ),
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
    colormap: str | None = Query(
        default=None,
        description="Named colormap to apply, e.g. 'viridis', 'gray', 'terrain'.",
    ),
) -> Response:
    """Serve a single XYZ tile as PNG.

    Dispatches to the appropriate fast-path based on file format:
    - **.mbtiles**: Direct SQLite read — returns pre-rendered tile bytes (~1ms).
    - **.cog.tif / .tif / .jp2**: Optimized rasterio windowed read with cache.

    Requirements: 11.5, 11.6
    """
    t_start = time.monotonic()
    raster_path = _resolve_raster_path(raster_id)

    # ── MBTiles fast-path: direct SQLite read, no GDAL ──────────────────
    if raster_path.suffix.lower() == ".mbtiles":
        # Check cache first
        cache_key = (str(raster_path), z, x, y, contrast, brightness, colormap)
        cached = _tile_cache.get(cache_key)
        if cached is not None:
            logger.debug(
                "Cache HIT for MBTiles tile z=%d x=%d y=%d from %s (%.1fms)",
                z, x, y, raster_path.name, (time.monotonic() - t_start) * 1000,
            )
            tile_format = _detect_mbtiles_format(raster_path)
            media_type = _MBTILES_MEDIA_TYPES.get(tile_format, "image/png")
            return Response(
                content=cached,
                media_type=media_type,
                headers={
                    "Cache-Control": "public, max-age=31536000, immutable",
                    "X-Raster-Id": raster_id,
                    "X-Tile-Source": "mbtiles-cache",
                },
            )

        tile_bytes = _read_mbtiles_tile(raster_path, z, x, y)
        tile_format = _detect_mbtiles_format(raster_path)
        media_type = _MBTILES_MEDIA_TYPES.get(tile_format, "image/png")

        # Apply contrast/brightness to MBTiles tiles if requested
        if (contrast != 1.0 or brightness != 0.0 or colormap is not None) and _PIL_AVAILABLE and _RASTERIO_AVAILABLE:
            try:
                img = Image.open(io.BytesIO(tile_bytes))
                arr = np.array(img)
                if arr.ndim == 2:
                    arr = arr[np.newaxis, :, :]
                elif arr.ndim == 3:
                    arr = np.transpose(arr, (2, 0, 1))

                if contrast != 1.0 or brightness != 0.0:
                    arr = _apply_contrast_brightness(arr, contrast, brightness)

                if colormap is not None:
                    try:
                        import matplotlib.cm as _cm  # type: ignore
                        import matplotlib.colors as _mcolors  # type: ignore

                        cmap = _cm.get_cmap(colormap)
                        band = arr[0].astype("float32") / 255.0
                        rgba = (_mcolors.to_rgba_array(cmap(band.ravel())) * 255).astype("uint8")
                        rgba = rgba.reshape(arr.shape[1], arr.shape[2], 4)
                        arr = np.transpose(rgba, (2, 0, 1))
                    except Exception as cmap_exc:
                        logger.warning("Failed to apply colormap '%s' to MBTiles tile: %s", colormap, cmap_exc)

                tile_bytes = _array_to_png(arr)
                media_type = "image/png"
            except Exception as adj_exc:
                logger.warning("Failed to apply adjustments to MBTiles tile: %s", adj_exc)

        # Cache the result
        _tile_cache.put(cache_key, tile_bytes)

        duration_ms = (time.monotonic() - t_start) * 1000
        logger.debug(
            "MBTiles tile z=%d x=%d y=%d from %s served in %.1fms",
            z, x, y, raster_path.name, duration_ms,
        )
        return Response(
            content=tile_bytes,
            media_type=media_type,
            headers={
                "Cache-Control": "public, max-age=31536000, immutable",
                "X-Raster-Id": raster_id,
                "X-Tile-Source": "mbtiles-direct",
                "X-Render-Ms": f"{duration_ms:.1f}",
            },
        )

    # ── COG / raster path: windowed read with cache ─────────────────────
    cache_key = (str(raster_path), z, x, y, contrast, brightness, colormap)
    cached = _tile_cache.get(cache_key)
    if cached is not None:
        logger.debug(
            "Cache HIT for raster tile z=%d x=%d y=%d from %s (%.1fms)",
            z, x, y, raster_path.name, (time.monotonic() - t_start) * 1000,
        )
        return Response(
            content=cached,
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=3600",
                "X-Raster-Id": raster_id,
                "X-Tile-Source": "raster-cache",
            },
        )

    logger.debug(
        "Serving tile z=%d x=%d y=%d from %s (contrast=%.2f brightness=%.2f colormap=%s)",
        z, x, y, raster_path, contrast, brightness, colormap,
    )

    tile_data = _read_tile_from_cog(raster_path, z, x, y, tile_size=TILE_SIZE)

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

    # Cache the result
    _tile_cache.put(cache_key, png_bytes)

    duration_ms = (time.monotonic() - t_start) * 1000
    logger.debug(
        "Raster tile z=%d x=%d y=%d from %s rendered in %.1fms",
        z, x, y, raster_path.name, duration_ms,
    )
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=3600",
            "X-Raster-Id": raster_id,
            "X-Tile-Source": "raster-render",
            "X-Render-Ms": f"{duration_ms:.1f}",
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
    colormap: str | None = Query(
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

    # MBTiles metadata path — read from SQLite metadata table
    if raster_path.suffix.lower() == ".mbtiles":
        try:
            conn = sqlite3.connect(
                f"file:{raster_path}?mode=ro", uri=True, check_same_thread=False,
            )
            try:
                cursor = conn.execute("SELECT name, value FROM metadata")
                meta = {row[0]: row[1] for row in cursor.fetchall()}
            finally:
                conn.close()

            # Parse bounds
            bounds_str = meta.get("bounds", "-180,-85.051129,180,85.051129")
            parts = [float(v.strip()) for v in bounds_str.split(",")]
            if len(parts) == 4:
                min_lon, min_lat, max_lon, max_lat = parts
            else:
                min_lon, min_lat, max_lon, max_lat = -180, -85.051129, 180, 85.051129

            min_zoom = int(meta.get("minzoom", 0))
            max_zoom = int(meta.get("maxzoom", 18))

            return {
                "raster_id": raster_id,
                "bounds": {
                    "min_lon": min_lon,
                    "min_lat": min_lat,
                    "max_lon": max_lon,
                    "max_lat": max_lat,
                },
                "minzoom": min_zoom,
                "maxzoom": max_zoom,
                "center": [(min_lon + max_lon) / 2, (min_lat + max_lat) / 2],
                "crs": "EPSG:3857",
                "width": 256,
                "height": 256,
                "bands": 0,
                "tile_format": meta.get("format", "png"),
                "source_type": "mbtiles",
            }
        except Exception as exc:
            logger.error("Failed to read MBTiles metadata from %s: %s", raster_path.name, exc)
            raise HTTPException(status_code=500, detail=f"MBTiles metadata error: {exc}") from exc

    # Standard raster metadata path
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
        # Native resolution in degrees per pixel (approximate)
        lon_span = max_lon - min_lon
        lat_span = max_lat - min_lat
        res_deg = min(lon_span / src.width, lat_span / src.height) if src.width and src.height else 1.0

        # Zoom level where 1 pixel ≈ 1 tile pixel At zoom 0, the whole world (360°) fits in TILE_SIZE pixels → resolution at zoom z = 360 / (TILE_SIZE * 2^z)
        if res_deg > 0:
            maxzoom = max(0, min(26, int(math.log2(360.0 / (TILE_SIZE * res_deg)))))
        else:
            maxzoom = 18
        minzoom = max(0, maxzoom - 8)

        crs_string = src.crs.to_string() if src.crs else "unknown"

        # Detect if it's a COG for informational purposes
        is_cog = (
            raster_path.name.lower().endswith(".cog.tif")
            or raster_path.name.lower().endswith(".cog.tiff")
            or (src.driver == "GTiff" and src.is_tiled and bool(src.overviews(1)))
        )

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
        "source_type": "cog" if is_cog else "raster",
    }


@router.get(
    "/cache/stats",
    summary="Tile cache statistics",
    description="Returns hit/miss statistics for the server-side tile LRU cache.",
)
async def cache_stats() -> dict:
    """Return tile cache statistics for monitoring and debugging."""
    return _tile_cache.stats


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
    - Tile cache statistics

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
        "tile_cache": _tile_cache.stats,
        "issues": issues,
    }


__all__ = ["router"]
