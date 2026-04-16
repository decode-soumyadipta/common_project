from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from offline_gis_app.api.schemas import RegisterRasterRequest
from offline_gis_app.db.session import get_session
from offline_gis_app.services.ingest_service import register_raster
from offline_gis_app.services.metadata_extractor import MetadataExtractorError


router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/register")
def register(request: RegisterRasterRequest, session: Session = Depends(get_session)) -> dict:
    path = Path(request.path)
    try:
        return register_raster(path, session)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MetadataExtractorError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

