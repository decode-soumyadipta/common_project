"""CoordinateReferenceSystem Pydantic model.

Represents a CRS by its EPSG code and optional WKT definition.
Used across all services when exchanging spatial metadata.

Requirement 12.1: Shared Pydantic data models.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class CoordinateReferenceSystem(BaseModel):
    """Coordinate Reference System descriptor.

    At minimum an EPSG code must be provided.  The WKT string is optional
    and is populated by the ingestion pipeline when available.

    Example::

        crs = CoordinateReferenceSystem(epsg_code=4326)
        crs_with_wkt = CoordinateReferenceSystem(
            epsg_code=32644,
            wkt="PROJCRS[...]",
        )
    """

    epsg_code: int = Field(
        gt=0,
        description=(
            "EPSG numeric code identifying the CRS "
            "(e.g. 4326 for WGS 84, 3857 for Web Mercator)."
        ),
    )
    wkt: str | None = Field(
        default=None,
        description=(
            "Full Well-Known Text (WKT2) representation of the CRS. "
            "Optional — populated by the ingestion pipeline when available."
        ),
    )

    # ------------------------------------------------------------------ Validators ------------------------------------------------------------------

    @field_validator("epsg_code")
    @classmethod
    def _validate_epsg_range(cls, v: int) -> int:
        """EPSG codes are positive integers; the registry currently goes up to ~32767."""
        if v <= 0:
            raise ValueError(f"EPSG code must be a positive integer, got {v}.")
        return v

    @field_validator("wkt")
    @classmethod
    def _validate_wkt_not_empty(cls, v: str | None) -> str | None:
        """If provided, WKT must not be an empty or whitespace-only string."""
        if v is not None and not v.strip():
            raise ValueError("wkt must not be an empty string when provided.")
        return v

    # ------------------------------------------------------------------ Convenience helpers ------------------------------------------------------------------

    @property
    def authority_code(self) -> str:
        """Return the CRS as an 'EPSG:<code>' authority string."""
        return f"EPSG:{self.epsg_code}"

    @classmethod
    def from_authority_string(cls, authority: str) -> CoordinateReferenceSystem:
        """Parse an 'EPSG:<code>' string into a CoordinateReferenceSystem.

        Args:
            authority: String in the form ``"EPSG:4326"`` (case-insensitive).

        Raises:
            ValueError: If the string cannot be parsed.
        """
        parts = authority.strip().upper().split(":")
        if len(parts) != 2 or parts[0] != "EPSG":
            raise ValueError(
                f"Cannot parse CRS authority string '{authority}'. "
                "Expected format: 'EPSG:<code>'."
            )
        try:
            code = int(parts[1])
        except ValueError as exc:
            raise ValueError(
                f"EPSG code in '{authority}' is not a valid integer."
            ) from exc
        return cls(epsg_code=code)


__all__ = ["CoordinateReferenceSystem"]
