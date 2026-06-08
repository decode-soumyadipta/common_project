"""QueryResult Pydantic model.

Represents the response returned by the Query Service for spatial search
operations (point query, bounding-box query, etc.).

Requirement 12.1: Shared Pydantic data models.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from src_new.shared.models.raster_metadata import RasterMetadata


class QueryResult(BaseModel):
    """Result of a spatial query against the raster catalog.

    The ``count`` field must always equal ``len(rasters)``.  It is included
    as a convenience so API consumers can read the total without iterating
    the list.

    Example::

        result = QueryResult(rasters=[], count=0)

        result_with_data = QueryResult(
            rasters=[meta1, meta2],
            count=2,
        )
    """

    rasters: list[RasterMetadata] = Field(
        default_factory=list,
        description="List of raster metadata records matching the query.",
    )
    count: int = Field(
        ge=0,
        description="Total number of matching rasters (must equal len(rasters)).",
    )

    @model_validator(mode="after")
    def _validate_count_matches_list(self) -> QueryResult:
        """Ensure count is consistent with the length of the rasters list."""
        if self.count != len(self.rasters):
            raise ValueError(
                f"count ({self.count}) must equal the number of rasters "
                f"in the list ({len(self.rasters)})."
            )
        return self

    @classmethod
    def from_rasters(cls, rasters: list[RasterMetadata]) -> QueryResult:
        """Convenience constructor that sets count automatically."""
        return cls(rasters=rasters, count=len(rasters))


__all__ = ["QueryResult"]
