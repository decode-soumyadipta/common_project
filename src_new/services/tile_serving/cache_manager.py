"""Tile cache manager for the Tile Service.

Implements an in-memory LRU (Least Recently Used) cache for rendered tile
bytes.  The maximum number of cached tiles is controlled by the
``TILE_CACHE_SIZE`` environment variable (via ``shared.config.settings``).

Design notes:
- Uses ``functools.lru_cache`` semantics via a manual ``OrderedDict``-based
  LRU so that the cache is a plain object (not a decorated function), making
  it easy to inject, inspect, and invalidate at runtime.
- Thread-safe: all mutations are protected by a ``threading.Lock``.
- Cache keys are ``(raster_id, z, x, y, contrast, brightness, colormap)``
  tuples so that different rendering parameters produce separate entries.
- Invalidation helpers allow clearing all tiles for a given raster_id
  (e.g. after the underlying file is updated) or flushing the entire cache.

Requirements: 11.3
"""
from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from typing import Optional, Tuple

from src_new.shared.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type alias for cache keys
# ---------------------------------------------------------------------------

# (raster_id, z, x, y, contrast, brightness, colormap)
CacheKey = Tuple[str, int, int, int, float, float, Optional[str]]


# ---------------------------------------------------------------------------
# LRU Cache implementation
# ---------------------------------------------------------------------------


class TileCacheManager:
    """Thread-safe LRU cache for rendered tile bytes.

    The cache stores raw PNG bytes keyed by tile coordinates and rendering
    parameters.  When the cache reaches ``max_size`` entries the least
    recently used entry is evicted automatically.

    Args:
        max_size: Maximum number of tiles to keep in memory.  Defaults to
                  ``settings.tile_cache_size`` (from ``TILE_CACHE_SIZE`` env
                  var, default 512).

    Example::

        cache = TileCacheManager()

        # Store a rendered tile
        cache.put("my_raster", z=10, x=512, y=300, png_bytes=b"...")

        # Retrieve it later
        data = cache.get("my_raster", z=10, x=512, y=300)
        if data is None:
            data = render_tile(...)
            cache.put("my_raster", z=10, x=512, y=300, png_bytes=data)

        # Invalidate all tiles for a raster (e.g. after file update)
        cache.invalidate_raster("my_raster")

        # Flush everything
        cache.clear()
    """

    def __init__(self, max_size: Optional[int] = None) -> None:
        self._max_size: int = max_size if max_size is not None else settings.tile_cache_size
        if self._max_size <= 0:
            logger.warning(
                "TILE_CACHE_SIZE is %d (≤ 0); caching is effectively disabled.",
                self._max_size,
            )
        self._cache: OrderedDict[CacheKey, bytes] = OrderedDict()
        self._lock: threading.Lock = threading.Lock()
        self._hits: int = 0
        self._misses: int = 0
        logger.info(
            "TileCacheManager initialised with max_size=%d (TILE_CACHE_SIZE=%d).",
            self._max_size,
            settings.tile_cache_size,
        )

    # ------------------------------------------------------------------
    # Core get / put
    # ------------------------------------------------------------------

    def _make_key(
        self,
        raster_id: str,
        z: int,
        x: int,
        y: int,
        contrast: float = 1.0,
        brightness: float = 0.0,
        colormap: Optional[str] = None,
    ) -> CacheKey:
        """Build a hashable cache key from tile parameters."""
        return (raster_id, z, x, y, contrast, brightness, colormap)

    def get(
        self,
        raster_id: str,
        z: int,
        x: int,
        y: int,
        contrast: float = 1.0,
        brightness: float = 0.0,
        colormap: Optional[str] = None,
    ) -> Optional[bytes]:
        """Return cached PNG bytes for the given tile, or ``None`` on a miss.

        On a cache hit the entry is moved to the end of the LRU order
        (most recently used).

        Args:
            raster_id: Raster identifier.
            z: Zoom level.
            x: Tile column.
            y: Tile row.
            contrast: Contrast multiplier used when rendering (default 1.0).
            brightness: Brightness offset used when rendering (default 0.0).
            colormap: Colormap name used when rendering (default None).

        Returns:
            PNG bytes if the tile is cached, ``None`` otherwise.
        """
        if self._max_size <= 0:
            return None

        key = self._make_key(raster_id, z, x, y, contrast, brightness, colormap)
        with self._lock:
            if key in self._cache:
                # Move to end (most recently used)
                self._cache.move_to_end(key)
                self._hits += 1
                logger.debug(
                    "Cache HIT  raster=%s z=%d x=%d y=%d (hits=%d misses=%d)",
                    raster_id, z, x, y, self._hits, self._misses,
                )
                return self._cache[key]

            self._misses += 1
            logger.debug(
                "Cache MISS raster=%s z=%d x=%d y=%d (hits=%d misses=%d)",
                raster_id, z, x, y, self._hits, self._misses,
            )
            return None

    def put(
        self,
        raster_id: str,
        z: int,
        x: int,
        y: int,
        png_bytes: bytes,
        contrast: float = 1.0,
        brightness: float = 0.0,
        colormap: Optional[str] = None,
    ) -> None:
        """Store PNG bytes in the cache, evicting the LRU entry if full.

        If ``max_size`` is 0 or negative the call is a no-op.

        Args:
            raster_id: Raster identifier.
            z: Zoom level.
            x: Tile column.
            y: Tile row.
            png_bytes: Rendered PNG bytes to cache.
            contrast: Contrast multiplier used when rendering (default 1.0).
            brightness: Brightness offset used when rendering (default 0.0).
            colormap: Colormap name used when rendering (default None).
        """
        if self._max_size <= 0:
            return

        key = self._make_key(raster_id, z, x, y, contrast, brightness, colormap)
        with self._lock:
            if key in self._cache:
                # Update existing entry and move to end
                self._cache.move_to_end(key)
                self._cache[key] = png_bytes
                return

            # Evict LRU entry if at capacity
            while len(self._cache) >= self._max_size:
                evicted_key, _ = self._cache.popitem(last=False)
                logger.debug(
                    "Cache evicted LRU entry: raster=%s z=%d x=%d y=%d",
                    evicted_key[0], evicted_key[1], evicted_key[2], evicted_key[3],
                )

            self._cache[key] = png_bytes
            logger.debug(
                "Cache stored raster=%s z=%d x=%d y=%d (size=%d/%d)",
                raster_id, z, x, y, len(self._cache), self._max_size,
            )

    # ------------------------------------------------------------------
    # Invalidation
    # ------------------------------------------------------------------

    def invalidate_raster(self, raster_id: str) -> int:
        """Remove all cached tiles for a specific raster.

        Call this when the underlying raster file has been updated or deleted
        to prevent stale tiles from being served.

        Args:
            raster_id: Raster identifier whose tiles should be evicted.

        Returns:
            Number of cache entries removed.
        """
        with self._lock:
            keys_to_remove = [k for k in self._cache if k[0] == raster_id]
            for key in keys_to_remove:
                del self._cache[key]

        count = len(keys_to_remove)
        if count:
            logger.info(
                "Cache invalidated %d tile(s) for raster_id=%s.", count, raster_id
            )
        return count

    def clear(self) -> int:
        """Flush the entire cache.

        Returns:
            Number of cache entries removed.
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._hits = 0
            self._misses = 0

        logger.info("Cache flushed (%d entries removed).", count)
        return count

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def size(self) -> int:
        """Current number of entries in the cache."""
        with self._lock:
            return len(self._cache)

    @property
    def max_size(self) -> int:
        """Maximum number of entries the cache will hold."""
        return self._max_size

    @property
    def hits(self) -> int:
        """Total number of cache hits since creation or last ``clear()``."""
        return self._hits

    @property
    def misses(self) -> int:
        """Total number of cache misses since creation or last ``clear()``."""
        return self._misses

    @property
    def hit_rate(self) -> float:
        """Cache hit rate as a fraction in [0.0, 1.0].

        Returns 0.0 when no lookups have been performed yet.
        """
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def stats(self) -> dict:
        """Return a snapshot of cache statistics.

        Returns:
            Dictionary with keys: ``size``, ``max_size``, ``hits``,
            ``misses``, ``hit_rate``.
        """
        return {
            "size": self.size,
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self.hit_rate, 4),
        }

    def __repr__(self) -> str:
        return (
            f"TileCacheManager(size={self.size}/{self._max_size}, "
            f"hits={self._hits}, misses={self._misses})"
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

#: Global cache instance shared across the tile service.
#: Max size is read from ``settings.tile_cache_size`` (TILE_CACHE_SIZE env var).
tile_cache: TileCacheManager = TileCacheManager()

__all__ = ["TileCacheManager", "tile_cache", "CacheKey"]
