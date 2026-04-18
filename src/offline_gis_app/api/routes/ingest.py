from pathlib import Path
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from offline_gis_app.api.schemas import IngestJobResponse, IngestQueueRequest, RegisterRasterRequest
from offline_gis_app.db.session import get_session
from offline_gis_app.services.ingest_queue_service import ingest_queue_service
from offline_gis_app.services.ingest_service import register_raster
from offline_gis_app.services.metadata_extractor import MetadataExtractorError


router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/register")
def register(request: RegisterRasterRequest, session: Session = Depends(get_session)) -> dict:
    """Register a raster immediately and return the created/updated catalog asset."""
    path = Path(request.path)
    try:
        return register_raster(path, session)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MetadataExtractorError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/queue", response_model=IngestJobResponse)
def enqueue_ingest(request: IngestQueueRequest) -> IngestJobResponse:
    """Queue one or more raster paths for background ingest processing."""
    try:
        view = ingest_queue_service.enqueue_paths(request.paths)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_job_response(view)


@router.get("/jobs/{job_id}", response_model=IngestJobResponse)
def get_ingest_job(job_id: str) -> IngestJobResponse:
    """Fetch ingest job progress and status by id."""
    view = ingest_queue_service.get_job(job_id)
    if view is None:
        raise HTTPException(status_code=404, detail=f"Ingest job not found: {job_id}")
    return _to_job_response(view)


@router.post("/jobs/{job_id}/resume", response_model=IngestJobResponse)
def resume_ingest_job(job_id: str) -> IngestJobResponse:
    """Resume a recoverable ingest job."""
    try:
        view = ingest_queue_service.resume_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_job_response(view)


def _to_job_response(view) -> IngestJobResponse:
    """Convert service view dataclass into API response model."""
    return IngestJobResponse(**asdict(view))

