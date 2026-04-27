import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from server_vm.server_backend.schemas import (
    IngestJobResponse,
    IngestQueueRequest,
    RegisterRasterRequest,
)
from core_shared.db.session import get_session
from server_vm.api_routes.ingest import (
    enqueue_ingest_from_request,
    get_ingest_job as get_ingest_job_from_boundary,
    register_raster_from_request,
    resume_ingest_job as resume_ingest_job_from_boundary,
)


router = APIRouter(prefix="/ingest", tags=["ingest"])
LOGGER = logging.getLogger("server.routes.ingest")


@router.post("/register")
def register(
    request: RegisterRasterRequest, session: Session = Depends(get_session)
) -> dict:
    """Register a raster immediately and return the created/updated catalog asset."""
    return register_raster_from_request(request, session)


@router.post("/queue", response_model=IngestJobResponse)
def enqueue_ingest(request: IngestQueueRequest) -> IngestJobResponse:
    """Queue one or more raster paths for background ingest processing."""
    try:
        return enqueue_ingest_from_request(request)
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
    return get_ingest_job_from_boundary(job_id)


@router.post("/jobs/{job_id}/resume", response_model=IngestJobResponse)
def resume_ingest_job(job_id: str) -> IngestJobResponse:
    """Resume a recoverable ingest job."""
    return resume_ingest_job_from_boundary(job_id)
