"""Lazy ORM import helper for the query service repositories.

Importing ``platform_core.db.models`` directly from the repository module
would create a hard dependency on the legacy ``src/`` package tree.  This
shim tries to import the ORM model from the legacy location first, then
falls back to a minimal stand-in so that the repository can still be
imported in environments where ``platform_core`` is not on the path (e.g.
unit tests that use asyncpg directly).

The ``RasterAsset`` exported from this module is the SQLAlchemy ORM class
used by ``RasterRepository`` (sync path).  The async ``AsyncRasterRepository``
does not use this module at all — it works directly with asyncpg records.
"""
from __future__ import annotations

try:
    from platform_core.db.models import RasterAsset  # type: ignore[import]
except ImportError:
    # Minimal stand-in for environments without platform_core installed.
    # Only used by the sync SQLAlchemy path; the async path (asyncpg) does
    # not depend on this class at all.
    class RasterAsset:  # type: ignore[no-redef]
        """Placeholder when platform_core is not available."""

        __tablename__ = "raster_assets"

        def __init__(self, **kwargs: object) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)


__all__ = ["RasterAsset"]
