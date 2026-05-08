from fastapi import APIRouter, Request, Response
import httpx
from platform_core.config.settings import settings

router = APIRouter(prefix="/proxy", tags=["proxy"])

@router.get("/tile/{path:path}")
async def proxy_tile(path: str, request: Request):
    """Proxy requests to the local TiTiler instance on Server A."""
    target_url = f"{settings.titiler_base_url}/{path}"
    async with httpx.AsyncClient() as client:
        # Forward query parameters
        params = dict(request.query_params)
        resp = await client.get(target_url, params=params, timeout=10.0)
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=dict(resp.headers)
        )
