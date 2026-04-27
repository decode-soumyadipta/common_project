"""FastAPI route boundary helpers for server_vm."""

from fastapi import FastAPI


def include_default_routes(app: FastAPI) -> None:
    """Attach the standard server routers in a single boundary call."""
    from server_vm.server_backend.routes.health import router as health_router
    from server_vm.server_backend.routes.ingest import router as ingest_router
    from server_vm.server_backend.routes.profile import router as profile_router
    from server_vm.server_backend.routes.search import router as search_router

    app.include_router(health_router)
    app.include_router(ingest_router)
    app.include_router(search_router)
    app.include_router(profile_router)


__all__ = ["include_default_routes"]
