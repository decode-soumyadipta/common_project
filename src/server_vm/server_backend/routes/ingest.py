from pathlib import Path
from dataclasses import asdict
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from server_vm.server_backend.schemas import (
    IngestJobResponse,
    IngestQueueRequest,
    RegisterRasterRequest,
)
from core_shared.db.session import get_session
from core_shared.ingestion.services.ingest_queue_service import (
    ingest_queue_service,
)
from core_shared.ingestion.services.ingest_service import register_raster
from core_shared.ingestion.services.metadata_extractor import (
    MetadataExtractorError,
)


router = APIRouter(prefix="/ingest", tags=["ingest"])
LOGGER = logging.getLogger("server.routes.ingest")


@router.post("/register")
def register(
    request: RegisterRasterRequest, session: Session = Depends(get_session)
) -> dict:
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
        return _to_job_response(view)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Failed to queue ingest paths count=%s", len(request.paths))
        raise HTTPException(
            status_code=500, detail=f"Queue ingest failed: {exc}"
        ) from exc


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
