"""
rust_accelerators — PyO3 Rust extension with pure-Python fallbacks.

Attempts to import the compiled Rust extension module (.so on Linux/macOS,
.pyd on Windows).  If the compiled module is not present (e.g. on a fresh
checkout before running ``scripts/build_rust.sh``), functional pure-Python
implementations are used instead and a performance warning is logged.

Public API
----------
rasterize_vectors(geometries, burn_value, width, height, transform) -> list[float]
    Rasterize GeoJSON-like vector geometries onto a pixel grid.

transform_coordinates(coordinates, source_crs, target_crs) -> list[tuple[float, float]]
    Batch-transform (x, y) coordinate pairs between two CRS.
"""
from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # type stubs only — no runtime imports needed here

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- Attempt to load the compiled Rust extension ---------------------------------------------------------------------------
_RUST_AVAILABLE = False

try:
    from .rust_accelerators import (  # type: ignore[import]
        rasterize_vectors,
        transform_coordinates,
    )
    _RUST_AVAILABLE = True
    logger.debug(
        "Rust accelerators loaded successfully (compiled extension found)."
    )
except ImportError:
    logger.warning(
        "Rust accelerators not available — compiled .so/.pyd not found. "
        "Falling back to pure-Python implementations. "
        "Performance may be significantly lower for large datasets. "
        "Run 'scripts/build_rust.sh' to compile the Rust extension."
    )

    # ----------------------------------------------------------------------- Pure-Python fallback: rasterize_vectors -----------------------------------------------------------------------
    def rasterize_vectors(  # type: ignore[misc]
        geometries: list,
        burn_value: float,
        width: int,
        height: int,
        transform: list[float],
    ) -> list[float]:
        """Rasterize GeoJSON-like vector geometries onto a pixel grid.

        Pure-Python fallback used when the Rust extension is not compiled.
        Delegates to ``rasterio.features.rasterize`` when rasterio is
        available; otherwise performs a simple bounding-box approximation.

        Parameters
        ----------
        geometries:
            List of GeoJSON geometry dicts, e.g.
            ``[{"type": "Polygon", "coordinates": [[[lon, lat], ...]]}]``.
        burn_value:
            Scalar pixel value written where geometries overlap the grid.
        width:
            Output raster width in pixels.
        height:
            Output raster height in pixels.
        transform:
            6-element GDAL GeoTransform list:
            ``[x_min, x_pixel_size, 0, y_max, 0, -y_pixel_size]``.

        Returns
        -------
        list[float]
            Flat row-major pixel buffer of length ``width * height``.
            Pixels not covered by any geometry are ``0.0``.
        """
        if width <= 0 or height <= 0:
            raise ValueError(
                "rasterize_vectors: width and height must both be > 0"
            )
        if len(transform) != 6:
            raise ValueError(
                "rasterize_vectors: transform must be a 6-element GDAL GeoTransform list"
            )

        # Try rasterio first — it is almost always available in the conda env
        try:
            import rasterio.features
            import rasterio.transform as rio_transform

            affine = rio_transform.Affine(
                transform[1],  # x_pixel_size
                transform[2],  # row rotation (usually 0)
                transform[0],  # x_min
                transform[4],  # column rotation (usually 0)
                transform[5],  # -y_pixel_size
                transform[3],  # y_max
            )
            result = rasterio.features.rasterize(
                [(geom, burn_value) for geom in geometries],
                out_shape=(height, width),
                transform=affine,
                fill=0.0,
                dtype="float64",
            )
            return result.flatten().tolist()

        except ImportError:
            pass  # rasterio not available — use bounding-box approximation below

        # Minimal bounding-box approximation: mark one pixel per geometry
        x_min = transform[0]
        x_res = transform[1]
        y_max = transform[3]
        y_res = -transform[5]  # positive pixel height

        buffer = [0.0] * (width * height)
        for geom in geometries:
            coords = _extract_all_coords(geom)
            if not coords:
                continue
            xs = [c[0] for c in coords]
            ys = [c[1] for c in coords]
            # Compute pixel extent of the geometry bounding box
            col_min = max(0, int((min(xs) - x_min) / x_res))
            col_max = min(width - 1, int((max(xs) - x_min) / x_res))
            row_min = max(0, int((y_max - max(ys)) / y_res))
            row_max = min(height - 1, int((y_max - min(ys)) / y_res))
            for row in range(row_min, row_max + 1):
                for col in range(col_min, col_max + 1):
                    buffer[row * width + col] = burn_value

        return buffer

    # ----------------------------------------------------------------------- Pure-Python fallback: transform_coordinates -----------------------------------------------------------------------
    def transform_coordinates(  # type: ignore[misc]
        coordinates: list[tuple[float, float]],
        source_crs: str,
        target_crs: str,
    ) -> list[tuple[float, float]]:
        """Batch-transform (x, y) coordinate pairs between two CRS.

        Pure-Python fallback used when the Rust extension is not compiled.
        Delegates to ``pyproj.Transformer`` when pyproj is available;
        otherwise applies the spherical Mercator formula for the common
        EPSG:4326 → EPSG:3857 case and returns a pass-through for all others.

        Parameters
        ----------
        coordinates:
            List of ``(x, y)`` tuples in the source CRS.
            For geographic CRS (e.g. EPSG:4326) x = longitude, y = latitude.
        source_crs:
            Source CRS as an EPSG authority string, e.g. ``"EPSG:4326"``.
        target_crs:
            Target CRS as an EPSG authority string, e.g. ``"EPSG:3857"``.

        Returns
        -------
        list[tuple[float, float]]
            Transformed ``(x, y)`` pairs in the target CRS.
            Same length and order as the input list.
        """
        if not source_crs or not source_crs.strip():
            raise ValueError(
                "transform_coordinates: source_crs must not be empty"
            )
        if not target_crs or not target_crs.strip():
            raise ValueError(
                "transform_coordinates: target_crs must not be empty"
            )

        # Try pyproj first — it is almost always available in the conda env
        try:
            from pyproj import Transformer

            transformer = Transformer.from_crs(
                source_crs, target_crs, always_xy=True
            )
            xs = [c[0] for c in coordinates]
            ys = [c[1] for c in coordinates]
            tx, ty = transformer.transform(xs, ys)
            return list(zip(tx, ty))

        except ImportError:
            pass  # pyproj not available — use built-in approximation below

        # Built-in spherical Mercator approximation for EPSG:4326 → EPSG:3857
        is_4326_to_3857 = (
            ("4326" in source_crs or "WGS84" in source_crs.upper())
            and ("3857" in target_crs or "900913" in target_crs)
        )

        if is_4326_to_3857:
            earth_radius = 6_378_137.0  # WGS-84 semi-major axis in metres
            result = []
            for lon, lat in coordinates:
                easting = math.radians(lon) * earth_radius
                northing = math.log(
                    math.tan(math.pi / 4 + math.radians(lat) / 2)
                ) * earth_radius
                result.append((easting, northing))
            return result

        # Pass-through for all other CRS pairs (no conversion available)
        logger.warning(
            "transform_coordinates: pyproj not available and no built-in "
            "formula for %s → %s. Returning coordinates unchanged.",
            source_crs,
            target_crs,
        )
        return list(coordinates)


# --------------------------------------------------------------------------- Internal helper (used by the pure-Python rasterize fallback only) ---------------------------------------------------------------------------

def _extract_all_coords(geometry: dict) -> list[tuple[float, float]]:
    """Recursively extract all (x, y) coordinate pairs from a GeoJSON geometry."""
    coords: list[tuple[float, float]] = []
    geom_type = geometry.get("type", "")
    raw = geometry.get("coordinates", [])

    if geom_type == "Point":
        if len(raw) >= 2:
            coords.append((raw[0], raw[1]))
    elif geom_type in ("LineString", "MultiPoint"):
        for pt in raw:
            if len(pt) >= 2:
                coords.append((pt[0], pt[1]))
    elif geom_type in ("Polygon", "MultiLineString"):
        for ring in raw:
            for pt in ring:
                if len(pt) >= 2:
                    coords.append((pt[0], pt[1]))
    elif geom_type == "MultiPolygon":
        for polygon in raw:
            for ring in polygon:
                for pt in ring:
                    if len(pt) >= 2:
                        coords.append((pt[0], pt[1]))
    elif geom_type == "GeometryCollection":
        for sub_geom in geometry.get("geometries", []):
            coords.extend(_extract_all_coords(sub_geom))

    return coords


# --------------------------------------------------------------------------- Public API ---------------------------------------------------------------------------

__all__ = [
    "rasterize_vectors",
    "transform_coordinates",
    "_RUST_AVAILABLE",
]
