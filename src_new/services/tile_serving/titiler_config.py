"""TiTiler FastAPI application setup for the Tile Service.

Adapted from ``src/server_vm/titiler_service/service.py``.

Key responsibilities:
- Apply GDAL environment variables from ``shared.config.settings`` **before**
  TiTiler is imported/initialized (GDAL reads env vars at import time).
- Add the Windows encoded-path fix middleware for cross-platform compatibility.
- Disable all external HTTP requests so TiTiler only reads local files
  (air-gap / LAN security requirement 16.4).
- Expose ``create_titiler_app()`` and ``run_titiler()`` for use by
  ``tile_serving.service``.

Requirements: 11.1, 11.4, 16.4
"""
from __future__ import annotations

import logging
import os
import platform
import re

from src_new.shared.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Step 1: Apply GDAL env vars from config BEFORE importing TiTiler.
# TiTiler / GDAL reads several env vars at import time, so this must happen
# as early as possible — before any titiler.* import.
# ---------------------------------------------------------------------------
settings.apply_gdal_env()

# Disable GDAL's built-in HTTP/VSICURL transport so TiTiler cannot reach
# remote rasters.  This enforces the air-gap requirement (16.4).
os.environ.setdefault("GDAL_HTTP_TIMEOUT", "1")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", "")  # block all remote extensions
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", settings.gdal_disable_readdir_on_open)
os.environ.setdefault("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", settings.gdal_http_merge_consecutive_ranges)

# ---------------------------------------------------------------------------
# Step 2: Import TiTiler (after env vars are set).
# Use try/except so the module can be imported even when titiler is not
# installed (e.g. in CI or lightweight environments).
# ---------------------------------------------------------------------------
try:
    from titiler.application.main import app as _titiler_app  # type: ignore[import]

    _TITILER_AVAILABLE = True
    logger.debug("TiTiler imported successfully.")
except ImportError as _exc:  # pragma: no cover
    _TITILER_AVAILABLE = False
    _titiler_app = None  # type: ignore[assignment]
    logger.warning(
        "TiTiler is not installed (%s). "
        "titiler_config will return a stub FastAPI app. "
        "Install titiler[application] to enable full tile serving.",
        _exc,
    )


# ---------------------------------------------------------------------------
# Windows encoded-path fix middleware
# ---------------------------------------------------------------------------

if _TITILER_AVAILABLE:
    from starlette.middleware.base import BaseHTTPMiddleware as _BaseHTTPMiddleware
    from starlette.requests import Request as _Request
    from starlette.responses import Response as _Response

    class _WindowsEncodedPathFixMiddleware(_BaseHTTPMiddleware):
        """Normalize Windows drive-letter URLs passed via encoded query params.

        On Windows, file paths like ``C:\\data\\file.tif`` may arrive as
        ``url=%2FC%3A%5Cdata%5Cfile.tif`` or similar variants.  This
        middleware normalizes them so GDAL can open the file correctly.

        Preserved from the original ``src/server_vm/titiler_service/service.py``.
        """

        async def dispatch(  # type: ignore[override]
            self, request: _Request, call_next  # type: ignore[type-arg]
        ) -> _Response:
            if platform.system() == "Windows" and "url" in request.query_params:
                raw: str = request.scope.get("query_string", b"").decode(
                    "utf-8", errors="replace"
                )
                # Remove leading slash before drive letter (e.g. %2FC: → C:)
                fixed = re.sub(
                    r"(?<=[?&])url=%2F([A-Za-z](?:%3A|:))",
                    lambda m: "url=" + m.group(1).replace("%3A", ":"),
                    raw,
                )
                # Remove leading slash before drive letter (e.g. /C: → C:)
                fixed = re.sub(r"(?<=[?&])url=/([A-Za-z]:)", r"url=\1", fixed)
                # Strip file:// prefix (e.g. file:///C: → C:)
                fixed = re.sub(
                    r"(?<=[?&])url=file:/{2,3}([A-Za-z]:)", r"url=\1", fixed
                )
                # Strip encoded file:// prefix (e.g. file%3A%2F%2F%2FC: → C:)
                fixed = re.sub(
                    r"(?<=[?&])url=file%3A(?:%2F){2,3}([A-Za-z](?:%3A|:))",
                    lambda m: "url=" + m.group(1).replace("%3A", ":"),
                    fixed,
                )
                request.scope["query_string"] = fixed.encode("utf-8")
            return await call_next(request)

else:  # pragma: no cover
    # Stub class when TiTiler is unavailable
    class _WindowsEncodedPathFixMiddleware:  # type: ignore[no-redef]
        pass


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------


def create_titiler_app():  # type: ignore[return]
    """Return a TiTiler ASGI app configured for offline / LAN use.

    - GDAL env vars are already applied at module import time.
    - The Windows encoded-path fix middleware is added once (idempotent).
    - External HTTP is disabled via GDAL env vars set above.

    Returns a real TiTiler ``FastAPI`` instance when titiler is installed,
    or a minimal stub ``FastAPI`` app otherwise.

    Requirements: 11.1, 11.4, 16.4
    """
    if not _TITILER_AVAILABLE:
        # Return a minimal stub so the service can still start and serve /health
        from fastapi import FastAPI  # type: ignore[import]

        stub = FastAPI(title="TiTiler (stub — titiler not installed)")

        @stub.get("/health")
        async def _stub_health():  # type: ignore[return]
            return {"status": "degraded", "reason": "titiler not installed"}

        logger.warning("Returning stub TiTiler app because titiler is not installed.")
        return stub

    # Add the Windows path-fix middleware (idempotent guard)
    existing_middleware_classes = [m.cls for m in _titiler_app.user_middleware]
    if _WindowsEncodedPathFixMiddleware not in existing_middleware_classes:
        _titiler_app.add_middleware(_WindowsEncodedPathFixMiddleware)
        logger.debug("Added _WindowsEncodedPathFixMiddleware to TiTiler app.")

    return _titiler_app


def run_titiler(
    host: str | None = None,
    port: int | None = None,
    log_level: str | None = None,
) -> None:
    """Run the TiTiler ASGI app using uvicorn.

    Parameters default to values from ``shared.config.settings`` so that
    the service respects the centralized .env configuration.

    Args:
        host: Bind address. Defaults to ``settings.api_host``.
        port: TCP port. Defaults to ``settings.tile_service_port``.
        log_level: Uvicorn log level. Defaults to ``settings.log_level.lower()``.
    """
    if not _TITILER_AVAILABLE:  # pragma: no cover
        raise RuntimeError(
            "Cannot run TiTiler: the 'titiler[application]' package is not installed."
        )

    _host = host or settings.api_host
    _port = port or settings.tile_service_port
    _log_level = log_level or settings.log_level.lower()

    logger.info("Starting TiTiler on %s:%d (log_level=%s)", _host, _port, _log_level)

    import uvicorn as _uvicorn  # local import to avoid hard dependency at module level

    _uvicorn.run(
        create_titiler_app(),
        host=_host,
        port=_port,
        log_level=_log_level,
        access_log=False,
        timeout_keep_alive=5,
        backlog=max(128, (os.cpu_count() or 2) * 64),
    )


__all__ = ["create_titiler_app", "run_titiler"]
