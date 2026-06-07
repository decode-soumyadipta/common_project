"""File validation and geometry utilities.

Adapted from src/platform_core/utils/geometry.py (which delegates to
src/core_shared/utils/geometry.py).

Provides:
- Bounds dataclass and WKT polygon parsing (geometry helpers from original)
- File-format validators for GeoTIFF, JPEG2000, and MBTiles
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src_new.shared.constants import SUPPORTED_FORMATS, MAX_UPLOAD_SIZE_DEFAULT

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- Geometry helpers (preserved from core_shared/utils/geometry.py) ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Bounds:
    """Axis-aligned bounding box in any coordinate system."""

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def centroid(self) -> tuple[float, float]:
        """Return the (x, y) centroid of the bounding box."""
        return ((self.min_x + self.max_x) / 2.0, (self.min_y + self.max_y) / 2.0)

    def to_wkt_polygon(self) -> str:
        """Serialize the bounding box as a WKT POLYGON string."""
        return (
            "POLYGON(("
            f"{self.min_x} {self.min_y},"
            f"{self.max_x} {self.min_y},"
            f"{self.max_x} {self.max_y},"
            f"{self.min_x} {self.max_y},"
            f"{self.min_x} {self.min_y}"
            "))"
        )

    def is_valid(self) -> bool:
        """Return True if the bounding box has positive area."""
        return self.max_x > self.min_x and self.max_y > self.min_y


def parse_bounds_wkt_polygon(wkt: str) -> Bounds:
    """Parse a WKT POLYGON string into a Bounds object.

    Handles POLYGON, POLYGONZ, POLYGONM variants and extra whitespace.

    Args:
        wkt: WKT polygon string, e.g. "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"

    Returns:
        Bounds with min/max x/y derived from the polygon vertices.
    """
    raw = wkt.upper().replace("POLYGON", "").replace("Z", "").replace("M", "")
    raw = raw.replace("(", "").replace(")", "").strip()

    points: list[tuple[float, float]] = []
    for token in raw.split(","):
        parts = token.strip().split()
        if len(parts) >= 2:
            try:
                points.append((float(parts[0]), float(parts[1])))
            except ValueError:
                logger.warning("Skipping unparseable WKT token: %r", token)

    if not points:
        logger.warning("No valid points found in WKT: %r — returning zero Bounds", wkt)
        return Bounds(0.0, 0.0, 0.0, 0.0)

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return Bounds(min(xs), min(ys), max(xs), max(ys))


# --------------------------------------------------------------------------- File-format validators ---------------------------------------------------------------------------

# Magic bytes for supported formats
_GEOTIFF_MAGIC_LE = b"\x49\x49\x2a\x00"  # Little-endian TIFF
_GEOTIFF_MAGIC_BE = b"\x4d\x4d\x00\x2a"  # Big-endian TIFF
_BIGTIFF_MAGIC_LE = b"\x49\x49\x2b\x00"  # BigTIFF little-endian
_BIGTIFF_MAGIC_BE = b"\x4d\x4d\x00\x2b"  # BigTIFF big-endian
_JPEG2000_MAGIC = b"\x00\x00\x00\x0c\x6a\x50\x20\x20"  # JP2 box signature
_JPEG2000_MAGIC_ALT = b"\xff\x4f\xff\x51"  # Raw J2K codestream
_MBTILES_MAGIC = b"SQLite format 3"  # SQLite header (MBTiles is SQLite)


class FileValidationError(ValueError):
    """Raised when a file fails format or size validation."""


def validate_file_exists(path: Path) -> None:
    """Raise FileNotFoundError if *path* does not exist or is not a file."""
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not path.is_file():
        raise FileValidationError(f"Path is not a regular file: {path}")


def validate_file_size(path: Path, max_bytes: Optional[int] = None) -> None:
    """Raise FileValidationError if the file exceeds *max_bytes*.

    Args:
        path: Path to the file.
        max_bytes: Maximum allowed size in bytes. Defaults to MAX_UPLOAD_SIZE_DEFAULT.
    """
    if max_bytes is None:
        max_bytes = MAX_UPLOAD_SIZE_DEFAULT
    size = os.path.getsize(path)
    if size > max_bytes:
        raise FileValidationError(
            f"File {path.name} is {size:,} bytes, exceeding the "
            f"{max_bytes:,}-byte limit."
        )


def validate_file_extension(path: Path) -> str:
    """Return the normalized extension and raise if it is not supported.

    Returns:
        Lowercase extension without the leading dot, e.g. "tif".

    Raises:
        FileValidationError: If the extension is not in SUPPORTED_FORMATS.
    """
    ext = path.suffix.lower().lstrip(".")
    # Normalize common aliases
    ext = {"tiff": "tif", "j2k": "jp2", "j2c": "jp2"}.get(ext, ext)
    if ext not in SUPPORTED_FORMATS:
        raise FileValidationError(
            f"Unsupported file format '.{ext}'. "
            f"Supported formats: {sorted(SUPPORTED_FORMATS)}"
        )
    return ext


def is_geotiff(path: Path) -> bool:
    """Return True if *path* has a TIFF magic header."""
    try:
        with open(path, "rb") as fh:
            magic = fh.read(4)
        return magic in (
            _GEOTIFF_MAGIC_LE,
            _GEOTIFF_MAGIC_BE,
            _BIGTIFF_MAGIC_LE,
            _BIGTIFF_MAGIC_BE,
        )
    except OSError:
        return False


def is_jpeg2000(path: Path) -> bool:
    """Return True if *path* has a JPEG2000 magic header."""
    try:
        with open(path, "rb") as fh:
            magic = fh.read(8)
        return magic[:8] == _JPEG2000_MAGIC or magic[:4] == _JPEG2000_MAGIC_ALT
    except OSError:
        return False


def is_mbtiles(path: Path) -> bool:
    """Return True if *path* is an SQLite database (MBTiles format)."""
    try:
        with open(path, "rb") as fh:
            magic = fh.read(len(_MBTILES_MAGIC))
        return magic == _MBTILES_MAGIC
    except OSError:
        return False


def detect_format(path: Path) -> Optional[str]:
    """Detect the geospatial format of *path* by inspecting magic bytes.

    Returns:
        One of "tif", "jp2", "mbtiles", or None if unrecognized.
    """
    if is_geotiff(path):
        return "tif"
    if is_jpeg2000(path):
        return "jp2"
    if is_mbtiles(path):
        return "mbtiles"
    return None


def validate_geospatial_file(
    path: Path,
    max_bytes: Optional[int] = None,
) -> str:
    """Run all validation checks on a geospatial file.

    Checks existence, size, extension, and magic bytes.

    Args:
        path: Path to the file to validate.
        max_bytes: Optional size limit override.

    Returns:
        Detected format string ("tif", "jp2", or "mbtiles").

    Raises:
        FileNotFoundError: If the file does not exist.
        FileValidationError: If any validation check fails.
    """
    validate_file_exists(path)
    validate_file_size(path, max_bytes)
    validate_file_extension(path)

    detected = detect_format(path)
    if detected is None:
        raise FileValidationError(
            f"File {path.name} has an unrecognized binary format. "
            "Expected GeoTIFF, JPEG2000, or MBTiles."
        )
    logger.debug("Validated %s as format=%s", path, detected)
    return detected


__all__ = [
    "Bounds",
    "parse_bounds_wkt_polygon",
    "FileValidationError",
    "validate_file_exists",
    "validate_file_size",
    "validate_file_extension",
    "is_geotiff",
    "is_jpeg2000",
    "is_mbtiles",
    "detect_format",
    "validate_geospatial_file",
]
