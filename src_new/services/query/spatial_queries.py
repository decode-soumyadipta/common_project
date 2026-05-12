"""High-level spatial query business logic for the Query Service.

Consolidates business logic from:
  - ``src/server_vm/server_backend/routes/search.py``
  - ``src/server_gateway/api/routes/search.py``
  - ``src/server_gateway/api/catalog/service.py``

This module composes :class:`~src_new.services.query.repositories.raster_repository.RasterRepository`
(or its async counterpart) and
:class:`~src_new.services.query.repositories.spatial_index_repository.SpatialIndexRepository`
to implement all spatial search operations.

**No raw SQL lives here** — all database access is delegated to the repository
layer (Requirement 10.6).  All public functions return typed models from
``src_new.shared.models`` (Requirement 10.5).

Two usage modes are provided:

1. **Sync** (:class:`SpatialQueryService`) — backed by a SQLAlchemy ``Session``
   via :class:`~src_new.services.query.repositories.raster_repository.RasterRepository`.
   Suitable for synchronous FastAPI dependencies (``run_in_executor``), CLI
   scripts, and unit tests.

2. **Async** (:class:`AsyncSpatialQueryService`) — backed by an ``asyncpg``
   connection/pool via
   :class:`~src_new.services.query.repositories.raster_repository.AsyncRasterRepository`
   and
   :class:`~src_new.services.query.repositories.spatial_index_repository.SpatialIndexRepository`.
   Preferred for FastAPI async route handlers.

Requirements: 10.6
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from src_new.shared.models.bounding_box import BoundingBox
from src_new.shared.models.query_result import QueryResult
from src_new.shared.models.raster_metadata import RasterMetadata
from src_new.services.query.repositories.raster_repository import (
    AsyncRasterRepository,
    RasterRepository,
)
from src_new.services.query.repositories.spatial_index_repository import (
    SpatialIndexRepository,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Synchronous service
# ---------------------------------------------------------------------------


class SpatialQueryService:
    """Synchronous spatial query service backed by a SQLAlchemy Session.

    Composes :class:`RasterRepository` for all database access.  The
    :class:`SpatialIndexRepository` is not used in the sync path because it
    requires an async SQLAlchemy session; the sync repository already issues
    parameterized PostGIS queries that leverage the GiST index when running
    against PostgreSQL.

    Usage::

        from sqlalchemy.orm import Session
        from src_new.services.query.spatial_queries import SpatialQueryService

        def get_service(session: Session) -> SpatialQueryService:
            return SpatialQueryService(session)

        service = get_service(db_session)
        result = service.find_by_point(lon=77.5, lat=28.6)
    """

    def __init__(self, session: Any) -> None:
        """
        Args:
            session: A SQLAlchemy ``Session`` instance.
        """
        self._repo = RasterRepository(session)

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_assets(self) -> QueryResult:
        """Return all cataloged raster assets ordered by ingestion date (newest first).

        Delegates to :meth:`RasterRepository.find_by_bbox` with a world-extent
        bounding box so the same parameterized query path is used.

        Returns:
            A :class:`QueryResult` containing all rasters.
        """
        # Use a world-extent bbox to retrieve all assets via the existing
        # parameterized find_by_bbox path (avoids a separate list_all method).
        rasters = self._repo.find_by_bbox(
            min_lon=-180.0,
            min_lat=-90.0,
            max_lon=180.0,
            max_lat=90.0,
        )
        logger.debug("list_assets: %d raster(s) found", len(rasters))
        return QueryResult.from_rasters(rasters)

    # ------------------------------------------------------------------
    # Point query
    # ------------------------------------------------------------------

    def find_by_point(self, lon: float, lat: float) -> QueryResult:
        """Return all rasters whose spatial extent contains the given point.

        Delegates to :meth:`RasterRepository.find_by_point`.

        Args:
            lon: Longitude in decimal degrees (WGS 84).
            lat: Latitude in decimal degrees (WGS 84).

        Returns:
            A :class:`QueryResult` with matching rasters.
        """
        rasters = self._repo.find_by_point(lon=lon, lat=lat)
        logger.debug("find_by_point(%.6f, %.6f): %d result(s)", lon, lat, len(rasters))
        return QueryResult.from_rasters(rasters)

    # ------------------------------------------------------------------
    # Bounding-box query
    # ------------------------------------------------------------------

    def find_by_bbox(
        self,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
    ) -> QueryResult:
        """Return all rasters that intersect the given bounding box.

        Delegates to :meth:`RasterRepository.find_by_bbox`.

        Args:
            min_lon: Western boundary longitude (WGS 84).
            min_lat: Southern boundary latitude (WGS 84).
            max_lon: Eastern boundary longitude (WGS 84).
            max_lat: Northern boundary latitude (WGS 84).

        Returns:
            A :class:`QueryResult` with matching rasters.
        """
        rasters = self._repo.find_by_bbox(
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
        )
        logger.debug(
            "find_by_bbox(%.4f,%.4f,%.4f,%.4f): %d result(s)",
            min_lon, min_lat, max_lon, max_lat, len(rasters),
        )
        return QueryResult.from_rasters(rasters)

    # ------------------------------------------------------------------
    # Polygon query (approximated via bounding-box envelope)
    # ------------------------------------------------------------------

    def find_by_polygon(
        self,
        points: List[tuple],
        buffer_meters: float = 0.0,
    ) -> QueryResult:
        """Return all rasters that intersect a polygon defined by a list of points.

        The polygon is approximated by its axis-aligned bounding envelope for
        the initial database query (using the parameterized
        :meth:`RasterRepository.find_by_bbox`).  An optional buffer in meters
        is applied by expanding the envelope by the equivalent degree offset
        (approximate, suitable for mid-latitude regions).

        This mirrors the behaviour of the original
        ``CatalogService.search_by_polygon`` in ``src/server_gateway/api/catalog/service.py``.

        Args:
            points: List of ``(lon, lat)`` tuples defining the polygon vertices
                in WGS 84 decimal degrees.
            buffer_meters: Optional buffer distance in metres to expand the
                query envelope.  Defaults to 0.0 (no buffer).

        Returns:
            A :class:`QueryResult` with matching rasters.

        Raises:
            ValueError: If fewer than 3 points are provided (degenerate polygon).
        """
        if len(points) < 3:
            raise ValueError(
                f"A polygon requires at least 3 points; got {len(points)}."
            )

        lons = [p[0] for p in points]
        lats = [p[1] for p in points]
        min_lon, max_lon = min(lons), max(lons)
        min_lat, max_lat = min(lats), max(lats)

        if buffer_meters > 0.0:
            # Approximate degree offset: 1° ≈ 111_320 m at the equator.
            # This is a reasonable approximation for mid-latitude regions.
            deg_offset = buffer_meters / 111_320.0
            min_lon = max(-180.0, min_lon - deg_offset)
            min_lat = max(-90.0, min_lat - deg_offset)
            max_lon = min(180.0, max_lon + deg_offset)
            max_lat = min(90.0, max_lat + deg_offset)

        rasters = self._repo.find_by_bbox(
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
        )
        logger.debug(
            "find_by_polygon(%d points, buffer=%.1fm): %d result(s)",
            len(points), buffer_meters, len(rasters),
        )
        return QueryResult.from_rasters(rasters)

    # ------------------------------------------------------------------
    # Single-raster lookup
    # ------------------------------------------------------------------

    def find_by_id(self, raster_id: str) -> Optional[RasterMetadata]:
        """Return the raster with the given UUID, or None if not found.

        Delegates to :meth:`RasterRepository.find_by_id`.

        Args:
            raster_id: UUID string of the raster asset.

        Returns:
            A :class:`RasterMetadata` instance, or ``None`` if not found.
        """
        result = self._repo.find_by_id(raster_id)
        if result is None:
            logger.debug("find_by_id(%s): not found", raster_id)
        return result

    # ------------------------------------------------------------------
    # Catalog management
    # ------------------------------------------------------------------

    def insert_metadata(self, metadata: RasterMetadata) -> RasterMetadata:
        """Insert a new raster metadata record into the catalog.

        Delegates to :meth:`RasterRepository.insert_metadata`.

        Args:
            metadata: Fully populated :class:`RasterMetadata` instance.

        Returns:
            The inserted :class:`RasterMetadata` with ``raster_id`` populated.

        Raises:
            ValueError: If a record with the same ``file_path`` already exists.
            RuntimeError: On any database error.
        """
        inserted = self._repo.insert_metadata(metadata)
        logger.info("insert_metadata: cataloged raster %s", inserted.raster_id)
        return inserted

    def update_metadata(
        self, raster_id: str, metadata: RasterMetadata
    ) -> Optional[RasterMetadata]:
        """Update an existing raster metadata record.

        Delegates to :meth:`RasterRepository.update_metadata`.

        Args:
            raster_id: UUID of the record to update.
            metadata: :class:`RasterMetadata` carrying the new field values.

        Returns:
            The updated :class:`RasterMetadata`, or ``None`` if not found.

        Raises:
            RuntimeError: On any database error.
        """
        updated = self._repo.update_metadata(raster_id, metadata)
        if updated is None:
            logger.warning("update_metadata: raster %s not found", raster_id)
        return updated


# ---------------------------------------------------------------------------
# Asynchronous service
# ---------------------------------------------------------------------------


class AsyncSpatialQueryService:
    """Async spatial query service backed by asyncpg and SQLAlchemy async session.

    Composes :class:`AsyncRasterRepository` (asyncpg) for CRUD operations and
    :class:`SpatialIndexRepository` (SQLAlchemy async) for GiST-indexed spatial
    queries.  The two repositories are complementary:

    - :class:`AsyncRasterRepository` is used for ``find_by_id``,
      ``insert_metadata``, and ``update_metadata`` (full-row operations).
    - :class:`SpatialIndexRepository` is used for ``find_by_point``,
      ``find_by_bbox``, and ``find_by_polygon`` (spatial index queries).

    Usage::

        import asyncpg
        from sqlalchemy.ext.asyncio import AsyncSession
        from src_new.services.query.spatial_queries import AsyncSpatialQueryService

        async def get_service(
            conn: asyncpg.Connection,
            async_session: AsyncSession,
        ) -> AsyncSpatialQueryService:
            return AsyncSpatialQueryService(conn, async_session)

        service = await get_service(conn, session)
        result = await service.find_by_point(lon=77.5, lat=28.6)
    """

    def __init__(self, asyncpg_conn: Any, async_session: Any) -> None:
        """
        Args:
            asyncpg_conn: An ``asyncpg.Connection`` or ``asyncpg.Pool`` instance
                used by :class:`AsyncRasterRepository`.
            async_session: A SQLAlchemy ``AsyncSession`` or ``AsyncConnection``
                used by :class:`SpatialIndexRepository`.
        """
        self._raster_repo = AsyncRasterRepository(asyncpg_conn)
        self._spatial_repo = SpatialIndexRepository(async_session)

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    async def list_assets(self) -> QueryResult:
        """Return all cataloged raster assets ordered by ingestion date (newest first).

        Uses :meth:`SpatialIndexRepository.query_intersects` with a world-extent
        bounding box so the GiST index path is exercised.

        Returns:
            A :class:`QueryResult` containing all rasters.
        """
        world_bbox = BoundingBox(
            min_lon=-180.0, min_lat=-90.0, max_lon=180.0, max_lat=90.0
        )
        rasters = await self._spatial_repo.query_intersects(world_bbox)
        logger.debug("list_assets: %d raster(s) found", len(rasters))
        return QueryResult.from_rasters(rasters)

    # ------------------------------------------------------------------
    # Point query
    # ------------------------------------------------------------------

    async def find_by_point(self, lon: float, lat: float) -> QueryResult:
        """Return all rasters whose spatial extent contains the given point.

        Delegates to :meth:`SpatialIndexRepository.query_intersects_point`
        which uses a parameterized ``ST_Intersects`` with a point geometry.

        Args:
            lon: Longitude in decimal degrees (WGS 84).
            lat: Latitude in decimal degrees (WGS 84).

        Returns:
            A :class:`QueryResult` with matching rasters.
        """
        rasters = await self._spatial_repo.query_intersects_point(lon=lon, lat=lat)
        logger.debug("find_by_point(%.6f, %.6f): %d result(s)", lon, lat, len(rasters))
        return QueryResult.from_rasters(rasters)

    # ------------------------------------------------------------------
    # Bounding-box query
    # ------------------------------------------------------------------

    async def find_by_bbox(
        self,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
    ) -> QueryResult:
        """Return all rasters that intersect the given bounding box.

        Delegates to :meth:`SpatialIndexRepository.query_intersects` which
        uses a parameterized ``ST_Intersects`` with ``ST_MakeEnvelope``.

        Args:
            min_lon: Western boundary longitude (WGS 84).
            min_lat: Southern boundary latitude (WGS 84).
            max_lon: Eastern boundary longitude (WGS 84).
            max_lat: Northern boundary latitude (WGS 84).

        Returns:
            A :class:`QueryResult` with matching rasters.
        """
        bbox = BoundingBox(
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
        )
        rasters = await self._spatial_repo.query_intersects(bbox)
        logger.debug(
            "find_by_bbox(%.4f,%.4f,%.4f,%.4f): %d result(s)",
            min_lon, min_lat, max_lon, max_lat, len(rasters),
        )
        return QueryResult.from_rasters(rasters)

    # ------------------------------------------------------------------
    # Polygon query (approximated via bounding-box envelope)
    # ------------------------------------------------------------------

    async def find_by_polygon(
        self,
        points: List[tuple],
        buffer_meters: float = 0.0,
    ) -> QueryResult:
        """Return all rasters that intersect a polygon defined by a list of points.

        The polygon is approximated by its axis-aligned bounding envelope for
        the database query (using :meth:`SpatialIndexRepository.query_intersects`).
        An optional buffer in metres is applied by expanding the envelope.

        Args:
            points: List of ``(lon, lat)`` tuples defining the polygon vertices
                in WGS 84 decimal degrees.
            buffer_meters: Optional buffer distance in metres to expand the
                query envelope.  Defaults to 0.0 (no buffer).

        Returns:
            A :class:`QueryResult` with matching rasters.

        Raises:
            ValueError: If fewer than 3 points are provided (degenerate polygon).
        """
        if len(points) < 3:
            raise ValueError(
                f"A polygon requires at least 3 points; got {len(points)}."
            )

        lons = [p[0] for p in points]
        lats = [p[1] for p in points]
        min_lon, max_lon = min(lons), max(lons)
        min_lat, max_lat = min(lats), max(lats)

        if buffer_meters > 0.0:
            deg_offset = buffer_meters / 111_320.0
            min_lon = max(-180.0, min_lon - deg_offset)
            min_lat = max(-90.0, min_lat - deg_offset)
            max_lon = min(180.0, max_lon + deg_offset)
            max_lat = min(90.0, max_lat + deg_offset)

        bbox = BoundingBox(
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
        )
        rasters = await self._spatial_repo.query_intersects(bbox)
        logger.debug(
            "find_by_polygon(%d points, buffer=%.1fm): %d result(s)",
            len(points), buffer_meters, len(rasters),
        )
        return QueryResult.from_rasters(rasters)

    # ------------------------------------------------------------------
    # Contained-within query (uses ST_Contains via spatial index repo)
    # ------------------------------------------------------------------

    async def find_contained_by_bbox(
        self,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
    ) -> QueryResult:
        """Return rasters *fully contained* within the given bounding box.

        Unlike :meth:`find_by_bbox` (which returns any raster that *intersects*
        the query envelope), this method only returns rasters that lie entirely
        inside the envelope.  Delegates to
        :meth:`SpatialIndexRepository.query_contains`.

        Args:
            min_lon: Western boundary longitude (WGS 84).
            min_lat: Southern boundary latitude (WGS 84).
            max_lon: Eastern boundary longitude (WGS 84).
            max_lat: Northern boundary latitude (WGS 84).

        Returns:
            A :class:`QueryResult` with fully-contained rasters.
        """
        bbox = BoundingBox(
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
        )
        rasters = await self._spatial_repo.query_contains(bbox)
        logger.debug(
            "find_contained_by_bbox(%.4f,%.4f,%.4f,%.4f): %d result(s)",
            min_lon, min_lat, max_lon, max_lat, len(rasters),
        )
        return QueryResult.from_rasters(rasters)

    # ------------------------------------------------------------------
    # Single-raster lookup
    # ------------------------------------------------------------------

    async def find_by_id(self, raster_id: str) -> Optional[RasterMetadata]:
        """Return the raster with the given UUID, or None if not found.

        Delegates to :meth:`AsyncRasterRepository.find_by_id`.

        Args:
            raster_id: UUID string of the raster asset.

        Returns:
            A :class:`RasterMetadata` instance, or ``None`` if not found.
        """
        result = await self._raster_repo.find_by_id(raster_id)
        if result is None:
            logger.debug("find_by_id(%s): not found", raster_id)
        return result

    # ------------------------------------------------------------------
    # Catalog management
    # ------------------------------------------------------------------

    async def insert_metadata(self, metadata: RasterMetadata) -> RasterMetadata:
        """Insert a new raster metadata record into the catalog.

        Delegates to :meth:`AsyncRasterRepository.insert_metadata`.

        Args:
            metadata: Fully populated :class:`RasterMetadata` instance.

        Returns:
            The inserted :class:`RasterMetadata` with ``raster_id`` populated.

        Raises:
            ValueError: If a record with the same ``file_path`` already exists.
            RuntimeError: On any database error.
        """
        inserted = await self._raster_repo.insert_metadata(metadata)
        logger.info("insert_metadata: cataloged raster %s", inserted.raster_id)
        return inserted

    async def update_metadata(
        self, raster_id: str, metadata: RasterMetadata
    ) -> Optional[RasterMetadata]:
        """Update an existing raster metadata record.

        Delegates to :meth:`AsyncRasterRepository.update_metadata`.

        Args:
            raster_id: UUID of the record to update.
            metadata: :class:`RasterMetadata` carrying the new field values.

        Returns:
            The updated :class:`RasterMetadata`, or ``None`` if not found.

        Raises:
            RuntimeError: On any database error.
        """
        updated = await self._raster_repo.update_metadata(raster_id, metadata)
        if updated is None:
            logger.warning("update_metadata: raster %s not found", raster_id)
        return updated

    # ------------------------------------------------------------------
    # Index management (delegated to SpatialIndexRepository)
    # ------------------------------------------------------------------

    async def ensure_spatial_index(self) -> None:
        """Ensure the PostGIS GiST spatial index exists on the raster_assets table.

        Safe to call on every service startup — uses ``CREATE INDEX IF NOT EXISTS``
        so it is a no-op when the index is already present.

        Delegates to :meth:`SpatialIndexRepository.create_gist_index`.
        """
        await self._spatial_repo.create_gist_index(if_not_exists=True)
        logger.info("Spatial GiST index verified/created.")


__all__ = ["SpatialQueryService", "AsyncSpatialQueryService"]
