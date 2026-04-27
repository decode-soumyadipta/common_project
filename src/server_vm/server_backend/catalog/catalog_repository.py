from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from core_shared.db.models import RasterAsset
from core_shared.ingestion.services.metadata_models import RasterMetadata
from core_shared.utils.geometry import Bounds, parse_bounds_wkt_polygon


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
                    ST_MakeEnvelope(:lon, :lat, :lon, :lat, 4326)
                )
                AND ST_Intersects(
                    ST_GeomFromText(bounds_wkt, 4326),
                    ST_SetSRID(ST_Point(:lon, :lat), 4326)
                )
                ORDER BY created_at DESC
                """
            )
            ids = self._select_asset_ids(stmt, {"lon": lon, "lat": lat})
            return self._load_assets_by_ids(ids)
        # Optimized memory-efficient search for SQLite without loading full ORM objects
        stmt = select(RasterAsset.id, RasterAsset.bounds_wkt).order_by(
            RasterAsset.created_at.desc()
        )
        matching_ids = []
        for asset_id, wkt in self._session.execute(stmt):
            try:
                parsed_bounds = parse_bounds_wkt_polygon(wkt)
                asset_box = _SimpleBounds(
                    parsed_bounds.min_x,
                    parsed_bounds.min_y,
                    parsed_bounds.max_x,
                    parsed_bounds.max_y,
                )
                if asset_box.contains(lon, lat):
                    matching_ids.append(asset_id)
            except Exception:
                pass

        return self._load_assets_by_ids(matching_ids)

    def search_assets_by_bbox(
        self, west: float, south: float, east: float, north: float
    ) -> list[RasterAsset]:
        """Find assets that intersect a bounding box."""
        query_west, query_south, query_east, query_north = _normalized_bounds(
            west, south, east, north
        )

        if self._is_postgresql():
            stmt = text(
                """
                SELECT id
                FROM raster_assets
                WHERE ST_Intersects(
                    ST_GeomFromText(bounds_wkt, 4326),
                    ST_MakeEnvelope(:west, :south, :east, :north, 4326)
                )
                AND ST_Intersects(
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

        # Optimized memory-efficient search for SQLite without loading full ORM objects
        stmt = select(RasterAsset.id, RasterAsset.bounds_wkt).order_by(
            RasterAsset.created_at.desc()
        )
        matching_ids = []
        for asset_id, wkt in self._session.execute(stmt):
            try:
                parsed_bounds = parse_bounds_wkt_polygon(wkt)
                asset_box = _SimpleBounds(
                    parsed_bounds.min_x,
                    parsed_bounds.min_y,
                    parsed_bounds.max_x,
                    parsed_bounds.max_y,
                )
                if asset_box.intersects(query):
                    matching_ids.append(asset_id)
            except Exception:
                pass

        return self._load_assets_by_ids(matching_ids)

    def search_assets_by_polygon(
        self, points: list[tuple[float, float]], buffer_meters: float = 0.0
    ) -> list[RasterAsset]:
        """Find assets that intersect a polygon, optionally buffered in meters."""
        polygon_wkt = _polygon_to_wkt(points)
        if self._is_postgresql():
            stmt = text(
                """
                WITH query_geom AS (
                    SELECT CASE
                        WHEN :buffer_meters > 0
                        THEN ST_Buffer(ST_GeomFromText(:polygon_wkt, 4326)::geography, :buffer_meters)::geometry
                        ELSE ST_GeomFromText(:polygon_wkt, 4326)
                    END AS geom
                )
                SELECT id
                FROM raster_assets
                CROSS JOIN query_geom
                WHERE ST_Intersects(ST_GeomFromText(bounds_wkt, 4326), ST_Envelope(query_geom.geom))
                AND ST_Intersects(ST_GeomFromText(bounds_wkt, 4326), query_geom.geom)
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

        # Optimized memory-efficient search for SQLite without loading full ORM objects
        stmt = select(RasterAsset.id, RasterAsset.bounds_wkt).order_by(
            RasterAsset.created_at.desc()
        )
        matching_ids = []
        for asset_id, wkt in self._session.execute(stmt):
            try:
                parsed_bounds = parse_bounds_wkt_polygon(wkt)
                asset_box = _SimpleBounds(
                    parsed_bounds.min_x,
                    parsed_bounds.min_y,
                    parsed_bounds.max_x,
                    parsed_bounds.max_y,
                )
                if asset_box.intersects(fallback):
                    matching_ids.append(asset_id)
            except Exception:
                pass

        return self._load_assets_by_ids(matching_ids)

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


def _simple_polygon_bounds(
    points: list[tuple[float, float]], buffer_meters: float
) -> _SimpleBounds:
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


def _normalized_bounds(
    west: float, south: float, east: float, north: float
) -> tuple[float, float, float, float]:
    """Return bounds with guaranteed west<=east and south<=north ordering."""
    return min(west, east), min(south, north), max(west, east), max(south, north)
