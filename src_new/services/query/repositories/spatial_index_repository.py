"""Spatial index repository for PostGIS GiST index management and spatial queries.

Extracted from ``src/server_vm/server_backend/catalog/catalog_repository.py``
and ``src/server_gateway/api/catalog/catalog_repository.py``.

This module is responsible for:
- Creating and managing PostGIS GiST spatial indexes on the raster_assets table.
- Executing parameterized ST_Intersects and ST_Contains queries against those indexes.

All queries use parameterized statements — no f-string SQL — to prevent SQL injection
(Requirement 10.4).  All public methods return typed models from
``src_new.shared.models`` rather than raw database rows (Requirement 10.5).

Requirements: 10.3, 10.4
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from src_new.shared.models.bounding_box import BoundingBox
from src_new.shared.models.raster_metadata import RasterMetadata, RasterKind

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- Table / column constants — single source of truth for raw SQL references ---------------------------------------------------------------------------
_TABLE = "raster_assets"
_GEOM_EXPR = "ST_GeomFromText(bounds_wkt, 4326)"
_INDEX_NAME = "idx_raster_assets_geom_gist"


class SpatialIndexRepository:
    """Repository for PostGIS spatial index operations on the raster_assets table.

    Accepts either an :class:`~sqlalchemy.ext.asyncio.AsyncSession` or an
    :class:`~sqlalchemy.ext.asyncio.AsyncConnection` so it can be used both
    inside a unit-of-work session and in standalone DDL scripts.

    Usage::

        async with AsyncSession(engine) as session:
            repo = SpatialIndexRepository(session)
            await repo.create_gist_index()
            results = await repo.query_intersects(bbox)
    """

    def __init__(self, db: AsyncSession | AsyncConnection) -> None:
        self._db = db

    # ------------------------------------------------------------------ DDL — index management ------------------------------------------------------------------

    async def create_gist_index(self, *, if_not_exists: bool = True) -> None:
        """Create a PostGIS GiST index on the ``bounds_wkt`` geometry column.

        The index is built on the expression ``ST_GeomFromText(bounds_wkt, 4326)``
        so that spatial operators (ST_Intersects, ST_Contains, etc.) can use it
        without a full table scan.

        Args:
            if_not_exists: When *True* (default) the statement is a no-op if the
                index already exists, making it safe to call on every startup.

        Raises:
            sqlalchemy.exc.SQLAlchemyError: If the DDL statement fails (e.g. the
                table does not exist yet or the user lacks CREATE INDEX privilege).

        Requirements: 10.3
        """
        qualifier = "IF NOT EXISTS" if if_not_exists else ""
        # DDL cannot use bind parameters, but the index/table names are internal constants — not user-supplied — so this is safe.
        ddl = text(
            f"CREATE INDEX {qualifier} {_INDEX_NAME} "
            f"ON {_TABLE} USING GIST ({_GEOM_EXPR})"
        )
        logger.info(
            "Creating GiST spatial index '%s' on table '%s' (if_not_exists=%s)",
            _INDEX_NAME,
            _TABLE,
            if_not_exists,
        )
        await self._execute(ddl)
        logger.info("GiST index '%s' ready.", _INDEX_NAME)

    async def drop_gist_index(self, *, if_exists: bool = True) -> None:
        """Drop the GiST spatial index.

        Useful for maintenance operations (e.g. bulk re-ingestion) where
        dropping and recreating the index is faster than incremental updates.

        Args:
            if_exists: When *True* (default) the statement is a no-op if the
                index does not exist.
        """
        qualifier = "IF EXISTS" if if_exists else ""
        ddl = text(f"DROP INDEX {qualifier} {_INDEX_NAME}")
        logger.info("Dropping GiST index '%s' (if_exists=%s)", _INDEX_NAME, if_exists)
        await self._execute(ddl)

    # ------------------------------------------------------------------ Spatial queries — ST_Intersects ------------------------------------------------------------------

    async def query_intersects(
        self,
        bbox: BoundingBox,
        *,
        limit: int | None = None,
    ) -> list[RasterMetadata]:
        """Return all rasters whose geometry intersects the given bounding box.

        Uses a parameterized ``ST_Intersects`` query so the GiST index is
        leveraged and SQL injection is impossible (Requirement 10.4).

        The query envelope is built with ``ST_MakeEnvelope`` which is the
        canonical PostGIS way to construct a rectangular geometry from four
        coordinate values.

        Args:
            bbox: The query bounding box in WGS 84 (EPSG:4326).
            limit: Optional maximum number of results to return.  When *None*
                all matching rows are returned.

        Returns:
            A list of :class:`~src_new.shared.models.RasterMetadata` objects
            ordered by ``created_at DESC`` (most recently ingested first).

        Requirements: 10.3, 10.4, 10.5
        """
        limit_clause = "LIMIT :limit" if limit is not None else ""
        stmt = text(
            f"""
            SELECT
                id,
                file_path,
                file_name,
                raster_kind,
                crs,
                bounds_wkt,
                resolution_x,
                resolution_y,
                width,
                height,
                created_at,
                updated_at
            FROM {_TABLE}
            WHERE ST_Intersects(
                {_GEOM_EXPR},
                ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)
            )
            ORDER BY created_at DESC
            {limit_clause}
            """
        )
        params: dict[str, Any] = {
            "min_lon": bbox.min_lon,
            "min_lat": bbox.min_lat,
            "max_lon": bbox.max_lon,
            "max_lat": bbox.max_lat,
        }
        if limit is not None:
            params["limit"] = limit

        logger.debug(
            "query_intersects bbox=(%s, %s, %s, %s) limit=%s",
            bbox.min_lon,
            bbox.min_lat,
            bbox.max_lon,
            bbox.max_lat,
            limit,
        )
        rows = await self._fetchall(stmt, params)
        return [_row_to_metadata(row) for row in rows]

    # ------------------------------------------------------------------ Spatial queries — ST_Contains ------------------------------------------------------------------

    async def query_contains(
        self,
        bbox: BoundingBox,
        *,
        limit: int | None = None,
    ) -> list[RasterMetadata]:
        """Return all rasters whose geometry is *fully contained* within the bbox.

        Uses a parameterized ``ST_Contains`` query.  Unlike ``query_intersects``,
        this only returns rasters that lie entirely inside the query envelope —
        rasters that merely touch or partially overlap the boundary are excluded.

        Args:
            bbox: The query bounding box in WGS 84 (EPSG:4326).
            limit: Optional maximum number of results to return.

        Returns:
            A list of :class:`~src_new.shared.models.RasterMetadata` objects
            ordered by ``created_at DESC``.

        Requirements: 10.3, 10.4, 10.5
        """
        limit_clause = "LIMIT :limit" if limit is not None else ""
        stmt = text(
            f"""
            SELECT
                id,
                file_path,
                file_name,
                raster_kind,
                crs,
                bounds_wkt,
                resolution_x,
                resolution_y,
                width,
                height,
                created_at,
                updated_at
            FROM {_TABLE}
            WHERE ST_Contains(
                ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326),
                {_GEOM_EXPR}
            )
            ORDER BY created_at DESC
            {limit_clause}
            """
        )
        params: dict[str, Any] = {
            "min_lon": bbox.min_lon,
            "min_lat": bbox.min_lat,
            "max_lon": bbox.max_lon,
            "max_lat": bbox.max_lat,
        }
        if limit is not None:
            params["limit"] = limit

        logger.debug(
            "query_contains bbox=(%s, %s, %s, %s) limit=%s",
            bbox.min_lon,
            bbox.min_lat,
            bbox.max_lon,
            bbox.max_lat,
            limit,
        )
        rows = await self._fetchall(stmt, params)
        return [_row_to_metadata(row) for row in rows]

    # ------------------------------------------------------------------ Point-based ST_Intersects convenience method ------------------------------------------------------------------

    async def query_intersects_point(
        self,
        lon: float,
        lat: float,
        *,
        limit: int | None = None,
    ) -> list[RasterMetadata]:
        """Return all rasters whose geometry intersects a single point.

        This is a convenience wrapper around ``ST_Intersects`` with a point
        geometry rather than an envelope.  Useful for click-to-query workflows
        in the desktop search client.

        Args:
            lon: Longitude in decimal degrees (WGS 84).
            lat: Latitude in decimal degrees (WGS 84).
            limit: Optional maximum number of results.

        Returns:
            A list of :class:`~src_new.shared.models.RasterMetadata` objects.

        Requirements: 10.3, 10.4, 10.5
        """
        limit_clause = "LIMIT :limit" if limit is not None else ""
        stmt = text(
            f"""
            SELECT
                id,
                file_path,
                file_name,
                raster_kind,
                crs,
                bounds_wkt,
                resolution_x,
                resolution_y,
                width,
                height,
                created_at,
                updated_at
            FROM {_TABLE}
            WHERE ST_Intersects(
                {_GEOM_EXPR},
                ST_SetSRID(ST_Point(:lon, :lat), 4326)
            )
            ORDER BY created_at DESC
            {limit_clause}
            """
        )
        params: dict[str, Any] = {"lon": lon, "lat": lat}
        if limit is not None:
            params["limit"] = limit

        logger.debug("query_intersects_point lon=%s lat=%s limit=%s", lon, lat, limit)
        rows = await self._fetchall(stmt, params)
        return [_row_to_metadata(row) for row in rows]

    # ------------------------------------------------------------------ Internal helpers ------------------------------------------------------------------

    async def _execute(self, stmt: Any, params: dict[str, Any] | None = None) -> None:
        """Execute a statement (DDL or DML) against the underlying connection."""
        if isinstance(self._db, AsyncSession):
            await self._db.execute(stmt, params or {})
            await self._db.commit()
        else:
            # AsyncConnection — used for DDL outside a session
            await self._db.execute(stmt, params or {})
            await self._db.commit()

    async def _fetchall(
        self, stmt: Any, params: dict[str, Any]
    ) -> list[Any]:
        """Execute a SELECT statement and return all rows as a list."""
        if isinstance(self._db, AsyncSession):
            result = await self._db.execute(stmt, params)
        else:
            result = await self._db.execute(stmt, params)
        return list(result.mappings().all())


# --------------------------------------------------------------------------- Row → model conversion ---------------------------------------------------------------------------

def _row_to_metadata(row: Any) -> RasterMetadata:
    """Convert a raw database row mapping to a :class:`RasterMetadata` model.

    The ``bounds_wkt`` column stores a WKT POLYGON string; we parse the
    envelope coordinates from it to populate the :class:`BoundingBox`.

    Requirements: 10.5 — repository methods return typed models, not raw rows.
    """
    bbox = _parse_bbox_from_wkt(row["bounds_wkt"])
    return RasterMetadata(
        raster_id=str(row["id"]),
        file_path=str(row["file_path"]),
        file_name=str(row["file_name"]),
        kind=_parse_kind(row.get("raster_kind")),
        crs=str(row["crs"]),
        bbox=bbox,
        resolution_x=float(row["resolution_x"]),
        resolution_y=float(row["resolution_y"]),
        width=int(row["width"]),
        height=int(row["height"]),
        upload_date=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _parse_kind(value: str | None) -> RasterKind:
    """Safely coerce a raw DB string to a :class:`RasterKind` enum value."""
    if value is None:
        return RasterKind.UNKNOWN
    try:
        return RasterKind(value)
    except ValueError:
        return RasterKind.UNKNOWN


def _parse_bbox_from_wkt(wkt: str) -> BoundingBox:
    """Extract the bounding envelope from a WKT POLYGON string.

    The WKT format stored in the database is::

        POLYGON((min_lon min_lat, max_lon min_lat, max_lon max_lat,
                  min_lon max_lat, min_lon min_lat))

    We extract the five coordinate pairs and derive the envelope from the
    min/max of all longitudes and latitudes.

    Args:
        wkt: A WKT POLYGON string as stored in ``raster_assets.bounds_wkt``.

    Returns:
        A :class:`BoundingBox` with the envelope coordinates.

    Raises:
        ValueError: If the WKT cannot be parsed.
    """
    try:
        # Strip "POLYGON((" prefix and "))" suffix, then split on ","
        inner = wkt.strip()
        if not inner.upper().startswith("POLYGON"):
            raise ValueError(f"Expected POLYGON WKT, got: {wkt!r}")
        # Remove POLYGON(( ... ))
        inner = inner[inner.index("(") + 1 :].strip()
        inner = inner[inner.index("(") + 1 :].strip()
        inner = inner[: inner.rindex(")")].strip()
        inner = inner[: inner.rindex(")")].strip()

        pairs = [pair.strip() for pair in inner.split(",")]
        lons: list[float] = []
        lats: list[float] = []
        for pair in pairs:
            parts = pair.split()
            if len(parts) < 2:
                continue
            lons.append(float(parts[0]))
            lats.append(float(parts[1]))

        if not lons or not lats:
            raise ValueError(f"No coordinate pairs found in WKT: {wkt!r}")

        min_lon, max_lon = min(lons), max(lons)
        min_lat, max_lat = min(lats), max(lats)

        # Guard against degenerate (zero-area) polygons stored in the DB
        if min_lon == max_lon:
            max_lon += 1e-9
        if min_lat == max_lat:
            max_lat += 1e-9

        return BoundingBox(
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
        )
    except (ValueError, IndexError) as exc:
        raise ValueError(f"Cannot parse BoundingBox from WKT {wkt!r}: {exc}") from exc


__all__ = ["SpatialIndexRepository"]
