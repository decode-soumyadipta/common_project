"""TileRequest Pydantic model.

Represents a request for a single map tile, including the tile coordinates,
the target raster, and optional image-manipulation parameters.

Requirement 12.1: Shared Pydantic data models.
Requirement 11.6: Tile Service supports contrast, brightness, colormap query params.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class TileRequest(BaseModel):
    """Parameters for a single XYZ tile request.

    Tile coordinates follow the standard slippy-map convention:
    - ``z``: zoom level (0 = whole world, higher = more detail)
    - ``x``: column index (0 = leftmost tile at zoom level z)
    - ``y``: row index (0 = topmost tile at zoom level z)

    Image manipulation parameters (``contrast``, ``brightness``, ``colormap``)
    are optional and default to neutral / no-op values.

    Example::

        req = TileRequest(z=10, x=512, y=384, raster_id="abc-123")
        req_styled = TileRequest(
            z=12, x=2048, y=1536,
            raster_id="abc-123",
            contrast=1.2,
            brightness=0.9,
            colormap="viridis",
        )
    """

    z: int = Field(
        ge=0,
        le=30,
        description="Zoom level (0–30). Higher values provide more detail.",
    )
    x: int = Field(
        ge=0,
        description="Tile column index at the given zoom level.",
    )
    y: int = Field(
        ge=0,
        description="Tile row index at the given zoom level.",
    )
    raster_id: str = Field(
        min_length=1,
        description="Unique identifier of the cataloged raster to render.",
    )
    contrast: float = Field(
        default=1.0,
        gt=0.0,
        description=(
            "Contrast multiplier applied to the rendered tile. "
            "1.0 = no change; >1.0 increases contrast; <1.0 decreases contrast."
        ),
    )
    brightness: float = Field(
        default=1.0,
        gt=0.0,
        description=(
            "Brightness multiplier applied to the rendered tile. "
            "1.0 = no change; >1.0 brightens; <1.0 darkens."
        ),
    )
    colormap: str | None = Field(
        default=None,
        description=(
            "Named colormap to apply (e.g. 'viridis', 'plasma', 'gray'). "
            "None means the raster's native color interpretation is used."
        ),
    )


__all__ = ["TileRequest"]
