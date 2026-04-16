from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from offline_gis_app.db.catalog import CatalogRepository
from offline_gis_app.db.session import get_session
from offline_gis_app.services.tile_url_builder import build_xyz_url


router = APIRouter(prefix="/search", tags=["search"])


@router.get("/assets")
def list_assets(session: Session = Depends(get_session)) -> list[dict]:
    repo = CatalogRepository(session)
    return [
        {
            "id": item.id,
            "file_name": item.file_name,
            "file_path": item.file_path,
            "kind": item.raster_kind.value,
            "crs": item.crs,
            "bounds_wkt": item.bounds_wkt,
            "tile_url": build_xyz_url(item.file_path),
        }
        for item in repo.list_assets()
    ]
