"""Ingestion Service FastAPI application entry point.

This module creates and configures the FastAPI application for the Ingestion
Service (Server 1).  It wires together:

- Route handlers from ``src_new.services.ingestion.api.routes``
- LAN security middleware from ``src_new.shared.auth.lan_security``
- Shared exception handlers from ``src_new.shared.utils.error_handlers``
- Structured logging from ``src_new.shared.utils.logging_config``

The service reads its bind port from the ``INGESTION_SERVICE_PORT`` environment
variable (default: 8001) via the centralized ``Settings`` object.

Starting the service
--------------------
Via uvicorn directly::

    uvicorn src_new.services.ingestion.service:app \\
        --host 192.168.1.10 \\
        --port 8001

Via the deployment script::

    bash src_new/scripts/start_ingestion_service.sh

Requirements: 6.1, 6.6, 16.1, 16.2
"""
from __future__ import annotations

import logging
import time

import uvicorn
from fastapi import FastAPI, Request

from src_new.services.ingestion.api.routes import router
from src_new.shared.auth.lan_security import LANSecurityMiddleware, get_bind_host
from src_new.shared.config import settings
from src_new.shared.utils.error_handlers import register_exception_handlers

# --------------------------------------------------------------------------- Logging setup — configure before creating the app so startup messages land ---------------------------------------------------------------------------

try:
    from src_new.shared.utils.logging_config import configure_logging

    configure_logging()
except Exception:
    # Fallback: basic logging if logging_config is not yet available
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- FastAPI application ---------------------------------------------------------------------------

app = FastAPI(
    title="Ingestion Service",
    description=(
        "Geospatial Ingestion Service (Server 1) — handles upload, GDAL "
        "processing, and PostGIS cataloging of raster assets "
        "(GeoTIFF, JPEG2000, MBTiles)."
    ),
    version="1.0.0",
    # Disable automatic redirect for trailing slashes to avoid CORS issues
    redirect_slashes=False,
    # OpenAPI docs are served at /docs; access is controlled by LANSecurityMiddleware at the network level
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# --------------------------------------------------------------------------- Middleware — LAN security (Requirement 16.1) Must be added BEFORE routers so it intercepts every request. ---------------------------------------------------------------------------

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

# --------------------------------------------------------------------------- Routers ---------------------------------------------------------------------------

app.include_router(router)

# --------------------------------------------------------------------------- Exception handlers ---------------------------------------------------------------------------

register_exception_handlers(app)

# --------------------------------------------------------------------------- Startup / shutdown lifecycle events ---------------------------------------------------------------------------


@app.on_event("startup")
async def _on_startup() -> None:
    """Log service startup and apply GDAL environment variables."""
    # Apply GDAL env vars from config before any GDAL/Rasterio operation (Requirement 9.4)
    settings.apply_gdal_env()
    logger.info(
        "Ingestion Service STARTUP — host=%s port=%d database=%s log_level=%s",
        get_bind_host(),
        settings.ingestion_service_port,
        # Mask credentials in the log — show only the host/db portion
        settings.database_url.split("@")[-1]
        if "@" in settings.database_url
        else settings.database_url,
        settings.log_level,
        extra={
            "event": "service_startup",
            "service": "ingestion",
            "host": get_bind_host(),
            "port": settings.ingestion_service_port,
        }
    )


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    """Log service shutdown."""
    logger.info(
        "Ingestion Service SHUTDOWN",
        extra={
            "event": "service_shutdown",
            "service": "ingestion",
        }
    )


# --------------------------------------------------------------------------- Programmatic entry point (python -m src_new.services.ingestion.service) ---------------------------------------------------------------------------

if __name__ == "__main__":
    host = get_bind_host()
    port = settings.ingestion_service_port

    logger.info("Starting Ingestion Service on %s:%d", host, port)

    uvicorn.run(
        "src_new.services.ingestion.service:app",
        host=host,
        port=port,
        reload=False,
        log_level=settings.log_level.lower(),
    )
