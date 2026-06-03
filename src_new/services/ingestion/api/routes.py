"""Ingestion Service FastAPI route handlers.

Consolidated from:
  - ``src/server_vm/server_backend/routes/ingest.py``
  - ``src/server_gateway/api/routes/ingest.py``

Endpoints
---------
POST /upload
    Multipart file upload — saves the file to DATA_ROOT, runs GDAL metadata
    extraction, validates the format, and catalogs the raster in PostGIS.
    Returns ``{raster_id, status, message, bbox}``.

GET  /status/{raster_id}
    Return ingestion progress and status for a previously uploaded raster.
    Returns ``{raster_id, status, progress, error}``.

GET  /health
    Liveness / readiness probe returning service status, database
    connectivity, and available disk space.

Requirements: 6.1, 6.6, 9.6, 16.1
"""
from __future__ import annotations

import logging
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, text as sa_text
from sqlalchemy.orm import Session

from src_new.services.ingestion.api.dependencies import (
    get_data_root,
    get_db,
    get_format_handler,
    get_metadata_extractor,
    get_settings,
)
from src_new.shared.config import Settings
from src_new.shared.models.bounding_box import BoundingBox
from src_new.shared.models.raster_metadata import RasterMetadata

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingestion"])

# ---------------------------------------------------------------------------
# Supported file extensions (mirrors src_new/shared/constants.py)
# ---------------------------------------------------------------------------

_SUPPORTED_EXTENSIONS = {".tif", ".tiff", ".jp2", ".j2k", ".mbtiles"}

# ---------------------------------------------------------------------------
# In-memory ingestion status store
# (In production this would be backed by the database / a job queue)
# ---------------------------------------------------------------------------

# Maps raster_id → IngestionStatus dict
_ingestion_status: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class UploadResponse(BaseModel):
    """Response body for POST /upload.

    Matches the design-doc specification:
        {raster_id, status, message, bbox}
    """

    raster_id: str = Field(description="Original file name used as raster id.")
    status: Literal["processing", "cataloged", "failed"] = Field(
        description="Current ingestion status."
    )
    message: str = Field(description="Human-readable status message.")
    bbox: Optional[BoundingBox] = Field(
        default=None,
        description="Geographic bounding box of the raster in WGS 84 (EPSG:4326).",
    )


class IngestionStatus(BaseModel):
    """Response body for GET /status/{raster_id}.

    Matches the design-doc specification:
        {raster_id, status, progress, error}
    """

    raster_id: str = Field(description="Raster id (original file name).")
    status: str = Field(description="Current ingestion status string.")
    progress: float = Field(
        ge=0.0,
        le=1.0,
        description="Ingestion progress from 0.0 (queued) to 1.0 (complete).",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if ingestion failed, otherwise None.",
    )


class UploadedAsset(BaseModel):
    """Response item for GET /assets."""

    raster_id: str
    file_name: str
    kind: str
    tags: str = ""
    description: str = ""
    upload_date: str


class DeleteAssetsRequest(BaseModel):
    """Request body for DELETE /assets."""

    raster_ids: list[str] = Field(default_factory=list, min_length=1)


class DeleteAssetsResponse(BaseModel):
    """Response body for DELETE /assets."""

    deleted: list[str]
    missing: list[str]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _save_upload_to_disk(upload: UploadFile, data_root: Path, max_size: int) -> Path:
    """Persist an uploaded file to the data root directory.

    Creates a unique subdirectory per upload to avoid filename collisions.

    Args:
        upload:    The FastAPI ``UploadFile`` object.
        data_root: Root directory for geospatial data storage.
        max_size:  Maximum allowed file size in bytes.

    Returns:
        ``Path`` to the saved file.

    Raises:
        HTTPException(400): If the filename is missing or empty.
        HTTPException(413): If the file exceeds ``max_size``.
        IOError: On disk write failures.
    """
    if not upload.filename:
        raise HTTPException(status_code=400, detail="Uploaded file has no filename.")

    # Sanitize filename — strip directory components
    safe_name = Path(upload.filename).name
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid filename.")

    # Create a unique upload directory
    upload_dir = data_root / "uploads" / str(uuid.uuid4())
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest_path = upload_dir / safe_name

    # Stream to disk while enforcing the size limit
    bytes_written = 0
    chunk_size = 1024 * 1024  # 1 MB chunks

    with dest_path.open("wb") as out_file:
        while True:
            chunk = upload.file.read(chunk_size)
            if not chunk:
                break
            bytes_written += len(chunk)
            if bytes_written > max_size:
                out_file.close()
                dest_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"Upload exceeds maximum allowed size of "
                        f"{max_size / (1024 ** 3):.1f} GB."
                    ),
                )
            out_file.write(chunk)

    logger.info(
        "Saved upload '%s' → %s (%.2f MB)",
        safe_name,
        dest_path,
        bytes_written / (1024 ** 2),
    )
    return dest_path


def _catalog_raster_in_db(metadata: RasterMetadata, db: Session) -> None:
    """Insert or update a raster metadata record in the database.

    Uses a simple upsert pattern: tries to insert; if the raster_id already
    exists, updates the record.  All queries use parameterized statements
    (Requirement 10.4).

    For PostGIS deployments the geometry column is populated with
    ``ST_MakeEnvelope``; for SQLite (testing) a plain JSON bbox is stored.

    Args:
        metadata: Populated ``RasterMetadata`` instance.
        db:       Active SQLAlchemy session.
    """
    db_url = str(db.bind.url) if db.bind else ""
    is_postgres = "postgresql" in db_url or "postgis" in db_url

    if is_postgres:
        # PostGIS upsert with spatial geometry column
        upsert_sql = sa_text(
            """
            INSERT INTO raster_assets (
                raster_id, file_path, file_name, kind, crs,
                min_lon, min_lat, max_lon, max_lat,
                resolution_x, resolution_y, width, height,
                tags, description,
                upload_date, geom
            ) VALUES (
                :raster_id, :file_path, :file_name, :kind, :crs,
                :min_lon, :min_lat, :max_lon, :max_lat,
                :resolution_x, :resolution_y, :width, :height,
                :tags, :description,
                :upload_date,
                ST_SetSRID(
                    ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat),
                    4326
                )
            )
            ON CONFLICT (raster_id) DO UPDATE SET
                file_path    = EXCLUDED.file_path,
                file_name    = EXCLUDED.file_name,
                kind         = EXCLUDED.kind,
                crs          = EXCLUDED.crs,
                min_lon      = EXCLUDED.min_lon,
                min_lat      = EXCLUDED.min_lat,
                max_lon      = EXCLUDED.max_lon,
                max_lat      = EXCLUDED.max_lat,
                resolution_x = EXCLUDED.resolution_x,
                resolution_y = EXCLUDED.resolution_y,
                width        = EXCLUDED.width,
                height       = EXCLUDED.height,
                tags         = EXCLUDED.tags,
                description  = EXCLUDED.description,
                upload_date  = EXCLUDED.upload_date,
                geom         = EXCLUDED.geom
            """
        )
    else:
        # SQLite fallback (no spatial extension required)
        upsert_sql = sa_text(
            """
            INSERT OR REPLACE INTO raster_assets (
                raster_id, file_path, file_name, kind, crs,
                min_lon, min_lat, max_lon, max_lat,
                resolution_x, resolution_y, width, height,
                tags, description,
                upload_date
            ) VALUES (
                :raster_id, :file_path, :file_name, :kind, :crs,
                :min_lon, :min_lat, :max_lon, :max_lat,
                :resolution_x, :resolution_y, :width, :height,
                :tags, :description,
                :upload_date
            )
            """
        )

    upload_date = (
        metadata.upload_date.isoformat()
        if metadata.upload_date
        else datetime.now(timezone.utc).isoformat()
    )

    db.execute(
        upsert_sql,
        {
            "raster_id": metadata.raster_id,
            "file_path": metadata.file_path,
            "file_name": metadata.file_name,
            "kind": metadata.kind.value,
            "crs": metadata.crs,
            "min_lon": metadata.bbox.min_lon,
            "min_lat": metadata.bbox.min_lat,
            "max_lon": metadata.bbox.max_lon,
            "max_lat": metadata.bbox.max_lat,
            "resolution_x": metadata.resolution_x,
            "resolution_y": metadata.resolution_y,
            "width": metadata.width,
            "height": metadata.height,
            "tags": metadata.tags or "",
            "description": metadata.description or "",
            "upload_date": upload_date,
        },
    )
    db.commit()
    logger.info(
        "Cataloged raster raster_id=%s file=%s",
        metadata.raster_id,
        metadata.file_name,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/upload",
    response_model=UploadResponse,
    summary="Upload and ingest a geospatial raster file",
    description=(
        "Accept a multipart file upload (GeoTIFF, JPEG2000, or MBTiles), "
        "save it to DATA_ROOT, extract GDAL metadata, and catalog the raster "
        "in PostGIS. Returns the assigned raster_id and bounding box."
    ),
    status_code=200,
)
def upload_raster(
    file: UploadFile = File(..., description="Geospatial raster file to ingest."),
    sidecar_json: Optional[str] = Form(None, alias="metadata", description="JSON with optional sidecar file contents."),
    tags: Optional[str] = Form(None, description="Comma-separated metadata tags."),
    description: Optional[str] = Form(None, description="Free-text description."),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    cfg: Settings = Depends(get_settings),
    data_root: Path = Depends(get_data_root),
) -> UploadResponse:
    """Upload and ingest a geospatial raster file.

    Pipeline:
    1. Validate file extension against supported formats.
    2. Save the file to ``DATA_ROOT/uploads/<uuid>/<filename>``.
    3. Dispatch to the appropriate format handler for format-level validation.
    4. Run GDAL metadata extraction (CRS, bounds, resolution).
    5. Catalog the metadata in PostGIS / SQLite.
    6. Record ingestion status for ``GET /status/{raster_id}``.

    Requirements: 6.1, 9.6
    """
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()

    logger.info("POST /upload — filename=%s size_hint=%s", filename, file.size)

    # --- 1. Validate extension ---
    if ext not in _SUPPORTED_EXTENSIONS:
        logger.warning(
            "POST /upload — unsupported extension '%s' for file '%s'", ext, filename
        )
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file format '{ext}'. "
                f"Supported formats: {', '.join(sorted(_SUPPORTED_EXTENSIONS))}."
            ),
        )

    # --- 2. Save to disk ---
    try:
        saved_path = _save_upload_to_disk(file, data_root, cfg.max_upload_size)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("POST /upload — failed to save file '%s': %s", filename, exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save uploaded file: {exc}",
        ) from exc

    raster_id = saved_path.name

    # Write any uploaded sidecar files (e.g. .prj, .j2w, .tfw, .jgw)
    if sidecar_json:
        try:
            import json as _json
            meta_dict = _json.loads(sidecar_json)
            for key, val in meta_dict.items():
                if key.startswith("sidecar_") and val:
                    suffix = "." + key.split("_", 1)[1]
                    sidecar_path = saved_path.with_suffix(suffix)
                    sidecar_path.write_text(val)
                    logger.info("Saved sidecar file during upload: %s", sidecar_path)
        except Exception as exc:
            logger.warning("Failed to parse sidecar_json Form parameter: %s", exc)

    # Record initial status
    _ingestion_status[raster_id] = {
        "raster_id": raster_id,
        "status": "processing",
        "progress": 0.1,
        "error": None,
    }

    # --- 3. Format handler validation ---
    handler = get_format_handler(ext)
    if handler is not None:
        try:
            is_valid = handler.validate(saved_path)
            if not is_valid:
                _ingestion_status[raster_id].update(
                    {
                        "status": "failed",
                        "progress": 0.0,
                        "error": "Format validation failed.",
                    }
                )
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"File '{filename}' failed format validation for extension '{ext}'. "
                        "Ensure the file is not corrupted."
                    ),
                )
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning(
                "POST /upload — format handler validation error for '%s': %s",
                filename,
                exc,
            )
            # Non-fatal: proceed to GDAL extraction even if handler validation fails

    _ingestion_status[raster_id]["progress"] = 0.3

    # --- 3.5. Schedule COG conversion as a background task ---
    # Fires AFTER the HTTP response is returned so it never blocks or
    # causes 500s. COG files will be available for fast tiling on next request.
    if ext in {".tif", ".tiff", ".jp2", ".j2k"}:
        _cog_path = saved_path  # capture snapshot before any mutation
        def _bg_cog(p: Path = _cog_path) -> None:
            try:
                from src_new.services.ingestion.gdal_pipelines.cog_converter import CogConverter
                res = CogConverter().convert(p)
                logger.info("BG COG: %s converted=%s", p.name, res.converted)
            except Exception as _exc:
                logger.warning("BG COG failed for %s: %s", p.name, _exc)
        background_tasks.add_task(_bg_cog)

    # --- 4. GDAL metadata extraction ---
    extract_metadata = get_metadata_extractor()
    try:
        metadata = extract_metadata(saved_path)
        # Assign the raster_id we generated (extractor creates its own id)
        metadata = metadata.model_copy(
            update={
                "raster_id": raster_id,
                "tags": tags or "",
                "description": description or "",
                "upload_date": datetime.now(timezone.utc),
            }
        )
    except FileNotFoundError as exc:
        _ingestion_status[raster_id].update(
            {"status": "failed", "progress": 0.0, "error": str(exc)}
        )
        logger.error("POST /upload — file not found after save: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        error_msg = str(exc)
        _ingestion_status[raster_id].update(
            {"status": "failed", "progress": 0.0, "error": error_msg}
        )
        logger.error(
            "POST /upload — GDAL metadata extraction failed for '%s': %s",
            filename,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Metadata extraction failed: {error_msg}",
        ) from exc

    _ingestion_status[raster_id]["progress"] = 0.7

    # --- 5. Catalog in database ---
    try:
        _catalog_raster_in_db(metadata, db)
    except Exception as exc:
        error_msg = str(exc)
        _ingestion_status[raster_id].update(
            {"status": "failed", "progress": 0.7, "error": error_msg}
        )
        logger.error(
            "POST /upload — database catalog failed for raster_id=%s: %s",
            raster_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to catalog raster in database: {error_msg}",
        ) from exc

    # --- 6. Mark complete ---
    _ingestion_status[raster_id].update(
        {"status": "cataloged", "progress": 1.0, "error": None}
    )

    logger.info(
        "POST /upload — SUCCESS raster_id=%s file=%s bbox=[%.4f,%.4f,%.4f,%.4f]",
        raster_id,
        filename,
        metadata.bbox.min_lon,
        metadata.bbox.min_lat,
        metadata.bbox.max_lon,
        metadata.bbox.max_lat,
    )

    return UploadResponse(
        raster_id=raster_id,
        status="cataloged",
        message=f"Raster '{filename}' successfully ingested and cataloged.",
        bbox=metadata.bbox,
    )


@router.get(
    "/status/{raster_id}",
    response_model=IngestionStatus,
    summary="Get ingestion status",
    description=(
        "Return the current ingestion status and progress for a previously "
        "uploaded raster identified by its UUID."
    ),
)
def get_ingestion_status(raster_id: str) -> IngestionStatus:
    """Return ingestion progress and status for a raster.

    Args:
        raster_id: Raster id of the asset (path parameter).

    Returns:
        ``IngestionStatus`` with status, progress (0.0–1.0), and optional error.

    Raises:
        HTTPException(404): If no ingestion record exists for the given raster_id.

    Requirements: 6.1
    """
    logger.info("GET /status/%s", raster_id)

    status_record = _ingestion_status.get(raster_id)
    if status_record is None:
        logger.warning("GET /status/%s — not found", raster_id)
        raise HTTPException(
            status_code=404,
            detail=f"No ingestion record found for raster_id: {raster_id}",
        )

    return IngestionStatus(**status_record)


@router.get(
    "/assets",
    response_model=list[UploadedAsset],
    summary="List cataloged assets",
    description="Return cataloged assets ordered by upload date (newest first).",
)
def list_assets(db: Session = Depends(get_db)) -> list[UploadedAsset]:
    """Return cataloged assets ordered by upload date (newest first)."""
    query = sa_text(
        """
        SELECT raster_id, file_name, kind, upload_date,
               COALESCE(tags, '') AS tags,
               COALESCE(description, '') AS description
        FROM raster_assets
        ORDER BY upload_date DESC
        """
    )
    rows = db.execute(query).fetchall()
    return [
        UploadedAsset(
            raster_id=str(row[0]),
            file_name=str(row[1]),
            kind=str(row[2]),
            upload_date=str(row[3]),
            tags=str(row[4] or ""),
            description=str(row[5] or ""),
        )
        for row in rows
    ]


@router.delete(
    "/assets",
    response_model=DeleteAssetsResponse,
    summary="Delete cataloged assets",
    description="Delete cataloged assets by raster_id and remove stored files.",
)
def delete_assets(
    payload: DeleteAssetsRequest,
    db: Session = Depends(get_db),
    data_root: Path = Depends(get_data_root),
) -> DeleteAssetsResponse:
    """Delete cataloged assets and remove stored files."""
    raster_ids = [rid for rid in payload.raster_ids if rid]
    if not raster_ids:
        raise HTTPException(status_code=400, detail="No raster_ids provided.")

    select_sql = sa_text(
        """
        SELECT raster_id, file_path
        FROM raster_assets
        WHERE raster_id IN :ids
        """
    ).bindparams(bindparam("ids", expanding=True))

    rows = db.execute(select_sql, {"ids": raster_ids}).fetchall()
    found_ids = {str(row[0]) for row in rows}
    missing = [rid for rid in raster_ids if rid not in found_ids]

    delete_sql = sa_text(
        """
        DELETE FROM raster_assets
        WHERE raster_id IN :ids
        """
    ).bindparams(bindparam("ids", expanding=True))

    if found_ids:
        db.execute(delete_sql, {"ids": list(found_ids)})
        db.commit()

    for raster_id, file_path in rows:
        _ingestion_status.pop(str(raster_id), None)
        try:
            path_to_delete = Path(file_path)
            if path_to_delete.exists():
                path_to_delete.unlink(missing_ok=True)

            # Clean up COG file
            cog_path = path_to_delete.parent / f"{path_to_delete.stem}.cog.tif"
            if cog_path.exists():
                cog_path.unlink(missing_ok=True)

            # Clean up sidecar files
            for suffix in (".prj", ".tfw", ".j2w", ".jgw", ".wld"):
                sidecar = path_to_delete.with_suffix(suffix)
                if sidecar.exists():
                    sidecar.unlink(missing_ok=True)

            # Delete parent directory if it's a unique upload folder (e.g. uploads/<uuid>)
            parent_dir = path_to_delete.parent
            if parent_dir.name != "uploads" and parent_dir.parent.name == "uploads":
                shutil.rmtree(parent_dir, ignore_errors=True)
                logger.info("Cleaned up upload directory: %s", parent_dir)
        except Exception as exc:
            logger.warning("Failed to clean up files for raster_id %s: %s", raster_id, exc)

    return DeleteAssetsResponse(deleted=sorted(found_ids), missing=missing)


@router.get(
    "/health",
    summary="Health check",
    description=(
        "Liveness and readiness probe. Returns service status, database "
        "connectivity, and available disk space on the data volume."
    ),
)
def health_check(
    db: Session = Depends(get_db),
    cfg: Settings = Depends(get_settings),
) -> dict:
    """Return Ingestion Service health information.

    Checks:
    1. Database connectivity — executes a lightweight ``SELECT 1`` query.
    2. Disk space — reports free gigabytes on the filesystem containing
       ``DATA_ROOT`` (the data volume).

    Returns:
        A dict with keys:
        - ``status``: ``"healthy"`` | ``"degraded"`` | ``"unhealthy"``
        - ``database``: ``True`` if the DB is reachable, ``False`` otherwise.
        - ``disk_space_gb``: Free disk space in gigabytes (float, rounded to 2 dp).

    Requirements: 6.1, 18.5
    """
    # --- Database connectivity check ---
    db_ok = False
    try:
        db.execute(sa_text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        logger.warning("Health check: database unreachable — %s", exc)

    # --- Disk space check (use DATA_ROOT as the reference path) ---
    disk_space_gb: float = 0.0
    try:
        check_path = str(cfg.data_root) if cfg.data_root else os.getcwd()
        usage = shutil.disk_usage(check_path)
        disk_space_gb = round(usage.free / (1024 ** 3), 2)
    except Exception as exc:
        logger.warning("Health check: disk usage check failed — %s", exc)

    # --- Overall status ---
    status = "healthy" if db_ok else "degraded"

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


# ---------------------------------------------------------------------------
# Expose the in-memory status store for testing
# ---------------------------------------------------------------------------


def _get_ingestion_status_store() -> dict:
    """Return the in-memory ingestion status store (for testing only)."""
    return _ingestion_status


__all__ = [
    "router",
    "UploadResponse",
    "IngestionStatus",
    "_get_ingestion_status_store",
]
