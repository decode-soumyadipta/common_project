from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from server_vm.server_backend.schemas import (
    BBoxSearchRequest,
    CoordinateSearchRequest,
    PolygonSearchRequest,
)
from server_vm.server_backend.catalog.catalog_repository import CatalogRepository
from server_vm.server_backend.catalog.service import CatalogService
from core_shared.db.session import get_session


router = APIRouter(prefix="/search", tags=["search"])


@router.get("/assets")
def list_assets(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """List all registered assets in descending creation order."""
    service = CatalogService(CatalogRepository(session))
    return service.list_assets()


@router.post("/point")
def search_by_point(
    request: CoordinateSearchRequest, session: Session = Depends(get_session)
) -> list[dict[str, Any]]:
    """Return assets whose bounds intersect the provided lon/lat point."""
    service = CatalogService(CatalogRepository(session))
    return service.search_by_point(request.lon, request.lat)


@router.post("/bbox")
def search_by_bbox(
    request: BBoxSearchRequest, session: Session = Depends(get_session)
) -> list[dict[str, Any]]:
    """Return assets whose bounds intersect the supplied bounding box."""
    service = CatalogService(CatalogRepository(session))
    return service.search_by_bbox(
        west=request.west,
        south=request.south,
        east=request.east,
        north=request.north,
    )


@router.post("/polygon")
def search_by_polygon(
    request: PolygonSearchRequest, session: Session = Depends(get_session)
) -> list[dict[str, Any]]:
    """Return assets intersecting a polygon, optionally buffered in meters."""
    service = CatalogService(CatalogRepository(session))
    points = [(point.lon, point.lat) for point in request.points]
    return service.search_by_polygon(
        points,
        buffer_meters=request.buffer_meters,
    )
