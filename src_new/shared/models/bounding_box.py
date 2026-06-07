"""BoundingBox Pydantic model for geographic extents.

Used across all services to represent axis-aligned geographic bounding boxes
in WGS 84 (EPSG:4326) coordinates unless otherwise specified.

Requirement 12.1: Shared Pydantic data models.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class BoundingBox(BaseModel):
    """Axis-aligned geographic bounding box.

    Coordinates are in decimal degrees (WGS 84 / EPSG:4326) by default.
    The box must span a non-zero area (min values must be strictly less than max values).

    Example::

        bbox = BoundingBox(min_lon=72.0, min_lat=18.0, max_lon=73.0, max_lat=19.0)
    """

    min_lon: float = Field(
        ge=-180.0,
        le=180.0,
        description="Western boundary longitude in decimal degrees.",
    )
    min_lat: float = Field(
        ge=-90.0,
        le=90.0,
        description="Southern boundary latitude in decimal degrees.",
    )
    max_lon: float = Field(
        ge=-180.0,
        le=180.0,
        description="Eastern boundary longitude in decimal degrees.",
    )
    max_lat: float = Field(
        ge=-90.0,
        le=90.0,
        description="Northern boundary latitude in decimal degrees.",
    )

    @model_validator(mode="after")
    def _validate_non_zero_area(self) -> "BoundingBox":
        """Ensure the bounding box spans a non-zero area."""
        if self.min_lon >= self.max_lon:
            raise ValueError(
                f"min_lon ({self.min_lon}) must be strictly less than max_lon ({self.max_lon})."
            )
        if self.min_lat >= self.max_lat:
            raise ValueError(
                f"min_lat ({self.min_lat}) must be strictly less than max_lat ({self.max_lat})."
            )
        return self

    # ------------------------------------------------------------------ Convenience helpers ------------------------------------------------------------------

    def contains_point(self, lon: float, lat: float) -> bool:
        """Return True if the given point falls within (or on the edge of) this box."""
        return self.min_lon <= lon <= self.max_lon and self.min_lat <= lat <= self.max_lat

    def intersects(self, other: "BoundingBox") -> bool:
        """Return True if this box overlaps with *other* (touching edges count)."""
        return not (
            self.max_lon < other.min_lon
            or self.min_lon > other.max_lon
            or self.max_lat < other.min_lat
            or self.min_lat > other.max_lat
        )

    def to_wkt_polygon(self) -> str:
        """Return a WKT POLYGON string representing this bounding box."""
        coords = (
            f"{self.min_lon} {self.min_lat}, "
            f"{self.max_lon} {self.min_lat}, "
            f"{self.max_lon} {self.max_lat}, "
            f"{self.min_lon} {self.max_lat}, "
            f"{self.min_lon} {self.min_lat}"
        )
        return f"POLYGON(({coords}))"

    @classmethod
    def from_wsen(
        cls, west: float, south: float, east: float, north: float
    ) -> "BoundingBox":
        """Construct from west/south/east/north ordering (common in GIS tools)."""
        return cls(min_lon=west, min_lat=south, max_lon=east, max_lat=north)


__all__ = ["BoundingBox"]
