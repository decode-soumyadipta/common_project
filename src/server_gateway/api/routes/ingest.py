import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from platform_core.schema.models import IngestJobResponse, IngestQueueRequest, RegisterRasterRequest
from platform_core.db.session import get_session
from platform_core.ingestion.repository.ingest_job_repository import IngestJobRepository

router = APIRouter(prefix="/ingest", tags=["ingest"])
logger = logging.getLogger("gateway.ingest")

@router.post("/register")
def register(request: RegisterRasterRequest, session: Session = Depends(get_session)) -> dict:
    """Register a raster metadata in the catalog."""
    from platform_core.ingestion.services.ingest_service import register_raster
    try:
        return register_raster(request.path, session)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/queue", response_model=IngestJobResponse)
def enqueue_ingest(request: IngestQueueRequest, session: Session = Depends(get_session)) -> IngestJobResponse:
    """Queue raster paths. Server B (Processor) will pick these up from the DB."""
    repo = IngestJobRepository(session)
    try:
        # We just create the job record. 
        # In a distributed setup, the worker on Server B polls for QUEUED jobs.
        job = repo.create_job(request.paths)
        return IngestJobResponse(
            id=job.id,
            status=job.status.value,
            total_items=job.total_items,
            processed_items=0,
            failed_items=0,
            progress_percent=0
        )
    except Exception as e:
        logger.exception("Failed to queue ingest")
        raise HTTPException(status_code=500, detail=f"Queue failed: {e}")

@router.get("/jobs/{job_id}", response_model=IngestJobResponse)
def get_job_status(job_id: str, session: Session = Depends(get_session)) -> IngestJobResponse:
    repo = IngestJobRepository(session)
    job = repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    repo.refresh_job_counters(job)
    return IngestJobResponse(
        id=job.id,
        status=job.status.value,
        total_items=job.total_items,
        processed_items=job.processed_items,
        failed_items=job.failed_items,
        progress_percent=int((job.processed_items / job.total_items) * 100) if job.total_items > 0 else 0
    )
