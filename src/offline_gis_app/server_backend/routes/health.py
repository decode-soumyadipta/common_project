from fastapi import APIRouter


router = APIRouter(tags=["health"])
API_BUILD = "2026-04-25-queue-fix"


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "api_build": API_BUILD}
