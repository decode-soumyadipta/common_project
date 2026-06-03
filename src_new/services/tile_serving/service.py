"""Tile Service FastAPI application entry point.

This module creates the FastAPI app for the Tile Service (Server 1).
It:
  1. Mounts the TiTiler sub-application at ``/titiler`` for default tile
     serving endpoints.
  2. Includes the custom ``tile_endpoints`` router (``/tiles``, ``/preview``,
     ``/metadata``, ``/health``).
  3. Applies ``LANSecurityMiddleware`` to restrict access to allowed LAN IPs.
  4. Reads the bind port from ``TILE_SERVICE_PORT`` env var via
     ``shared.config.settings``.

Run with uvicorn::

    uvicorn src_new.services.tile_serving.service:app \\
        --host 192.168.1.10 --port 8002

Or via the startup script::

    src_new/scripts/start_tile_service.sh

Requirements: 11.3, 16.1
"""
from __future__ import annotations

import logging
import os
import time

from fastapi import FastAPI, Request

from src_new.shared.auth.lan_security import LANSecurityMiddleware, get_bind_host
from src_new.shared.config import settings
from src_new.shared.utils.logging_config import configure_logging
from src_new.services.tile_serving.tile_endpoints import router as tile_router
from src_new.services.tile_serving.titiler_config import create_titiler_app

# --------------------------------------------------------------------------- Logging ---------------------------------------------------------------------------
configure_logging()
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- FastAPI application ---------------------------------------------------------------------------

app = FastAPI(
    title="Tile Service",
    description=(
        "Dynamic map tile serving for the offline 3D GIS system. "
        "Serves XYZ tiles, previews, and metadata from local COG rasters. "
        "Restricted to authorised LAN IP addresses."
    ),
    version="1.0.0",
    # Disable automatic redirect for trailing slashes to avoid CORS issues
    redirect_slashes=False,
)

# --------------------------------------------------------------------------- Security middleware — must be added before routes are registered so that every request (including sub-application requests) passes through it. Requirement 16.1 ---------------------------------------------------------------------------
app.add_middleware(LANSecurityMiddleware)

# --------------------------------------------------------------------------- Request/Response Logging Middleware (Requirement 18.3) ---------------------------------------------------------------------------

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests and responses with timing information."""
    start_time = time.time()
    
    # Log incoming request
    logger.info(
        "Request: %s %s",
        request.method,
        request.url.path,
        extra={
            "event": "http_request",
            "method": request.method,
            "path": request.url.path,
            "client_host": request.client.host if request.client else None,
        }
    )
    
    # Process request
    response = await call_next(request)
    
    # Calculate duration
    duration_ms = (time.time() - start_time) * 1000
    
    # Log response
    logger.info(
        "Response: %s %s — status=%d duration=%.2fms",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        extra={
            "event": "http_response",
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
        }
    )
    
    return response

# --------------------------------------------------------------------------- Mount TiTiler sub-application TiTiler provides its own set of tile-serving endpoints (COG, STAC, etc.). We mount it at /titiler so it does not conflict with our custom routes. ---------------------------------------------------------------------------
titiler_app = create_titiler_app()
app.mount("/titiler", titiler_app, name="titiler")
logger.debug("TiTiler sub-application mounted at /titiler.")

# --------------------------------------------------------------------------- Custom tile endpoints router Provides: /tiles/{z}/{x}/{y}.png, /preview/{raster_id}, /metadata/{raster_id}, /health Requirement 11.5 ---------------------------------------------------------------------------
app.include_router(tile_router)
logger.debug("Custom tile_endpoints router included.")

# --------------------------------------------------------------------------- Startup / shutdown lifecycle events ---------------------------------------------------------------------------


@app.on_event("startup")
async def _on_startup() -> None:
    """Log service startup and apply GDAL environment variables."""
    settings.apply_gdal_env()
    logger.info(
        "Tile Service STARTUP — port=%d host=%s log_level=%s",
        settings.tile_service_port,
        get_bind_host(),
        settings.log_level,
        extra={
            "event": "service_startup",
            "service": "tile_serving",
            "host": get_bind_host(),
            "port": settings.tile_service_port,
        }
    )
    logger.info(
        "Tile cache: max_size=%d (TILE_CACHE_SIZE=%d).",
        settings.tile_cache_size,
        settings.tile_cache_size,
    )
    logger.info(
        "GDAL env: GDAL_DISABLE_READDIR_ON_OPEN=%s, "
        "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES=%s.",
        os.environ.get("GDAL_DISABLE_READDIR_ON_OPEN", "not set"),
        os.environ.get("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "not set"),
    )


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    """Log service shutdown."""
    logger.info(
        "Tile Service SHUTDOWN",
        extra={
            "event": "service_shutdown",
            "service": "tile_serving",
        }
    )


# --------------------------------------------------------------------------- Uvicorn entry point ---------------------------------------------------------------------------


def run() -> None:
    """Start the Tile Service using uvicorn.

    Reads host and port from ``shared.config.settings`` so that the service
    respects the centralized .env configuration.

    Requirement 16.2: bind to LAN interface only (not 0.0.0.0) unless
    ``BIND_ALL_INTERFACES=true``.
    """
    import uvicorn  # local import to avoid hard dependency at module level

    host = get_bind_host()
    port = settings.tile_service_port
    log_level = settings.log_level.lower()

    logger.info(
        "Launching Tile Service via uvicorn on %s:%d (log_level=%s).",
        host, port, log_level,
    )

    uvicorn.run(
        "src_new.services.tile_serving.service:app",
        host=host,
        port=port,
        log_level=log_level,
        reload=False,
        access_log=True,
        timeout_keep_alive=5,
        backlog=max(128, (os.cpu_count() or 2) * 64),
    )


if __name__ == "__main__":
    run()


__all__ = ["app", "run"]
