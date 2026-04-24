from pathlib import Path

from fastapi import APIRouter, HTTPException

from offline_gis_app.server_backend.schemas import ProfileRequest
from offline_gis_app.server_ingestion.services.metadata_extractor import (
    MetadataExtractorError,
)
from offline_gis_app.server_ingestion.services.profile_service import sample_profile


router = APIRouter(prefix="/profile", tags=["profile"])


@router.post("/elevation")
def profile(request: ProfileRequest) -> dict:
    points = [(p.lon, p.lat) for p in request.line_points]
    try:
        values = sample_profile(Path(request.path), points, request.samples)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, MetadataExtractorError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"values": values, "samples": request.samples}
