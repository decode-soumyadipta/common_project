"""LAN security middleware for IP-based access control.

Implements FastAPI middleware that restricts API access to a configurable
allowlist of LAN IP addresses. Designed for air-gapped government LAN
deployments where network-level isolation is the primary security boundary.

Requirements: 16.1, 16.2, 16.5, 16.6

Usage — apply to any FastAPI app:

    from src_new.shared.auth.lan_security import LANSecurityMiddleware, get_bind_host

    app = FastAPI()
    app.add_middleware(LANSecurityMiddleware)

    # Determine the correct bind host for uvicorn:
    host = get_bind_host()  # "0.0.0.0" or settings.api_host
"""
from __future__ import annotations

import ipaddress
import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from src_new.shared.config import settings

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- Helpers ---------------------------------------------------------------------------


def _parse_allowed_hosts(raw: str) -> list[str]:
    """Parse a comma-separated ALLOWED_HOSTS string into a clean list.

    Falls back to ``["127.0.0.1", "::1"]`` (localhost only) when the raw
    value is empty or contains only whitespace, satisfying Requirement 16.6
    (missing env var → localhost-only fallback).

    Args:
        raw: Comma-separated IP addresses or CIDR ranges, e.g.
             ``"192.168.1.0/24,10.0.0.5,127.0.0.1"``.

    Returns:
        List of stripped, non-empty host strings.
    """
    hosts = [h.strip() for h in raw.split(",") if h.strip()]
    if not hosts:
        logger.warning(
            "ALLOWED_HOSTS is not configured or is empty. "
            "Falling back to localhost-only access (127.0.0.1, ::1). "
            "Set ALLOWED_HOSTS in .env for LAN deployment."
        )
        return ["127.0.0.1", "::1"]
    return hosts


def _is_ip_allowed(client_ip: str, allowed: list[str]) -> bool:
    """Check whether *client_ip* is permitted by the *allowed* list.

    Each entry in *allowed* may be:
    - A single IPv4 or IPv6 address (``"192.168.1.10"``)
    - A CIDR network range (``"192.168.1.0/24"``, ``"10.0.0.0/8"``)

    Args:
        client_ip: The IP address string extracted from the incoming request.
        allowed:   List of allowed IP addresses / CIDR ranges.

    Returns:
        ``True`` if the IP is permitted, ``False`` otherwise.
    """
    try:
        client_addr = ipaddress.ip_address(client_ip)
    except ValueError:
        logger.warning("Could not parse client IP address: %r", client_ip)
        return False

    for entry in allowed:
        try:
            # Try CIDR network first (e.g. "192.168.1.0/24")
            network = ipaddress.ip_network(entry, strict=False)
            if client_addr in network:
                return True
        except ValueError:
            # Not a valid network — skip silently
            logger.debug("Skipping invalid ALLOWED_HOSTS entry: %r", entry)

    return False


def _extract_client_ip(request: Request) -> str:
    """Extract the real client IP from the request.

    Checks ``X-Forwarded-For`` first (for reverse-proxy deployments), then
    falls back to the direct connection address from ``request.client``.

    Args:
        request: The incoming Starlette/FastAPI request.

    Returns:
        The client IP address string, or ``"unknown"`` if it cannot be
        determined.
    """
    # X-Forwarded-For may contain a comma-separated chain; take the first entry
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    if request.client and request.client.host:
        return request.client.host

    return "unknown"


# --------------------------------------------------------------------------- Middleware ---------------------------------------------------------------------------


class LANSecurityMiddleware(BaseHTTPMiddleware):
    """FastAPI/Starlette middleware enforcing IP-based LAN access control.

    On every incoming request the middleware:
    1. Extracts the client IP (honouring ``X-Forwarded-For`` for proxies).
    2. Checks the IP against the ``ALLOWED_HOSTS`` list from
       ``src_new.shared.config.settings``.
    3. Returns **HTTP 403 Forbidden** with a JSON body for disallowed IPs
       and logs the attempt at WARNING level (Requirement 16.6).
    4. Passes the request through unchanged for allowed IPs.

    The allowlist is resolved once at middleware instantiation time so that
    repeated requests do not re-parse the config string.

    Example::

        app = FastAPI()
        app.add_middleware(LANSecurityMiddleware)
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._allowed_hosts: list[str] = _parse_allowed_hosts(settings.allowed_hosts)
        logger.info(
            "LANSecurityMiddleware initialised. Allowed hosts: %s",
            self._allowed_hosts,
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Intercept every request and enforce the IP allowlist."""
        client_ip = _extract_client_ip(request)

        if not _is_ip_allowed(client_ip, self._allowed_hosts):
            logger.warning(
                "Unauthorized access attempt from IP %r — path: %s %s",
                client_ip,
                request.method,
                request.url.path,
            )
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "Forbidden: your IP address is not authorised to access this service.",
                    "client_ip": client_ip,
                },
            )

        return await call_next(request)


# --------------------------------------------------------------------------- Bind-host helper ---------------------------------------------------------------------------


def get_bind_host() -> str:
    """Return the host interface that services should bind to.

    Implements Requirement 16.2: services bind to the LAN interface
    (``settings.api_host``) by default. They only bind to ``0.0.0.0`` when
    ``BIND_ALL_INTERFACES=true`` is explicitly set in the environment.

    Returns:
        ``"0.0.0.0"`` when ``settings.bind_all_interfaces`` is ``True``,
        otherwise ``settings.api_host`` (e.g. ``"192.168.1.10"``).

    Example::

        import uvicorn
        from src_new.shared.auth.lan_security import get_bind_host

        uvicorn.run(app, host=get_bind_host(), port=settings.api_port)
    """
    if settings.bind_all_interfaces:
        logger.warning(
            "BIND_ALL_INTERFACES=true — service will bind to 0.0.0.0. "
            "Ensure firewall rules are in place for LAN security."
        )
        return "0.0.0.0"
    return settings.api_host


# --------------------------------------------------------------------------- Public API ---------------------------------------------------------------------------

__all__ = [
    "LANSecurityMiddleware",
    "get_bind_host",
    # Exposed for testing / advanced use
    "_parse_allowed_hosts",
    "_is_ip_allowed",
    "_extract_client_ip",
]
