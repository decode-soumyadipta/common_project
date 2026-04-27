from __future__ import annotations

import platform
import re

import uvicorn
from starlette.middleware.base import BaseHTTPMiddleware

from titiler.application.main import app as titiler_app


class _WindowsEncodedPathFixMiddleware(BaseHTTPMiddleware):
    """Normalize Windows drive-letter URLs passed via encoded query params."""

    async def dispatch(self, request, call_next):  # type: ignore[override]
        if platform.system() == "Windows" and "url" in request.query_params:
            raw = request.scope.get("query_string", b"").decode(
                "utf-8", errors="replace"
            )
            fixed = re.sub(
                r"(?<=[?&])url=%2F([A-Za-z](?:%3A|:))",
                lambda match: "url=" + match.group(1).replace("%3A", ":"),
                raw,
            )
            fixed = re.sub(r"(?<=[?&])url=/([A-Za-z]:)", r"url=\1", fixed)
            request.scope["query_string"] = fixed.encode("utf-8")
        return await call_next(request)


def create_titiler_app():
    """Create a TiTiler app with offline desktop compatibility middleware."""
    if _WindowsEncodedPathFixMiddleware not in [m.cls for m in titiler_app.user_middleware]:
        titiler_app.add_middleware(_WindowsEncodedPathFixMiddleware)
    return titiler_app


def run_titiler(host: str = "127.0.0.1", port: int = 8081, log_level: str = "warning") -> None:
    """Run the TiTiler ASGI app using uvicorn."""
    uvicorn.run(create_titiler_app(), host=host, port=port, log_level=log_level)


__all__ = ["create_titiler_app", "run_titiler"]
