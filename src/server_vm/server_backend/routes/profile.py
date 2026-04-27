from fastapi import APIRouter, HTTPException

from server_vm.server_backend.schemas import ProfileRequest
from server_vm.api_routes.profile import elevation_profile_from_request


router = APIRouter(prefix="/profile", tags=["profile"])


@router.post("/elevation")
def profile(request: ProfileRequest) -> dict:
    try:
        return elevation_profile_from_request(request)
    except HTTPException:
        raise
