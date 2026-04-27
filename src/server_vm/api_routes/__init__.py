"""FastAPI router exports for server_vm domain boundary."""

from server_vm.server_backend.routes.health import router as health_router
from server_vm.server_backend.routes.ingest import router as ingest_router
from server_vm.server_backend.routes.profile import router as profile_router
from server_vm.server_backend.routes.search import router as search_router

__all__ = [
    "health_router",
    "ingest_router",
    "profile_router",
    "search_router",
]
