from contextlib import asynccontextmanager

from fastapi import FastAPI

from offline_gis_app.server_backend.routes.health import router as health_router
from offline_gis_app.server_backend.routes.ingest import router as ingest_router
from offline_gis_app.server_backend.routes.profile import router as profile_router
from offline_gis_app.server_backend.routes.search import router as search_router
from offline_gis_app.db.session import init_db
from offline_gis_app.server_ingestion.services.ingest_queue_service import (
    ingest_queue_service,
)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Initialize DB/queue services on startup and shut them down on exit."""
    init_db()
    ingest_queue_service.start()
    ingest_queue_service.resume_recoverable_jobs()
    try:
        yield
    finally:
        ingest_queue_service.shutdown()


def create_app() -> FastAPI:
    """Build and configure the FastAPI application instance."""
    app = FastAPI(title="Offline 3D GIS API", version="0.1.0", lifespan=_lifespan)
    app.include_router(health_router)
    app.include_router(ingest_router)
    app.include_router(search_router)
    app.include_router(profile_router)
    return app


app = create_app()
