"""Compatibility DB session module for reorganized platform_core domain."""

from platform_core.db.session import SessionLocal, engine, get_session, init_db

__all__ = ["engine", "SessionLocal", "init_db", "get_session"]
