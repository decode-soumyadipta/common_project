import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from platform_core.config.settings import settings
from server_gateway.api.routes import ingest, search, proxy
from platform_core.db.session import init_db

# Configure logging
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("server_gateway")

def create_app() -> FastAPI:
    app = FastAPI(
        title="Distributed GIS Gateway",
        description="Server A: Gateway, Catalog, and Rendering Interface",
        version="2.0.0"
    )

    # Security: CORS configuration for LAN access
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], # Tighten this in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize Database
    @app.on_event("startup")
    def startup_event():
        logger.info("Initializing Gateway Database...")
        init_db()
        logger.info("Gateway API ready at %s", settings.gateway_url)

    # Include Routers
    app.include_router(ingest.router)
    app.include_router(search.router)
    app.include_router(proxy.router)

    @app.get("/health")
    def health():
        return {"status": "ok", "node": "gateway", "topology": settings.deployment_topology}

    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
