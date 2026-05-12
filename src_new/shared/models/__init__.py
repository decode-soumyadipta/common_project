"""Shared Pydantic data models for the geospatial microservices platform.

All services and clients import models from this package rather than
defining their own — this ensures consistency across service boundaries.

Requirement 12.1: Shared Pydantic data models.
Requirement 12.4: All services import shared models rather than duplicating logic.
"""
from src_new.shared.models.bounding_box import BoundingBox
from src_new.shared.models.crs import CoordinateReferenceSystem
from src_new.shared.models.query_result import QueryResult
from src_new.shared.models.raster_metadata import RasterKind, RasterMetadata
from src_new.shared.models.tile_request import TileRequest

__all__ = [
    "BoundingBox",
    "CoordinateReferenceSystem",
    "QueryResult",
    "RasterKind",
    "RasterMetadata",
    "TileRequest",
]
