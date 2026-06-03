"""RasterMetadata Pydantic model.

Adapted from ``src/server_vm/server_backend/schemas.py`` and the internal
``platform_core.ingestion.services.metadata_models.RasterMetadata`` dataclass.

This is the canonical shared representation of a cataloged raster asset.
All services exchange raster information using this model rather than raw
database rows or service-specific DTOs.

Requirement 12.1: Shared Pydantic data models.
Requirement 12.4: All services import shared models rather than duplicating logic.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from src_new.shared.models.bounding_box import BoundingBox


class RasterKind(str, Enum):
    """Supported raster source categories.

    Mirrors ``platform_core.db.models.RasterKind`` so that shared models
    have no dependency on the database layer.
    """

    GEOTIFF = "geotiff"
    JPEG2000 = "jpeg2000"
    MBTILES = "mbtiles"
    DEM = "dem"
    UNKNOWN = "unknown"


class RasterMetadata(BaseModel):
    """Full metadata record for a cataloged raster asset.

    This model is returned by the Query Service and used by the Ingestion
    Service when inserting records into PostGIS.  It maps 1-to-1 with the
    ``raster_assets`` database table.

    Example::

        meta = RasterMetadata(
            raster_id="550e8400-e29b-41d4-a716-446655440000",
            file_path="/data/imagery/scene_001.tif",
            file_name="scene_001.tif",
            kind=RasterKind.GEOTIFF,
            crs="EPSG:4326",
            bbox=BoundingBox(min_lon=72.0, min_lat=18.0, max_lon=73.0, max_lat=19.0),
            resolution_x=0.00002,
            resolution_y=0.00002,
            width=50000,
            height=50000,
        )
    """

    raster_id: str = Field(
        description="Unique identifier (UUID) assigned at ingestion time.",
    )
    file_path: str = Field(
        min_length=1,
        description="Absolute path to the raster file on the server's file system.",
    )
    file_name: str = Field(
        min_length=1,
        description="Base file name (without directory path).",
    )
    kind: RasterKind = Field(
        default=RasterKind.UNKNOWN,
        description="Raster format / source category.",
    )
    crs: str = Field(
        description=(
            "Coordinate Reference System as an authority string, "
            "e.g. 'EPSG:4326' or 'EPSG:32644'."
        ),
    )
    bbox: BoundingBox = Field(
        description="Geographic bounding box of the raster in WGS 84 (EPSG:4326).",
    )
    resolution_x: float = Field(
        gt=0.0,
        description="Pixel width in the raster's native CRS units.",
    )
    resolution_y: float = Field(
        gt=0.0,
        description="Pixel height in the raster's native CRS units (always positive).",
    )
    width: int = Field(
        gt=0,
        description="Raster width in pixels.",
    )
    height: int = Field(
        gt=0,
        description="Raster height in pixels.",
    )
    tags: Optional[str] = Field(
        default="",
        description="Comma-separated user-supplied metadata tags.",
    )
    description: Optional[str] = Field(
        default="",
        description="Free-text description of the asset.",
    )
    upload_date: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp when the raster was ingested. None if not yet set.",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp of the last metadata update.",
    )


__all__ = ["RasterKind", "RasterMetadata"]
