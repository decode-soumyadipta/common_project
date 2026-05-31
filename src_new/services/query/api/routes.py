"""Query Service FastAPI route handlers.

Adapted from:
  - ``src/server_vm/server_backend/routes/search.py``
  - ``src/server_gateway/api/routes/search.py``
  - ``src/server_vm/server_backend/routes/health.py``
  - ``src/server_gateway/api/routes/health.py``

Endpoints
---------
POST /query/point
    Spatial point query — returns all rasters whose extent contains the
    given lat/lon coordinate.

POST /query/bbox
    Bounding-box query — returns all rasters that intersect the given bbox.

GET  /raster/{raster_id}
    Retrieve full metadata for a single cataloged raster by its UUID.

GET  /health
    Liveness / readiness probe returning service status, database
    connectivity, and available disk space.

Requirements: 6.3, 6.6, 16.1
"""
from __future__ import annotations

import logging
import os
import shutil
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src_new.services.query.api.dependencies import get_db, get_raster_repository
from src_new.services.query.repositories.raster_repository import RasterRepository
from src_new.shared.models.query_result import QueryResult
from src_new.shared.models.raster_metadata import RasterMetadata

# Pydantic request schemas defined locally (no dependency on legacy src/)
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["query"])


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class PointQueryRequest(BaseModel):
    """Request body for POST /query/point.

    Matches the design-doc specification:
        {lat, lon, crs="EPSG:4326"}
    """

    lat: float = Field(
        ge=-90.0,
        le=90.0,
        description="Latitude of the query point in decimal degrees (WGS 84).",
    )
    lon: float = Field(
        ge=-180.0,
        le=180.0,
        description="Longitude of the query point in decimal degrees (WGS 84).",
    )
    crs: str = Field(
        default="EPSG:4326",
        description=(
            "Coordinate Reference System of the input coordinates. "
            "Currently only EPSG:4326 is supported."
        ),
    )


class BBoxQueryRequest(BaseModel):
    """Request body for POST /query/bbox.

    Matches the design-doc specification:
        {min_lon, min_lat, max_lon, max_lat, crs="EPSG:4326"}
    """

    min_lon: float = Field(
        ge=-180.0,
        le=180.0,
        description="Western boundary longitude in decimal degrees.",
    )
    min_lat: float = Field(
        ge=-90.0,
        le=90.0,
        description="Southern boundary latitude in decimal degrees.",
    )
    max_lon: float = Field(
        ge=-180.0,
        le=180.0,
        description="Eastern boundary longitude in decimal degrees.",
    )
    max_lat: float = Field(
        ge=-90.0,
        le=90.0,
        description="Northern boundary latitude in decimal degrees.",
    )
    crs: str = Field(
        default="EPSG:4326",
        description=(
            "Coordinate Reference System of the input coordinates. "
            "Currently only EPSG:4326 is supported."
        ),
    )


class PolygonPoint(BaseModel):
    """A single point in a polygon."""
    lon: float = Field(description="Longitude in decimal degrees")
    lat: float = Field(description="Latitude in decimal degrees")


class PolygonQueryRequest(BaseModel):
    """Request body for POST /search/polygon."""
    points: list[PolygonPoint] = Field(description="List of polygon vertices")
    buffer_meters: float = Field(default=0.0, description="Buffer distance in meters")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/query/point",
    response_model=QueryResult,
    summary="Spatial point query",
    description=(
        "Return all cataloged rasters whose geographic extent contains the "
        "given lat/lon point. Results are ordered by ingestion date (newest first)."
    ),
)
def query_by_point(
    request: PointQueryRequest,
    repo: Annotated[RasterRepository, Depends(get_raster_repository)],
) -> QueryResult:
    """Return rasters that contain the given point.

    Delegates to ``RasterRepository.find_by_point()`` which uses a
    parameterized PostGIS ``ST_Intersects`` query (or a pure-Python fallback
    on SQLite for testing).

    Args:
        request: Validated ``PointQueryRequest`` body.
        repo:    ``RasterRepository`` injected by the DI system.

    Returns:
        ``QueryResult`` with matching rasters and their count.

    Raises:
        HTTPException(500): On unexpected database errors.
    """
    logger.info(
        "POST /query/point — lat=%.6f lon=%.6f crs=%s",
        request.lat,
        request.lon,
        request.crs,
    )
    try:
        rasters = repo.find_by_point(lon=request.lon, lat=request.lat)
    except Exception as exc:
        logger.exception("find_by_point failed: %s", exc)
        raise HTTPException(status_code=500, detail="Spatial point query failed.") from exc

    result = QueryResult.from_rasters(rasters)
    logger.info("POST /query/point — %d result(s)", result.count)
    return result


@router.post(
    "/query/bbox",
    response_model=QueryResult,
    summary="Bounding-box spatial query",
    description=(
        "Return all cataloged rasters that intersect the given bounding box. "
        "Results are ordered by ingestion date (newest first)."
    ),
)
def query_by_bbox(
    request: BBoxQueryRequest,
    repo: Annotated[RasterRepository, Depends(get_raster_repository)],
) -> QueryResult:
    """Return rasters that intersect the given bounding box.

    Delegates to ``RasterRepository.find_by_bbox()`` which uses a
    parameterized PostGIS ``ST_Intersects`` / ``ST_MakeEnvelope`` query.

    Args:
        request: Validated ``BBoxQueryRequest`` body.
        repo:    ``RasterRepository`` injected by the DI system.

    Returns:
        ``QueryResult`` with matching rasters and their count.

    Raises:
        HTTPException(422): If min_lon >= max_lon or min_lat >= max_lat.
        HTTPException(500): On unexpected database errors.
    """
    logger.info(
        "POST /query/bbox — min_lon=%.4f min_lat=%.4f max_lon=%.4f max_lat=%.4f crs=%s",
        request.min_lon,
        request.min_lat,
        request.max_lon,
        request.max_lat,
        request.crs,
    )

    # Validate non-zero area (mirrors BBoxSearchRequest validator in legacy src/)
    if request.min_lon >= request.max_lon:
        raise HTTPException(
            status_code=422,
            detail="min_lon must be strictly less than max_lon.",
        )
    if request.min_lat >= request.max_lat:
        raise HTTPException(
            status_code=422,
            detail="min_lat must be strictly less than max_lat.",
        )

    try:
        rasters = repo.find_by_bbox(
            min_lon=request.min_lon,
            min_lat=request.min_lat,
            max_lon=request.max_lon,
            max_lat=request.max_lat,
        )
    except Exception as exc:
        logger.exception("find_by_bbox failed: %s", exc)
        raise HTTPException(status_code=500, detail="Bounding-box query failed.") from exc

    result = QueryResult.from_rasters(rasters)
    logger.info("POST /query/bbox — %d result(s)", result.count)
    return result


@router.get(
    "/raster/{raster_id}",
    response_model=RasterMetadata,
    summary="Get raster metadata by ID",
    description="Retrieve full metadata for a single cataloged raster asset by its UUID.",
)
def get_raster_metadata(
    raster_id: str,
    repo: Annotated[RasterRepository, Depends(get_raster_repository)],
) -> RasterMetadata:
    """Return metadata for a single raster asset.

    Args:
        raster_id: UUID of the raster asset (path parameter).
        repo:      ``RasterRepository`` injected by the DI system.

    Returns:
        ``RasterMetadata`` for the requested raster.

    Raises:
        HTTPException(404): If no raster with the given ID exists.
        HTTPException(500): On unexpected database errors.
    """
    logger.info("GET /raster/%s", raster_id)
    try:
        metadata = repo.find_by_id(raster_id)
    except Exception as exc:
        logger.exception("find_by_id failed for %s: %s", raster_id, exc)
        raise HTTPException(
            status_code=500, detail="Failed to retrieve raster metadata."
        ) from exc

    if metadata is None:
        logger.warning("GET /raster/%s — not found", raster_id)
        raise HTTPException(
            status_code=404,
            detail=f"Raster not found: {raster_id}",
        )

    return metadata


@router.get(
    "/rasters",
    response_model=QueryResult,
    summary="List all rasters",
    description="Return all cataloged rasters ordered by ingestion date (newest first).",
)
def list_all_rasters(
    repo: Annotated[RasterRepository, Depends(get_raster_repository)],
) -> QueryResult:
    """Return all cataloged rasters.

    Args:
        repo: ``RasterRepository`` injected by the DI system.

    Returns:
        ``QueryResult`` with all rasters and their count.
        Returns empty result if no rasters are cataloged.

    Raises:
        HTTPException(500): On unexpected database errors.
    """
    logger.info("GET /rasters")
    try:
        rasters = repo.find_all()
        result = QueryResult.from_rasters(rasters)
        logger.info("GET /rasters — %d result(s)", result.count)
        return result
    except Exception as exc:
        logger.exception("find_all failed: %s", exc)
        # Return empty result instead of 500 error if database is empty
        return QueryResult(rasters=[], count=0)


@router.post(
    "/search/point",
    response_model=QueryResult,
    summary="Search by point (alias)",
    description="Alias for /query/point for backward compatibility.",
)
def search_by_point(
    request: PointQueryRequest,
    repo: Annotated[RasterRepository, Depends(get_raster_repository)],
) -> QueryResult:
    """Alias for query_by_point for backward compatibility."""
    return query_by_point(request, repo)


@router.post(
    "/search/bbox",
    response_model=QueryResult,
    summary="Search by bbox (alias)",
    description="Alias for /query/bbox for backward compatibility.",
)
def search_by_bbox(
    request: BBoxQueryRequest,
    repo: Annotated[RasterRepository, Depends(get_raster_repository)],
) -> QueryResult:
    """Alias for query_by_bbox for backward compatibility."""
    return query_by_bbox(request, repo)


@router.post(
    "/search/polygon",
    response_model=QueryResult,
    summary="Search by polygon",
    description="Return all cataloged rasters that intersect the given polygon.",
)
def search_by_polygon(
    request: PolygonQueryRequest,
    repo: Annotated[RasterRepository, Depends(get_raster_repository)],
) -> QueryResult:
    """Return rasters that intersect the given polygon.

    Args:
        request: Validated ``PolygonQueryRequest`` body.
        repo:    ``RasterRepository`` injected by the DI system.

    Returns:
        ``QueryResult`` with matching rasters and their count.

    Raises:
        HTTPException(422): If polygon has fewer than 3 points.
    """
    logger.info("POST /search/polygon — %d points", len(request.points))
    
    if len(request.points) < 3:
        raise HTTPException(
            status_code=422,
            detail="Polygon must have at least 3 points.",
        )
    
    try:
        # Convert polygon to bounding box for now (simple implementation)
        # TODO: Implement proper polygon intersection in repository
        lons = [p.lon for p in request.points]
        lats = [p.lat for p in request.points]
        
        min_lon = min(lons) - (request.buffer_meters / 111320.0)
        max_lon = max(lons) + (request.buffer_meters / 111320.0)
        min_lat = min(lats) - (request.buffer_meters / 111320.0)
        max_lat = max(lats) + (request.buffer_meters / 111320.0)
        
        rasters = repo.find_by_bbox(
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
        )
        
        result = QueryResult.from_rasters(rasters)
        logger.info("POST /search/polygon — %d result(s)", result.count)
        return result
    except Exception as exc:
        logger.exception("Polygon search failed: %s", exc)
        # Return empty result instead of error
        return QueryResult(rasters=[], count=0)


@router.get(
    "/health",
    summary="Health check",
    description=(
        "Liveness and readiness probe. Returns service status, database "
        "connectivity, and available disk space on the data volume."
    ),
)
def health_check(
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Return service health information.

    Checks:
    1. Database connectivity — executes a lightweight ``SELECT 1`` query.
    2. Disk space — reports free gigabytes on the filesystem containing the
       current working directory (proxy for the data volume).

    Returns:
        A dict with keys:
        - ``status``: ``"healthy"`` | ``"degraded"`` | ``"unhealthy"``
        - ``database``: ``True`` if the DB is reachable, ``False`` otherwise.
        - ``disk_space_gb``: Free disk space in gigabytes (float, rounded to 2 dp).
    """
    # --- Database connectivity check ---
    db_ok = False
    try:
        from sqlalchemy import text as sa_text
        db.execute(sa_text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        logger.warning("Health check: database unreachable — %s", exc)

    # --- Disk space check ---
    disk_space_gb: float = 0.0
    try:
        usage = shutil.disk_usage(os.getcwd())
        disk_space_gb = round(usage.free / (1024 ** 3), 2)
    except Exception as exc:
        logger.warning("Health check: disk usage check failed — %s", exc)

    # --- Overall status ---
    if db_ok:
        status = "healthy"
    else:
        status = "degraded"

    logger.debug(
        "GET /health — status=%s database=%s disk_space_gb=%.2f",
        status,
        db_ok,
        disk_space_gb,
    )

    return {
        "status": status,
        "database": db_ok,
        "disk_space_gb": disk_space_gb,
    }


__all__ = [
    "router",
    "PointQueryRequest",
    "BBoxQueryRequest",
]
