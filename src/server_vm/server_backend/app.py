from contextlib import asynccontextmanager

from fastapi import FastAPI

from server_vm.api_routes import include_default_routes
from core_shared.db.session import init_db
from core_shared.ingestion.services.ingest_queue_service import (
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
    include_default_routes(app)
    return app


app = create_app()
