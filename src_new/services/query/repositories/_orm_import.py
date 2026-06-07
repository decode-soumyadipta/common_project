"""Lazy ORM import helper for the query service repositories.

Imports the RasterAsset ORM model from the shared models package.
The model definition matches the actual database schema used by both
Ingestion and Query services.

The ``RasterAsset`` exported from this module is the SQLAlchemy ORM class
used by ``RasterRepository`` (sync path).  The async ``AsyncRasterRepository``
does not use this module at all — it works directly with asyncpg records.
"""
from __future__ import annotations

from src_new.shared.models.raster_asset_orm import RasterAsset

__all__ = ["RasterAsset"]


__all__ = ["RasterAsset"]
