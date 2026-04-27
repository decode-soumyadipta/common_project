from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from core_shared.ingestion.services.metadata_extractor import MetadataExtractorError
from core_shared.ingestion.services.profile_service import sample_profile
from server_vm.server_backend.schemas import ProfileRequest


def elevation_profile_from_request(request: ProfileRequest) -> dict:
    """Compute a sampled elevation profile for an API request."""
    points = [(point.lon, point.lat) for point in request.line_points]
    try:
        values = sample_profile(Path(request.path), points, request.samples)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, MetadataExtractorError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"values": values, "samples": request.samples}


__all__ = ["elevation_profile_from_request"]
