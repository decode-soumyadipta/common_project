from datetime import datetime
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from offline_gis_app.db.models import IngestJob, IngestJobItem, IngestJobItemStatus, IngestJobStatus, RasterAsset
from offline_gis_app.services.metadata_models import RasterMetadata
from offline_gis_app.utils.geometry import Bounds, parse_bounds_wkt_polygon


class CatalogRepository:
    """Catalog data access for raster assets and spatial queries."""

    def __init__(self, session: Session):
        self._session = session

    def upsert_asset(self, metadata: RasterMetadata) -> RasterAsset:
        existing = self.get_by_path(str(metadata.file_path))
        if existing:
            existing.crs = metadata.crs
            existing.bounds_wkt = metadata.bounds.to_wkt_polygon()
            existing.resolution_x = metadata.resolution_x
            existing.resolution_y = metadata.resolution_y
            existing.width = metadata.width
            existing.height = metadata.height
            existing.raster_kind = metadata.kind
            self._session.add(existing)
            self._session.commit()
            self._session.refresh(existing)
            return existing

        asset = RasterAsset(
            id=str(uuid4()),
            file_path=str(metadata.file_path),
            file_name=metadata.file_name,
            raster_kind=metadata.kind,
            crs=metadata.crs,
            bounds_wkt=metadata.bounds.to_wkt_polygon(),
            resolution_x=metadata.resolution_x,
            resolution_y=metadata.resolution_y,
            width=metadata.width,
            height=metadata.height,
        )
        self._session.add(asset)
        self._session.commit()
        self._session.refresh(asset)
        return asset

    def get_by_path(self, file_path: str) -> RasterAsset | None:
        """Return an asset by storage path."""
        stmt = select(RasterAsset).where(RasterAsset.file_path == file_path)
        return self._session.scalar(stmt)

    def list_assets(self) -> list[RasterAsset]:
        """List assets in reverse creation order."""
        stmt = select(RasterAsset).order_by(RasterAsset.created_at.desc())
        return list(self._session.scalars(stmt))

    def search_assets_by_point(self, lon: float, lat: float) -> list[RasterAsset]:
        """Find assets that intersect a point."""
        if self._is_postgresql():
            stmt = text(
                """
                SELECT id
                FROM raster_assets
                WHERE ST_Intersects(
                    ST_GeomFromText(bounds_wkt, 4326),
                    ST_SetSRID(ST_Point(:lon, :lat), 4326)
                )
                ORDER BY created_at DESC
                """
            )
            ids = self._select_asset_ids(stmt, {"lon": lon, "lat": lat})
            return self._load_assets_by_ids(ids)
        return [asset for asset in self.list_assets() if _asset_bounds(asset).contains(lon, lat)]

    def search_assets_by_bbox(self, west: float, south: float, east: float, north: float) -> list[RasterAsset]:
        """Find assets that intersect a bounding box."""
        query_west, query_south, query_east, query_north = _normalized_bounds(west, south, east, north)

        if self._is_postgresql():
            stmt = text(
                """
                SELECT id
                FROM raster_assets
                WHERE ST_Intersects(
                    ST_GeomFromText(bounds_wkt, 4326),
                    ST_MakeEnvelope(:west, :south, :east, :north, 4326)
                )
                ORDER BY created_at DESC
                """
            )
            ids = self._select_asset_ids(
                stmt,
                {
                    "west": query_west,
                    "south": query_south,
                    "east": query_east,
                    "north": query_north,
                },
            )
            return self._load_assets_by_ids(ids)

        query = _SimpleBounds(query_west, query_south, query_east, query_north)
        return [asset for asset in self.list_assets() if _asset_bounds(asset).intersects(query)]

    def search_assets_by_polygon(self, points: list[tuple[float, float]], buffer_meters: float = 0.0) -> list[RasterAsset]:
        """Find assets that intersect a polygon, optionally buffered in meters."""
        polygon_wkt = _polygon_to_wkt(points)
        if self._is_postgresql():
            stmt = text(
                """
                SELECT id
                FROM raster_assets
                WHERE ST_Intersects(
                    ST_GeomFromText(bounds_wkt, 4326),
                    CASE
                        WHEN :buffer_meters > 0
                        THEN ST_Buffer(ST_GeomFromText(:polygon_wkt, 4326)::geography, :buffer_meters)::geometry
                        ELSE ST_GeomFromText(:polygon_wkt, 4326)
                    END
                )
                ORDER BY created_at DESC
                """
            )
            ids = self._select_asset_ids(
                stmt,
                {
                    "polygon_wkt": polygon_wkt,
                    "buffer_meters": float(buffer_meters),
                },
            )
            return self._load_assets_by_ids(ids)

        fallback = _simple_polygon_bounds(points, buffer_meters)
        return [asset for asset in self.list_assets() if _asset_bounds(asset).intersects(fallback)]

    def _is_postgresql(self) -> bool:
        bind = self._session.bind
        return bool(bind and bind.dialect.name == "postgresql")

    def _select_asset_ids(self, stmt, params: dict[str, float | str]) -> list[str]:
        return [str(row[0]) for row in self._session.execute(stmt, params)]

    def _load_assets_by_ids(self, ids: list[str]) -> list[RasterAsset]:
        if not ids:
            return []
        stmt = select(RasterAsset).where(RasterAsset.id.in_(ids))
        rows = list(self._session.scalars(stmt))
        by_id = {row.id: row for row in rows}
        return [by_id[item_id] for item_id in ids if item_id in by_id]


class IngestJobRepository:
    """Persistence helper for queued ingest jobs and items."""

    def __init__(self, session: Session):
        self._session = session

    def create_job(self, file_paths: list[str]) -> IngestJob:
        job = IngestJob(
            id=str(uuid4()),
            status=IngestJobStatus.QUEUED,
            total_items=len(file_paths),
            processed_items=0,
            failed_items=0,
            checkpoint_item_index=0,
        )
        self._session.add(job)
        self._session.flush()

        for index, path in enumerate(file_paths, start=1):
            item = IngestJobItem(
                id=str(uuid4()),
                job_id=job.id,
                item_index=index,
                file_path=path,
                status=IngestJobItemStatus.PENDING,
                attempts=0,
            )
            self._session.add(item)

        self._session.commit()
        self._session.refresh(job)
        return job

    def get_job(self, job_id: str) -> IngestJob | None:
        stmt = select(IngestJob).where(IngestJob.id == job_id)
        return self._session.scalar(stmt)

    def list_recoverable_jobs(self) -> list[IngestJob]:
        stmt = (
            select(IngestJob)
            .where(IngestJob.status.in_([IngestJobStatus.QUEUED, IngestJobStatus.RUNNING, IngestJobStatus.PAUSED]))
            .order_by(IngestJob.created_at.asc())
        )
        return list(self._session.scalars(stmt))

    def list_pending_or_failed_items(self, job_id: str) -> list[IngestJobItem]:
        stmt = (
            select(IngestJobItem)
            .where(
                IngestJobItem.job_id == job_id,
                IngestJobItem.status.in_([IngestJobItemStatus.PENDING, IngestJobItemStatus.FAILED]),
            )
            .order_by(IngestJobItem.item_index.asc())
        )
        return list(self._session.scalars(stmt))

    def get_item(self, item_id: str) -> IngestJobItem | None:
        stmt = select(IngestJobItem).where(IngestJobItem.id == item_id)
        return self._session.scalar(stmt)

    def mark_job_running(self, job: IngestJob) -> None:
        now = datetime.utcnow()
        job.status = IngestJobStatus.RUNNING
        if job.started_at is None:
            job.started_at = now
        job.updated_at = now
        self._session.add(job)
        self._session.commit()

    def set_job_status(self, job: IngestJob, status: IngestJobStatus, *, last_error: str | None = None) -> None:
        job.status = status
        job.last_error = last_error
        job.updated_at = datetime.utcnow()
        self._session.add(job)
        self._session.commit()

    def mark_job_checkpoint(self, job: IngestJob, checkpoint_item_index: int) -> None:
        now = datetime.utcnow()
        job.checkpoint_item_index = checkpoint_item_index
        job.last_checkpoint_at = now
        job.updated_at = now
        self._session.add(job)
        self._session.commit()

    def mark_job_terminal(self, job: IngestJob, status: IngestJobStatus, last_error: str | None = None) -> None:
        now = datetime.utcnow()
        job.status = status
        job.last_error = last_error
        job.completed_at = now
        job.updated_at = now
        self._session.add(job)
        self._session.commit()

    def update_item_status(
        self,
        item: IngestJobItem,
        status: IngestJobItemStatus,
        *,
        attempts: int | None = None,
        last_error: str | None = None,
        asset_id: str | None = None,
    ) -> None:
        item.status = status
        if attempts is not None:
            item.attempts = attempts
        item.last_error = last_error
        item.asset_id = asset_id
        item.updated_at = datetime.utcnow()
        self._session.add(item)
        self._session.commit()

    def update_item_status_by_id(
        self,
        item_id: str,
        status: IngestJobItemStatus,
        *,
        attempts: int | None = None,
        last_error: str | None = None,
        asset_id: str | None = None,
    ) -> None:
        item = self.get_item(item_id)
        if item is None:
            return
        self.update_item_status(
            item,
            status,
            attempts=attempts,
            last_error=last_error,
            asset_id=asset_id,
        )

    def refresh_job_counters(self, job: IngestJob) -> None:
        stmt = select(IngestJobItem.status).where(IngestJobItem.job_id == job.id)
        statuses = list(self._session.scalars(stmt))
        job.processed_items = sum(1 for status in statuses if status == IngestJobItemStatus.SUCCEEDED)
        job.failed_items = sum(1 for status in statuses if status == IngestJobItemStatus.FAILED)
        job.total_items = len(statuses)
        job.updated_at = datetime.utcnow()
        self._session.add(job)
        self._session.commit()


class _SimpleBounds:
    """Small axis-aligned bounds helper used by non-PostGIS fallback search."""

    def __init__(self, west: float, south: float, east: float, north: float):
        self.west = west
        self.south = south
        self.east = east
        self.north = north

    def contains(self, lon: float, lat: float) -> bool:
        return self.west <= lon <= self.east and self.south <= lat <= self.north

    def intersects(self, other: "_SimpleBounds") -> bool:
        return not (
            self.east < other.west
            or self.west > other.east
            or self.north < other.south
            or self.south > other.north
        )


def _asset_bounds(asset: RasterAsset) -> _SimpleBounds:
    """Parse stored asset WKT bounds into an axis-aligned bounds object."""
    parsed: Bounds = parse_bounds_wkt_polygon(asset.bounds_wkt)
    return _SimpleBounds(parsed.min_x, parsed.min_y, parsed.max_x, parsed.max_y)


def _polygon_to_wkt(points: list[tuple[float, float]]) -> str:
    """Build a closed WKT polygon from lon/lat vertices."""
    cleaned = [(float(lon), float(lat)) for lon, lat in points]
    if len(cleaned) < 3:
        raise ValueError("Polygon search requires at least 3 points")
    if cleaned[0] != cleaned[-1]:
        cleaned.append(cleaned[0])
    point_tokens = [f"{lon} {lat}" for lon, lat in cleaned]
    return f"POLYGON(({','.join(point_tokens)}))"


def _simple_polygon_bounds(points: list[tuple[float, float]], buffer_meters: float) -> _SimpleBounds:
    """Approximate polygon search with bounds-only fallback for non-PostGIS engines."""
    lons = [float(lon) for lon, _lat in points]
    lats = [float(lat) for _lon, lat in points]
    west = min(lons)
    east = max(lons)
    south = min(lats)
    north = max(lats)
    if buffer_meters > 0:
        lat_offset = buffer_meters / 111_320.0
        lon_offset = buffer_meters / 111_320.0
        west -= lon_offset
        east += lon_offset
        south -= lat_offset
        north += lat_offset
    return _SimpleBounds(west, south, east, north)


def _normalized_bounds(west: float, south: float, east: float, north: float) -> tuple[float, float, float, float]:
    """Return bounds with guaranteed west<=east and south<=north ordering."""
    return min(west, east), min(south, north), max(west, east), max(south, north)

