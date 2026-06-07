"""Shared authentication and LAN security package.

Public exports:
    LANSecurityMiddleware  — FastAPI middleware for IP-based access control
    get_bind_host          — Returns the correct bind host for uvicorn
"""
from src_new.shared.auth.lan_security import LANSecurityMiddleware, get_bind_host

__all__ = ["LANSecurityMiddleware", "get_bind_host"]
