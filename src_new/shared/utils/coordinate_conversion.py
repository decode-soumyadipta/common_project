"""Coordinate reference system utilities.

Adapted from src/platform_core/utils/crs.py (which delegates to
src/core_shared/utils/crs.py).

Provides CRS normalization and coordinate transformation helpers used
across all services and clients.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- CRS string normalization ---------------------------------------------------------------------------


def normalize_crs(crs_value: str | None) -> str:
    """Normalize a CRS string to a canonical EPSG:XXXX form.

    Examples:
        >>> normalize_crs(None)
        'EPSG:4326'
        >>> normalize_crs("epsg:4326")
        'EPSG:4326'
        >>> normalize_crs("EPSG::3857")
        'EPSG:3857'
    """
    if not crs_value:
        return "EPSG:4326"
    return crs_value.upper().replace("::", ":")


# --------------------------------------------------------------------------- Coordinate transformation helpers ---------------------------------------------------------------------------


def reproject_point(
    x: float,
    y: float,
    src_crs: str,
    dst_crs: str,
) -> tuple[float, float]:
    """Reproject a single point from *src_crs* to *dst_crs*.

    Uses PyProj for the transformation. Both CRS strings are normalized
    before use.

    Args:
        x: X coordinate (longitude for geographic CRS).
        y: Y coordinate (latitude for geographic CRS).
        src_crs: Source CRS string (e.g. "EPSG:4326").
        dst_crs: Destination CRS string (e.g. "EPSG:3857").

    Returns:
        Tuple of (x, y) in the destination CRS.

    Raises:
        ImportError: If PyProj is not installed.
        pyproj.exceptions.CRSError: If either CRS string is invalid.
    """
    try:
        from pyproj import Transformer  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "PyProj is required for coordinate transformation. "
            "Install it with: conda install pyproj"
        ) from exc

    src = normalize_crs(src_crs)
    dst = normalize_crs(dst_crs)

    transformer = Transformer.from_crs(src, dst, always_xy=True)
    tx, ty = transformer.transform(x, y)
    logger.debug("Reprojected (%s, %s) from %s to %s → (%s, %s)", x, y, src, dst, tx, ty)
    return float(tx), float(ty)


def reproject_bbox(
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
    src_crs: str,
    dst_crs: str,
) -> tuple[float, float, float, float]:
    """Reproject a bounding box from *src_crs* to *dst_crs*.

    Reprojects all four corners and returns the axis-aligned envelope.

    Returns:
        Tuple of (min_x, min_y, max_x, max_y) in the destination CRS.
    """
    corners = [
        (min_x, min_y),
        (max_x, min_y),
        (max_x, max_y),
        (min_x, max_y),
    ]
    reprojected = [reproject_point(cx, cy, src_crs, dst_crs) for cx, cy in corners]
    xs = [p[0] for p in reprojected]
    ys = [p[1] for p in reprojected]
    return min(xs), min(ys), max(xs), max(ys)


__all__ = ["normalize_crs", "reproject_bbox", "reproject_point"]
