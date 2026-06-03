"""FastAPI dependency injection for the Query Service.

Provides reusable dependencies for:
- Database session (SQLAlchemy sync session via ``get_db``)
- Shared settings object via ``get_settings``
- Repository instances via ``get_raster_repository``

Usage in route handlers::

    from src_new.services.query.api.dependencies import get_db, get_raster_repository

    @router.get("/raster/{raster_id}")
    async def get_raster(
        raster_id: str,
        repo: RasterRepository = Depends(get_raster_repository),
    ) -> RasterMetadata:
        ...

Requirements: 6.3, 6.6
"""
from __future__ import annotations

import logging
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from src_new.shared.config import Settings, settings as _default_settings

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- Engine / session factory — built lazily from settings so tests can override ---------------------------------------------------------------------------

_engine = None
_SessionLocal = None


def _get_engine():
    """Return (and lazily create) the SQLAlchemy engine for the Query Service."""
    global _engine
    if _engine is None:
        db_url = _default_settings.database_url
        engine_kwargs: dict = {"future": True}

        if "sqlite" in db_url:
            engine_kwargs["connect_args"] = {
                "timeout": 30,
                "check_same_thread": False,
            }

        _engine = create_engine(db_url, **engine_kwargs)

        # Enable WAL mode on SQLite for concurrent access
        if "sqlite" in db_url:
            @event.listens_for(_engine, "connect")
            def _set_sqlite_pragma(dbapi_conn, _record):
                try:
                    cursor = dbapi_conn.cursor()
                    cursor.execute("PRAGMA journal_mode=WAL;")
                    cursor.execute("PRAGMA synchronous=NORMAL;")
                    cursor.execute("PRAGMA busy_timeout=30000;")
                    cursor.close()
                except Exception:
                    pass

        logger.info("Query Service database engine created: %s", db_url.split("@")[-1])

        try:
            from src_new.shared.models.raster_asset_orm import migrate_database_schema
            migrate_database_schema(_engine)
        except Exception as e:
            logger.warning("Failed to run database migration on engine creation: %s", e)

    return _engine


def _get_session_factory():
    """Return (and lazily create) the SQLAlchemy session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=_get_engine(),
            autoflush=False,
            autocommit=False,
            class_=Session,
        )
    return _SessionLocal


# --------------------------------------------------------------------------- FastAPI dependency: database session ---------------------------------------------------------------------------


def get_db() -> Generator[Session, None, None]:
    """Yield a transactional SQLAlchemy session for each request.

    The session is automatically closed (and rolled back on error) after
    the request handler returns.

    Yields:
        Session: A SQLAlchemy ``Session`` bound to the Query Service database.

    Example::

        @router.get("/raster/{raster_id}")
        def get_raster(raster_id: str, db: Session = Depends(get_db)):
            ...
    """
    SessionLocal = _get_session_factory()
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# --------------------------------------------------------------------------- FastAPI dependency: settings ---------------------------------------------------------------------------


def get_settings() -> Settings:
    """Return the shared Settings singleton.

    Injected into route handlers that need to read configuration values
    (e.g. service URLs, allowed hosts) without importing the global directly.

    Returns:
        The application-wide ``Settings`` instance loaded from ``.env``.
    """
    return _default_settings


# --------------------------------------------------------------------------- FastAPI dependency: RasterRepository ---------------------------------------------------------------------------


def get_raster_repository(
    db: Annotated[Session, Depends(get_db)],
) -> "RasterRepository":  # noqa: F821 — forward ref resolved at runtime
    """Provide a ``RasterRepository`` bound to the current request's DB session.

    Args:
        db: SQLAlchemy session injected by ``get_db``.

    Returns:
        A ``RasterRepository`` instance ready for use in the route handler.
    """
    from src_new.services.query.repositories.raster_repository import RasterRepository

    return RasterRepository(db)


# --------------------------------------------------------------------------- Type aliases for cleaner route signatures ---------------------------------------------------------------------------

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]

__all__ = [
    "get_db",
    "get_settings",
    "get_raster_repository",
    "DbSession",
    "AppSettings",
]
