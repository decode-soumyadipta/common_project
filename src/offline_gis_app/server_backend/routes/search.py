from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from offline_gis_app.server_backend.schemas import BBoxSearchRequest, CoordinateSearchRequest, PolygonSearchRequest
from offline_gis_app.server_backend.catalog.catalog_repository import CatalogRepository
from offline_gis_app.db.models import RasterAsset
from offline_gis_app.db.session import get_session
from offline_gis_app.server_ingestion.services.tile_url_builder import build_xyz_url


router = APIRouter(prefix="/search", tags=["search"])


@router.get("/assets")
def list_assets(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """List all registered assets in descending creation order."""
    repo = CatalogRepository(session)
    return [_serialize_asset(item) for item in repo.list_assets()]


@router.post("/point")
def search_by_point(request: CoordinateSearchRequest, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Return assets whose bounds intersect the provided lon/lat point."""
    repo = CatalogRepository(session)
    filtered = repo.search_assets_by_point(request.lon, request.lat)
    return [_serialize_asset(item) for item in filtered]


@router.post("/bbox")
def search_by_bbox(request: BBoxSearchRequest, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Return assets whose bounds intersect the supplied bounding box."""
    repo = CatalogRepository(session)
    filtered = repo.search_assets_by_bbox(
        west=request.west,
        south=request.south,
        east=request.east,
        north=request.north,
    )
    return [_serialize_asset(item) for item in filtered]


@router.post("/polygon")
def search_by_polygon(request: PolygonSearchRequest, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Return assets intersecting a polygon, optionally buffered in meters."""
    repo = CatalogRepository(session)
    points = [(point.lon, point.lat) for point in request.points]
    filtered = repo.search_assets_by_polygon(
        points,
        buffer_meters=request.buffer_meters,
    )
    return [_serialize_asset(item) for item in filtered]


def _serialize_asset(item: RasterAsset) -> dict[str, Any]:
    """Convert a raster asset ORM object into a response-ready dictionary."""
    created_at = getattr(item, "created_at", None)
    return {
        "id": item.id,
        "file_name": item.file_name,
        "file_path": item.file_path,
        "kind": item.raster_kind.value,
        "crs": item.crs,
        "bounds_wkt": item.bounds_wkt,
        "tile_url": build_xyz_url(item.file_path),
        "created_at": created_at.isoformat() if created_at else None,
    }
