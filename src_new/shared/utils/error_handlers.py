"""FastAPI exception handlers shared across all services.

Extracted from route files in src/server_gateway/api/routes/ and
src/server_vm/api_routes/.

Register these handlers on any FastAPI app instance:

    from src_new.shared.utils.error_handlers import register_exception_handlers
    register_exception_handlers(app)
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exception types
# ---------------------------------------------------------------------------


class GeospatialServiceError(Exception):
    """Base class for all service-layer errors."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.status_code = status_code


class RasterNotFoundError(GeospatialServiceError):
    """Raised when a requested raster asset does not exist."""

    def __init__(self, raster_id: str) -> None:
        super().__init__(f"Raster not found: {raster_id}", status_code=404)
        self.raster_id = raster_id


class IngestJobNotFoundError(GeospatialServiceError):
    """Raised when a requested ingest job does not exist."""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"Ingest job not found: {job_id}", status_code=404)
        self.job_id = job_id


class FileFormatError(GeospatialServiceError):
    """Raised when an uploaded file has an unsupported or invalid format."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail, status_code=422)


class MetadataExtractionError(GeospatialServiceError):
    """Raised when GDAL metadata extraction fails."""

    def __init__(self, file_path: str, reason: str) -> None:
        super().__init__(
            f"Metadata extraction failed for {file_path!r}: {reason}",
            status_code=500,
        )
        self.file_path = file_path
        self.reason = reason


class DatabaseError(GeospatialServiceError):
    """Raised when a database operation fails."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"Database error: {detail}", status_code=500)


class UnauthorizedAccessError(GeospatialServiceError):
    """Raised when a request comes from an unauthorized IP address."""

    def __init__(self, client_ip: str) -> None:
        super().__init__(
            f"Access denied for IP {client_ip!r}. Not in ALLOWED_HOSTS.",
            status_code=403,
        )
        self.client_ip = client_ip


# ---------------------------------------------------------------------------
# Handler functions
# ---------------------------------------------------------------------------


async def _handle_geospatial_service_error(
    request: Request, exc: GeospatialServiceError
) -> JSONResponse:
    """Convert GeospatialServiceError subclasses into JSON error responses."""
    logger.error(
        "Service error [%s %s]: %s",
        request.method,
        request.url.path,
        exc,
        exc_info=False,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc), "type": type(exc).__name__},
    )


async def _handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    """Log and re-format FastAPI HTTPException responses."""
    logger.warning(
        "HTTP %d [%s %s]: %s",
        exc.status_code,
        request.method,
        request.url.path,
        exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


async def _handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return a 422 response with structured validation error details."""
    errors: list[dict[str, Any]] = []
    for error in exc.errors():
        errors.append(
            {
                "field": " → ".join(str(loc) for loc in error.get("loc", [])),
                "message": error.get("msg", ""),
                "type": error.get("type", ""),
            }
        )
    logger.warning(
        "Validation error [%s %s]: %d field(s) failed",
        request.method,
        request.url.path,
        len(errors),
    )
    return JSONResponse(
        status_code=422,
        content={"detail": "Request validation failed", "errors": errors},
    )


async def _handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for unexpected exceptions.

    Logs the full traceback and returns a generic 500 response so that
    internal details are not leaked to clients.
    """
    logger.exception(
        "Unhandled exception [%s %s]",
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred."},
    )


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------


def register_exception_handlers(app: FastAPI) -> None:
    """Register all shared exception handlers on a FastAPI application.

    Call this once during app creation, after all routers are included:

        app = FastAPI(...)
        app.include_router(router)
        register_exception_handlers(app)

    Args:
        app: The FastAPI application instance.
    """
    app.add_exception_handler(GeospatialServiceError, _handle_geospatial_service_error)  # type: ignore[arg-type]
    app.add_exception_handler(HTTPException, _handle_http_exception)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _handle_validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _handle_unhandled_exception)  # type: ignore[arg-type]
    logger.debug("Exception handlers registered on %s", app.title)


__all__ = [
    # Custom exceptions
    "GeospatialServiceError",
    "RasterNotFoundError",
    "IngestJobNotFoundError",
    "FileFormatError",
    "MetadataExtractionError",
    "DatabaseError",
    "UnauthorizedAccessError",
    # Registration
    "register_exception_handlers",
]
