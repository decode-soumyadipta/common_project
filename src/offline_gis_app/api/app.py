from fastapi import FastAPI

from offline_gis_app.api.routes.health import router as health_router
from offline_gis_app.api.routes.ingest import router as ingest_router
from offline_gis_app.api.routes.profile import router as profile_router
from offline_gis_app.api.routes.search import router as search_router
from offline_gis_app.db.session import init_db


def create_app() -> FastAPI:
    init_db()
    app = FastAPI(title="Offline 3D GIS API", version="0.1.0")
    app.include_router(health_router)
    app.include_router(ingest_router)
    app.include_router(search_router)
    app.include_router(profile_router)
    return app


app = create_app()

