from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from core_shared.ingestion.services.ingest_queue_service import ingest_queue_service
from core_shared.ingestion.services.ingest_service import register_raster
from core_shared.ingestion.services.metadata_extractor import MetadataExtractorError
from server_vm.server_backend.schemas import IngestJobResponse, IngestQueueRequest, RegisterRasterRequest


def register_raster_from_request(request: RegisterRasterRequest, session: Session) -> dict:
    """Register a raster and map service-layer failures into API-safe exceptions."""
    path = Path(request.path)
    try:
        return register_raster(path, session)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MetadataExtractorError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def enqueue_ingest_from_request(request: IngestQueueRequest) -> IngestJobResponse:
    """Queue ingest paths and return normalized API model."""
    try:
        return _to_job_response(ingest_queue_service.enqueue_paths(request.paths))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def get_ingest_job(job_id: str) -> IngestJobResponse:
    """Fetch ingest job status by id."""
    view = ingest_queue_service.get_job(job_id)
    if view is None:
        raise HTTPException(status_code=404, detail=f"Ingest job not found: {job_id}")
    return _to_job_response(view)


def resume_ingest_job(job_id: str) -> IngestJobResponse:
    """Resume a recoverable ingest job by id."""
    try:
        return _to_job_response(ingest_queue_service.resume_job(job_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _to_job_response(view) -> IngestJobResponse:
    return IngestJobResponse(**asdict(view))


__all__ = [
    "enqueue_ingest_from_request",
    "get_ingest_job",
    "register_raster_from_request",
    "resume_ingest_job",
]
