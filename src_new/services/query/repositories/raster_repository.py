"""PostGIS repository for raster asset catalog operations.

Consolidates query logic from:
  - ``src/server_vm/server_backend/catalog/catalog_repository.py``
  - ``src/server_gateway/api/catalog/catalog_repository.py``

All SQL statements use parameterized placeholders — no f-string interpolation —
to prevent SQL injection (Requirement 10.4).

All public methods return typed models from ``src_new.shared.models`` rather
than raw database rows (Requirement 10.5).

The repository exposes two usage modes:

1. **Async (asyncpg)** — preferred for FastAPI request handlers.
   Instantiate with an ``asyncpg.Connection`` or ``asyncpg.Pool``.

2. **Sync (SQLAlchemy Session)** — available for scripts, tests, and legacy
   callers that already hold a SQLAlchemy session.

Requirements: 10.1, 10.2, 10.4, 10.5
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from src_new.services.query.repositories._orm_import import RasterAsset
from src_new.shared.models.bounding_box import BoundingBox
from src_new.shared.models.raster_metadata import RasterKind, RasterMetadata

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- Internal helpers ---------------------------------------------------------------------------


def _normalized_bounds(
    west: float, south: float, east: float, north: float
) -> tuple[float, float, float, float]:
    """Return bounds with guaranteed west<=east and south<=north ordering."""
    return min(west, east), min(south, north), max(west, east), max(south, north)


def _bbox_from_wkt(wkt: str) -> BoundingBox:
    """Parse a WKT POLYGON envelope into a BoundingBox.

    Expects the canonical form produced by ``BoundingBox.to_wkt_polygon()``:
    ``POLYGON((min_lon min_lat, max_lon min_lat, max_lon max_lat, min_lon max_lat, min_lon min_lat))``
    """
    # Strip "POLYGON((" prefix and "))" suffix, then split on ","
    inner = wkt.strip()
    if inner.upper().startswith("POLYGON(("):
        inner = inner[9:]
    if inner.endswith("))"):
        inner = inner[:-2]
    pairs = [p.strip().split() for p in inner.split(",")]
    lons = [float(p[0]) for p in pairs if len(p) == 2]
    lats = [float(p[1]) for p in pairs if len(p) == 2]
    return BoundingBox(
        min_lon=min(lons),
        min_lat=min(lats),
        max_lon=max(lons),
        max_lat=max(lats),
    )


def _row_to_raster_metadata(row: Any) -> RasterMetadata:
    """Convert a database row (dict-like or ORM object) to a RasterMetadata model.

    Accepts both asyncpg ``Record`` objects (accessed by column name) and
    SQLAlchemy ORM ``RasterAsset`` instances.
    """
    # asyncpg Record — supports dict-style access
    if hasattr(row, "keys"):
        raster_id = str(row.get("raster_id") or row.get("id"))
        file_path = str(row["file_path"])
        file_name = str(row["file_name"])
        kind_raw = str(row.get("raster_kind") or row.get("kind"))
        crs = str(row["crs"])
        # Handle both old schema (min_lon, etc.) and new schema (bounds_wkt)
        if "bounds_wkt" in row.keys() and row.get("bounds_wkt") is not None:
            bounds_wkt = str(row["bounds_wkt"])
        else:
            # Construct WKT from bounding box coordinates
            min_lon = float(row["min_lon"])
            min_lat = float(row["min_lat"])
            max_lon = float(row["max_lon"])
            max_lat = float(row["max_lat"])
            bounds_wkt = (
                f"POLYGON(("
                f"{min_lon} {min_lat}, "
                f"{max_lon} {min_lat}, "
                f"{max_lon} {max_lat}, "
                f"{min_lon} {max_lat}, "
                f"{min_lon} {min_lat}"
                f"))"
            )
        resolution_x = float(row["resolution_x"])
        resolution_y = float(row["resolution_y"])
        width = int(row["width"])
        height = int(row["height"])
        tags = str(row.get("tags") or "") if "tags" in row.keys() else ""
        description = str(row.get("description") or "") if "description" in row.keys() else ""
        upload_date: Optional[datetime] = row.get("created_at") or row.get("upload_date")
        updated_at: Optional[datetime] = row.get("updated_at")
    else:
        # SQLAlchemy ORM RasterAsset
        raster_id = str(getattr(row, "raster_id", None) or getattr(row, "id", None))
        file_path = str(row.file_path)
        file_name = str(row.file_name)
        kind_raw = str(getattr(row, "kind", None) or getattr(row, "raster_kind", None))
        crs = str(row.crs)
        # Reconstruct WKT bounds from database columns
        if hasattr(row, "bounds_wkt") and getattr(row, "bounds_wkt") is not None:
            bounds_wkt = str(row.bounds_wkt)
        else:
            min_lon = float(row.min_lon)
            min_lat = float(row.min_lat)
            max_lon = float(row.max_lon)
            max_lat = float(row.max_lat)
            bounds_wkt = (
                f"POLYGON(("
                f"{min_lon} {min_lat}, "
                f"{max_lon} {min_lat}, "
                f"{max_lon} {max_lat}, "
                f"{min_lon} {max_lat}, "
                f"{min_lon} {min_lat}"
                f"))"
            )
        resolution_x = float(row.resolution_x)
        resolution_y = float(row.resolution_y)
        width = int(row.width)
        height = int(row.height)
        tags = str(getattr(row, "tags", "") or "")
        description = str(getattr(row, "description", "") or "")
        upload_date = getattr(row, "upload_date", None) or getattr(row, "created_at", None)
        updated_at = getattr(row, "updated_at", None)

    try:
        kind = RasterKind(kind_raw)
    except ValueError:
        kind = RasterKind.UNKNOWN

    try:
        bbox = _bbox_from_wkt(bounds_wkt)
    except Exception as exc:
        logger.warning("Could not parse bounds_wkt for raster %s: %s", raster_id, exc)
        # Provide a degenerate bbox so the model can still be constructed
        bbox = BoundingBox(min_lon=-180.0, min_lat=-90.0, max_lon=180.0, max_lat=90.0)

    return RasterMetadata(
        raster_id=raster_id,
        file_path=file_path,
        file_name=file_name,
        kind=kind,
        crs=crs,
        bbox=bbox,
        resolution_x=resolution_x,
        resolution_y=resolution_y,
        width=width,
        height=height,
        tags=tags,
        description=description,
        upload_date=upload_date,
        updated_at=updated_at,
    )


# --------------------------------------------------------------------------- Sync repository (SQLAlchemy Session) ---------------------------------------------------------------------------


class RasterRepository:
    """Synchronous PostGIS repository backed by a SQLAlchemy ``Session``.

    Suitable for use in synchronous FastAPI dependencies (``run_in_executor``),
    CLI scripts, and unit tests that use an in-process SQLite/PostGIS database.

    All SQL queries are parameterized.  PostGIS-specific queries are used when
    the underlying dialect is PostgreSQL; a pure-Python bounding-box fallback
    is used for SQLite (useful in tests).

    Requirement 10.1: Repository layer in ``src_new/services/query/repositories/``.
    Requirement 10.2: Methods find_by_bbox, find_by_point, find_by_id,
                      insert_metadata, update_metadata.
    Requirement 10.4: Parameterized statements only.
    Requirement 10.5: Returns typed RasterMetadata models.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------ Read operations ------------------------------------------------------------------

    def find_by_id(self, raster_id: str) -> Optional[RasterMetadata]:
        """Return the raster with the given UUID, or None if not found.

        Uses a parameterized equality filter — no string interpolation.

        Args:
            raster_id: UUID string of the raster asset.

        Returns:
            A ``RasterMetadata`` instance, or ``None`` if not found.
        """
        pk_attr = "id" if hasattr(RasterAsset, "id") else "raster_id"
        stmt = select(RasterAsset).where(getattr(RasterAsset, pk_attr) == raster_id)
        asset = self._session.scalar(stmt)
        if asset is None:
            return None
        logger.debug("find_by_id: found raster %s", raster_id)
        return _row_to_raster_metadata(asset)

    def find_all(self) -> list[RasterMetadata]:
        """Return all rasters ordered by ingestion date (newest first).

        Returns:
            List of ``RasterMetadata`` objects ordered by upload_date DESC.
            Returns empty list if no rasters are found.
        """
        try:
            sort_attr = "created_at" if hasattr(RasterAsset, "created_at") else "upload_date"
            stmt = select(RasterAsset).order_by(getattr(RasterAsset, sort_attr).desc())
            assets = self._session.scalars(stmt).all()
            logger.debug("find_all: found %d rasters", len(assets))
            return [_row_to_raster_metadata(asset) for asset in assets]
        except Exception as exc:
            logger.exception("find_all failed: %s", exc)
            return []  # Return empty list on error instead of raising

    def find_by_point(self, lon: float, lat: float) -> list[RasterMetadata]:
        """Return all rasters whose spatial extent contains the given point.

        Uses ``ST_Intersects`` with ``ST_SetSRID(ST_Point(...), 4326)`` on
        PostgreSQL/PostGIS.  Falls back to a pure-Python bounds check on
        SQLite (for testing).

        All parameters are passed as bound variables — no f-string SQL.

        Args:
            lon: Longitude in decimal degrees (WGS 84).
            lat: Latitude in decimal degrees (WGS 84).

        Returns:
            List of ``RasterMetadata`` objects ordered by ingestion date (newest first).
        """
        import time
        start_time = time.time()
        
        # Determine schema columns dynamically
        pk_col = "id" if hasattr(RasterAsset, "id") else "raster_id"
        sort_col = "created_at" if hasattr(RasterAsset, "created_at") else "upload_date"
        
        if self._is_postgresql():
            # Parameterized PostGIS point-in-polygon query. Uses ST_SetSRID(ST_Point(:lon, :lat), 4326) — no string interpolation.
            stmt = text(
                f"""
                SELECT {pk_col}
                FROM raster_assets
                WHERE ST_Intersects(
                    ST_GeomFromText(bounds_wkt, 4326),
                    ST_SetSRID(ST_Point(:lon, :lat), 4326)
                )
                ORDER BY {sort_col} DESC
                """
            )
            
            # Log database query (Requirement 18.7)
            logger.info(
                "Database query: find_by_point — lon=%.6f lat=%.6f",
                lon, lat,
                extra={
                    "event": "database_query",
                    "query_type": "find_by_point",
                    "lon": lon,
                    "lat": lat,
                }
            )
            
            ids = self._select_asset_ids(stmt, {"lon": lon, "lat": lat})
            assets = self._load_assets_by_ids(ids)
            
            duration_ms = (time.time() - start_time) * 1000
            logger.info(
                "Database query complete: find_by_point — results=%d duration=%.2fms",
                len(assets),
                duration_ms,
                extra={
                    "event": "database_query_complete",
                    "query_type": "find_by_point",
                    "result_count": len(assets),
                    "duration_ms": round(duration_ms, 2),
                }
            )
            logger.debug("find_by_point(%.6f, %.6f): %d result(s)", lon, lat, len(assets))
            return [_row_to_raster_metadata(a) for a in assets]

        # SQLite fallback: load id + bounding box coordinates, then filter in Python
        logger.info(
            "Database query: find_by_point (SQLite fallback) — lon=%.6f lat=%.6f",
            lon, lat,
            extra={
                "event": "database_query",
                "query_type": "find_by_point_sqlite",
                "lon": lon,
                "lat": lat,
            }
        )
        
        if all(hasattr(RasterAsset, attr) for attr in ("min_lon", "min_lat", "max_lon", "max_lat")):
            stmt_all = select(
                getattr(RasterAsset, pk_col),
                RasterAsset.min_lon,
                RasterAsset.min_lat,
                RasterAsset.max_lon,
                RasterAsset.max_lat,
            ).order_by(getattr(RasterAsset, sort_col).desc())

            matching_ids: list[str] = []
            for asset_id, min_lon, min_lat, max_lon, max_lat in self._session.execute(
                stmt_all
            ):
                try:
                    # Check if point is within bounding box
                    if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
                        matching_ids.append(str(asset_id))
                except Exception:
                    pass
        else:
            stmt_all = select(
                getattr(RasterAsset, pk_col),
                RasterAsset.bounds_wkt,
            ).order_by(getattr(RasterAsset, sort_col).desc())

            matching_ids = []
            for asset_id, bounds_wkt in self._session.execute(stmt_all):
                try:
                    bbox = _bbox_from_wkt(str(bounds_wkt))
                except Exception:
                    continue
                if bbox.contains_point(lon, lat):
                    matching_ids.append(str(asset_id))

        assets = self._load_assets_by_ids(matching_ids)
        
        duration_ms = (time.time() - start_time) * 1000
        logger.info(
            "Database query complete: find_by_point (SQLite) — results=%d duration=%.2fms",
            len(assets),
            duration_ms,
            extra={
                "event": "database_query_complete",
                "query_type": "find_by_point_sqlite",
                "result_count": len(assets),
                "duration_ms": round(duration_ms, 2),
            }
        )
        logger.debug(
            "find_by_point(%.6f, %.6f) [SQLite fallback]: %d result(s)",
            lon, lat, len(assets),
        )
        return [_row_to_raster_metadata(a) for a in assets]

    def find_by_bbox(
        self,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
    ) -> list[RasterMetadata]:
        """Return all rasters that intersect the given bounding box.

        Uses ``ST_Intersects`` with ``ST_MakeEnvelope`` on PostgreSQL/PostGIS.
        Falls back to a pure-Python intersection check on SQLite.

        All parameters are passed as bound variables — no f-string SQL.

        Args:
            min_lon: Western boundary longitude (WGS 84).
            min_lat: Southern boundary latitude (WGS 84).
            max_lon: Eastern boundary longitude (WGS 84).
            max_lat: Northern boundary latitude (WGS 84).

        Returns:
            List of ``RasterMetadata`` objects ordered by ingestion date (newest first).
        """
        west, south, east, north = _normalized_bounds(min_lon, min_lat, max_lon, max_lat)

        # Determine schema columns dynamically
        pk_col = "id" if hasattr(RasterAsset, "id") else "raster_id"
        sort_col = "created_at" if hasattr(RasterAsset, "created_at") else "upload_date"

        if self._is_postgresql():
            # Parameterized PostGIS bbox intersection query. ST_MakeEnvelope(:west, :south, :east, :north, 4326) — no interpolation.
            stmt = text(
                f"""
                SELECT {pk_col}
                FROM raster_assets
                WHERE ST_Intersects(
                    ST_GeomFromText(bounds_wkt, 4326),
                    ST_MakeEnvelope(:west, :south, :east, :north, 4326)
                )
                ORDER BY {sort_col} DESC
                """
            )
            ids = self._select_asset_ids(
                stmt,
                {"west": west, "south": south, "east": east, "north": north},
            )
            assets = self._load_assets_by_ids(ids)
            logger.debug(
                "find_by_bbox(%.4f,%.4f,%.4f,%.4f): %d result(s)",
                west, south, east, north, len(assets),
            )
            return [_row_to_raster_metadata(a) for a in assets]

        # SQLite fallback: load raster_id + bounding box coordinates, then filter in Python
        if all(hasattr(RasterAsset, attr) for attr in ("min_lon", "min_lat", "max_lon", "max_lat")):
            stmt_all = select(
                getattr(RasterAsset, pk_col),
                RasterAsset.min_lon,
                RasterAsset.min_lat,
                RasterAsset.max_lon,
                RasterAsset.max_lat,
            ).order_by(getattr(RasterAsset, sort_col).desc())

            matching_ids = []
            for asset_id, asset_min_lon, asset_min_lat, asset_max_lon, asset_max_lat in self._session.execute(
                stmt_all
            ):
                try:
                    # Check if bounding boxes intersect Two boxes intersect if they overlap in both X and Y dimensions
                    if not (
                        asset_max_lon < west
                        or asset_min_lon > east
                        or asset_max_lat < south
                        or asset_min_lat > north
                    ):
                        matching_ids.append(str(asset_id))
                except Exception:
                    pass
        else:
            stmt_all = select(
                getattr(RasterAsset, pk_col),
                RasterAsset.bounds_wkt,
            ).order_by(getattr(RasterAsset, sort_col).desc())

            matching_ids = []
            query_bbox = BoundingBox(min_lon=west, min_lat=south, max_lon=east, max_lat=north)
            for asset_id, bounds_wkt in self._session.execute(stmt_all):
                try:
                    bbox = _bbox_from_wkt(str(bounds_wkt))
                except Exception:
                    continue
                if bbox.intersects(query_bbox):
                    matching_ids.append(str(asset_id))

        assets = self._load_assets_by_ids(matching_ids)
        logger.debug(
            "find_by_bbox(%.4f,%.4f,%.4f,%.4f) [SQLite fallback]: %d result(s)",
            west, south, east, north, len(assets),
        )
        return [_row_to_raster_metadata(a) for a in assets]

    # ------------------------------------------------------------------ Write operations ------------------------------------------------------------------

    def insert_metadata(self, metadata: RasterMetadata) -> RasterMetadata:
        """Insert a new raster metadata record into the catalog.

        If a record with the same ``file_path`` already exists, raises
        ``ValueError``.  Use ``update_metadata`` to modify existing records.

        All field values are passed as ORM-level bound parameters — no raw
        SQL string interpolation.

        Args:
            metadata: Fully populated ``RasterMetadata`` instance.  If
                ``raster_id`` is empty, a new UUID is generated.

        Returns:
            The inserted ``RasterMetadata`` with ``raster_id`` populated.

        Raises:
            ValueError: If a record with the same ``file_path`` already exists.
            RuntimeError: On any database error (original exception is chained).
        """
        raster_id = metadata.raster_id or str(uuid4())

        # Check for duplicate path using a parameterized SELECT
        existing_stmt = select(RasterAsset).where(
            RasterAsset.file_path == metadata.file_path
        )
        existing = self._session.scalar(existing_stmt)
        if existing is not None:
            existing_id = getattr(existing, "id", None) or getattr(existing, "raster_id", None)
            raise ValueError(
                f"A raster with file_path '{metadata.file_path}' already exists "
                f"(id={existing_id}). Use update_metadata() to modify it."
            )

        try:
            # Polymorphically instantiate RasterAsset
            asset_kwargs = {}
            if hasattr(RasterAsset, "id"):
                asset_kwargs["id"] = raster_id
            else:
                asset_kwargs["raster_id"] = raster_id

            asset_kwargs["file_path"] = metadata.file_path
            asset_kwargs["file_name"] = metadata.file_name

            if hasattr(RasterAsset, "raster_kind"):
                asset_kwargs["raster_kind"] = metadata.kind.value
            else:
                asset_kwargs["kind"] = metadata.kind.value

            asset_kwargs["crs"] = metadata.crs

            if hasattr(RasterAsset, "bounds_wkt"):
                asset_kwargs["bounds_wkt"] = metadata.bbox.to_wkt_polygon()
            else:
                asset_kwargs["min_lon"] = metadata.bbox.min_lon
                asset_kwargs["min_lat"] = metadata.bbox.min_lat
                asset_kwargs["max_lon"] = metadata.bbox.max_lon
                asset_kwargs["max_lat"] = metadata.bbox.max_lat

            asset_kwargs["resolution_x"] = metadata.resolution_x
            asset_kwargs["resolution_y"] = metadata.resolution_y
            asset_kwargs["width"] = metadata.width
            asset_kwargs["height"] = metadata.height

            asset = RasterAsset(**asset_kwargs)
            self._session.add(asset)
            self._session.commit()
            self._session.refresh(asset)
            logger.info("insert_metadata: inserted raster %s (%s)", raster_id, metadata.file_name)
            return _row_to_raster_metadata(asset)
        except Exception as exc:
            try:
                self._session.rollback()
            except Exception:
                pass
            raise RuntimeError(f"insert_metadata failed: {exc}") from exc

    def update_metadata(
        self,
        raster_id: str,
        metadata: RasterMetadata,
    ) -> Optional[RasterMetadata]:
        """Update an existing raster metadata record.

        Only the mutable fields are updated: ``crs``, ``bbox``, ``resolution_x``,
        ``resolution_y``, ``width``, ``height``, ``kind``.  The ``file_path``,
        ``file_name``, and ``raster_id`` are immutable after insertion.

        All updates go through the ORM — no raw SQL string interpolation.

        Args:
            raster_id: UUID of the record to update.
            metadata: ``RasterMetadata`` carrying the new field values.

        Returns:
            The updated ``RasterMetadata``, or ``None`` if ``raster_id`` was not found.

        Raises:
            RuntimeError: On any database error (original exception is chained).
        """
        pk_attr = "id" if hasattr(RasterAsset, "id") else "raster_id"
        stmt = select(RasterAsset).where(getattr(RasterAsset, pk_attr) == raster_id)
        asset = self._session.scalar(stmt)
        if asset is None:
            logger.warning("update_metadata: raster %s not found", raster_id)
            return None

        try:
            asset.crs = metadata.crs
            if hasattr(asset, "bounds_wkt"):
                asset.bounds_wkt = metadata.bbox.to_wkt_polygon()
            else:
                asset.min_lon = metadata.bbox.min_lon
                asset.min_lat = metadata.bbox.min_lat
                asset.max_lon = metadata.bbox.max_lon
                asset.max_lat = metadata.bbox.max_lat
            asset.resolution_x = metadata.resolution_x
            asset.resolution_y = metadata.resolution_y
            asset.width = metadata.width
            asset.height = metadata.height
            if hasattr(asset, "raster_kind"):
                asset.raster_kind = metadata.kind.value
            else:
                asset.kind = metadata.kind.value
            self._session.add(asset)
            self._session.commit()
            self._session.refresh(asset)
            logger.info("update_metadata: updated raster %s", raster_id)
            return _row_to_raster_metadata(asset)
        except Exception as exc:
            try:
                self._session.rollback()
            except Exception:
                pass
            raise RuntimeError(f"update_metadata failed: {exc}") from exc

    # ------------------------------------------------------------------ Private helpers ------------------------------------------------------------------

    def _is_postgresql(self) -> bool:
        """Return True when the underlying database dialect is PostgreSQL."""
        bind = self._session.bind
        return bool(bind and bind.dialect.name == "postgresql")

    def _select_asset_ids(
        self, stmt: Any, params: dict[str, Any]
    ) -> list[str]:
        """Execute a parameterized SELECT returning a list of id strings."""
        return [str(row[0]) for row in self._session.execute(stmt, params)]

    def _load_assets_by_ids(self, ids: list[str]) -> list[Any]:
        """Load full ORM objects for the given id list, preserving order."""
        if not ids:
            return []
        pk_attr = "id" if hasattr(RasterAsset, "id") else "raster_id"
        stmt = select(RasterAsset).where(getattr(RasterAsset, pk_attr).in_(ids))
        rows = list(self._session.scalars(stmt))
        by_id = {str(getattr(row, pk_attr)): row for row in rows}
        return [by_id[item_id] for item_id in ids if item_id in by_id]


# --------------------------------------------------------------------------- Async repository (asyncpg) ---------------------------------------------------------------------------


class AsyncRasterRepository:
    """Async PostGIS repository backed by an ``asyncpg`` connection or pool.

    Designed for use inside FastAPI async route handlers.  All queries are
    fully parameterized using asyncpg's ``$1, $2, ...`` placeholder syntax.

    Usage::

        import asyncpg
        from src_new.shared.config import settings

        pool = await asyncpg.create_pool(settings.database_url)

        async with pool.acquire() as conn:
            repo = AsyncRasterRepository(conn)
            results = await repo.find_by_point(lon=77.5, lat=28.6)

    Requirement 10.1: Repository layer in ``src_new/services/query/repositories/``.
    Requirement 10.2: Methods find_by_bbox, find_by_point, find_by_id,
                      insert_metadata, update_metadata.
    Requirement 10.4: Parameterized statements only ($1, $2, ... placeholders).
    Requirement 10.5: Returns typed RasterMetadata models.
    """

    def __init__(self, connection: Any) -> None:
        """
        Args:
            connection: An ``asyncpg.Connection`` or ``asyncpg.Pool`` instance.
        """
        self._conn = connection

    # ------------------------------------------------------------------ Read operations ------------------------------------------------------------------

    async def find_by_id(self, raster_id: str) -> Optional[RasterMetadata]:
        """Return the raster with the given UUID, or None if not found.

        Args:
            raster_id: UUID string of the raster asset.

        Returns:
            A ``RasterMetadata`` instance, or ``None`` if not found.
        """
        # Parameterized query — $1 placeholder, no string interpolation
        row = await self._conn.fetchrow(
            """
            SELECT id, file_path, file_name, raster_kind, crs, bounds_wkt,
                   resolution_x, resolution_y, width, height,
                   created_at, updated_at
            FROM raster_assets
            WHERE id = $1
            """,
            raster_id,
        )
        if row is None:
            return None
        logger.debug("find_by_id: found raster %s", raster_id)
        return _row_to_raster_metadata(row)

    async def find_by_point(self, lon: float, lat: float) -> list[RasterMetadata]:
        """Return all rasters whose spatial extent contains the given point.

        Uses ``ST_Intersects`` with ``ST_SetSRID(ST_Point($1, $2), 4326)``.
        All parameters are bound — no f-string SQL.

        Args:
            lon: Longitude in decimal degrees (WGS 84).
            lat: Latitude in decimal degrees (WGS 84).

        Returns:
            List of ``RasterMetadata`` objects ordered by ingestion date (newest first).
        """
        # $1 = lon, $2 = lat — fully parameterized PostGIS point query
        rows = await self._conn.fetch(
            """
            SELECT id, file_path, file_name, raster_kind, crs, bounds_wkt,
                   resolution_x, resolution_y, width, height,
                   created_at, updated_at
            FROM raster_assets
            WHERE ST_Intersects(
                ST_GeomFromText(bounds_wkt, 4326),
                ST_SetSRID(ST_Point($1, $2), 4326)
            )
            ORDER BY created_at DESC
            """,
            lon,
            lat,
        )
        results = [_row_to_raster_metadata(r) for r in rows]
        logger.debug("find_by_point(%.6f, %.6f): %d result(s)", lon, lat, len(results))
        return results

    async def find_by_bbox(
        self,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
    ) -> list[RasterMetadata]:
        """Return all rasters that intersect the given bounding box.

        Uses ``ST_Intersects`` with ``ST_MakeEnvelope($1, $2, $3, $4, 4326)``.
        All parameters are bound — no f-string SQL.

        Args:
            min_lon: Western boundary longitude (WGS 84).
            min_lat: Southern boundary latitude (WGS 84).
            max_lon: Eastern boundary longitude (WGS 84).
            max_lat: Northern boundary latitude (WGS 84).

        Returns:
            List of ``RasterMetadata`` objects ordered by ingestion date (newest first).
        """
        west, south, east, north = _normalized_bounds(min_lon, min_lat, max_lon, max_lat)

        # $1=west, $2=south, $3=east, $4=north — fully parameterized bbox query
        rows = await self._conn.fetch(
            """
            SELECT id, file_path, file_name, raster_kind, crs, bounds_wkt,
                   resolution_x, resolution_y, width, height,
                   created_at, updated_at
            FROM raster_assets
            WHERE ST_Intersects(
                ST_GeomFromText(bounds_wkt, 4326),
                ST_MakeEnvelope($1, $2, $3, $4, 4326)
            )
            ORDER BY created_at DESC
            """,
            west,
            south,
            east,
            north,
        )
        results = [_row_to_raster_metadata(r) for r in rows]
        logger.debug(
            "find_by_bbox(%.4f,%.4f,%.4f,%.4f): %d result(s)",
            west, south, east, north, len(results),
        )
        return results

    # ------------------------------------------------------------------ Write operations ------------------------------------------------------------------

    async def insert_metadata(self, metadata: RasterMetadata) -> RasterMetadata:
        """Insert a new raster metadata record into the catalog.

        If a record with the same ``file_path`` already exists, raises
        ``ValueError``.

        All values are passed as positional bound parameters — no raw SQL
        string interpolation.

        Args:
            metadata: Fully populated ``RasterMetadata`` instance.  If
                ``raster_id`` is empty, a new UUID is generated.

        Returns:
            The inserted ``RasterMetadata`` with ``raster_id`` and
            ``upload_date`` populated from the database.

        Raises:
            ValueError: If a record with the same ``file_path`` already exists.
            RuntimeError: On any database error (original exception is chained).
        """
        raster_id = metadata.raster_id or str(uuid4())

        # Check for duplicate path — parameterized SELECT
        existing = await self._conn.fetchrow(
            "SELECT id FROM raster_assets WHERE file_path = $1",
            metadata.file_path,
        )
        if existing is not None:
            raise ValueError(
                f"A raster with file_path '{metadata.file_path}' already exists "
                f"(id={existing['id']}). Use update_metadata() to modify it."
            )

        try:
            # Fully parameterized INSERT — $1..$9 positional placeholders
            row = await self._conn.fetchrow(
                """
                INSERT INTO raster_assets (
                    id, file_path, file_name, raster_kind, crs, bounds_wkt,
                    resolution_x, resolution_y, width, height
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING id, file_path, file_name, raster_kind, crs, bounds_wkt,
                          resolution_x, resolution_y, width, height,
                          created_at, updated_at
                """,
                raster_id,
                metadata.file_path,
                metadata.file_name,
                metadata.kind.value,
                metadata.crs,
                metadata.bbox.to_wkt_polygon(),
                metadata.resolution_x,
                metadata.resolution_y,
                metadata.width,
                metadata.height,
            )
            logger.info(
                "insert_metadata: inserted raster %s (%s)", raster_id, metadata.file_name
            )
            return _row_to_raster_metadata(row)
        except Exception as exc:
            raise RuntimeError(f"insert_metadata failed: {exc}") from exc

    async def update_metadata(
        self,
        raster_id: str,
        metadata: RasterMetadata,
    ) -> Optional[RasterMetadata]:
        """Update an existing raster metadata record.

        Only mutable fields are updated: ``crs``, ``bbox``, ``resolution_x``,
        ``resolution_y``, ``width``, ``height``, ``kind``.

        All values are passed as positional bound parameters — no raw SQL
        string interpolation.

        Args:
            raster_id: UUID of the record to update.
            metadata: ``RasterMetadata`` carrying the new field values.

        Returns:
            The updated ``RasterMetadata``, or ``None`` if ``raster_id`` was not found.

        Raises:
            RuntimeError: On any database error (original exception is chained).
        """
        try:
            # Fully parameterized UPDATE — $1..$7 positional placeholders
            row = await self._conn.fetchrow(
                """
                UPDATE raster_assets
                SET crs          = $1,
                    bounds_wkt   = $2,
                    resolution_x = $3,
                    resolution_y = $4,
                    width        = $5,
                    height       = $6,
                    raster_kind  = $7,
                    updated_at   = NOW()
                WHERE id = $8
                RETURNING id, file_path, file_name, raster_kind, crs, bounds_wkt,
                          resolution_x, resolution_y, width, height,
                          created_at, updated_at
                """,
                metadata.crs,
                metadata.bbox.to_wkt_polygon(),
                metadata.resolution_x,
                metadata.resolution_y,
                metadata.width,
                metadata.height,
                metadata.kind.value,
                raster_id,
            )
            if row is None:
                logger.warning("update_metadata: raster %s not found", raster_id)
                return None
            logger.info("update_metadata: updated raster %s", raster_id)
            return _row_to_raster_metadata(row)
        except Exception as exc:
            raise RuntimeError(f"update_metadata failed: {exc}") from exc


__all__ = ["RasterRepository", "AsyncRasterRepository"]
