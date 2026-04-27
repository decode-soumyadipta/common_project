"""Compatibility DB session module for reorganized core_shared domain."""

from core_shared.db.session import SessionLocal, engine, get_session, init_db

__all__ = ["engine", "SessionLocal", "init_db", "get_session"]
