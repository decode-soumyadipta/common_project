import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from platform_core.db.session import get_session
from platform_core.db.models import RasterAsset
from urllib.parse import quote

from server_gateway.api.schemas import (
    CoordinateSearchRequest,
    BBoxSearchRequest,
    PolygonSearchRequest,
)

router = APIRouter(prefix="/search", tags=["search"])
logger = logging.getLogger("gateway.search")


@router.get("/assets")
def list_assets(request: Request, session: Session = Depends(get_session)):
    from sqlalchemy import select

    try:
        stmt = select(RasterAsset).order_by(RasterAsset.created_at.desc())
        assets = session.scalars(stmt).all()
        
        # Use the current request base_url to ensure the tile_url is absolute and offline-safe
        base_url = str(request.base_url).rstrip("/")
        
        # Return serialized asset data
        return [
            {
                "id": a.id,
                "file_path": a.file_path,
                "file_name": a.file_name,
                "kind": a.raster_kind.value,
                "tile_url": f"{base_url}/proxy/tile/cog/tiles/{{z}}/{{x}}/{{y}}?url={quote(a.file_path)}",
                "created_at": a.created_at.isoformat(),
                "crs": a.crs,
                "bounds_wkt": a.bounds_wkt,
            }
            for a in assets
        ]
    except Exception as e:
        logger.error("Search failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch assets")


@router.post("/assets")
def search_assets(request: Request, query: dict, session: Session = Depends(get_session)):
    # Placeholder for advanced spatial search
    return list_assets(request, session)


@router.post("/point")
def search_point(
    request: Request, payload: CoordinateSearchRequest, session: Session = Depends(get_session)
):
    """Search for assets overlapping a specific point (placeholder)."""
    return list_assets(request, session)


@router.post("/bbox")
def search_bbox(request: Request, payload: BBoxSearchRequest, session: Session = Depends(get_session)):
    """Search for assets overlapping a bounding box (placeholder)."""
    return list_assets(request, session)


@router.post("/polygon")
def search_polygon(
    request: Request, payload: PolygonSearchRequest, session: Session = Depends(get_session)
):
    """Search for assets overlapping a drawn polygon (placeholder)."""
    return list_assets(request, session)
