"""FastAPI dependency injection for the Ingestion Service.

Provides reusable dependencies for:
- Database session (SQLAlchemy sync session via ``get_db``)
- Shared settings object via ``get_settings``
- GDAL pipeline instances via ``get_metadata_extractor``
- Format handler dispatch via ``get_format_handler``

Usage in route handlers::

    from src_new.services.ingestion.api.dependencies import get_db, get_settings

    @router.post("/upload")
    async def upload(
        file: UploadFile,
        db: Session = Depends(get_db),
        cfg: Settings = Depends(get_settings),
    ) -> UploadResponse:
        ...

Requirements: 6.1, 6.6, 9.6, 16.1
"""
from __future__ import annotations

import logging
from collections.abc import Generator
from pathlib import Path
from typing import Annotated, Optional

from fastapi import Depends
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from src_new.shared.config import Settings, settings as _default_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engine / session factory — built lazily from settings so tests can override
# ---------------------------------------------------------------------------

_engine = None
_SessionLocal = None


def _get_engine():
    """Return (and lazily create) the SQLAlchemy engine for the Ingestion Service."""
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

        # Enable WAL mode on SQLite for concurrent access during ingestion
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

        logger.info(
            "Ingestion Service database engine created: %s",
            db_url.split("@")[-1],
        )

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


# ---------------------------------------------------------------------------
# FastAPI dependency: database session
# ---------------------------------------------------------------------------


def get_db() -> Generator[Session, None, None]:
    """Yield a transactional SQLAlchemy session for each request.

    The session is automatically closed (and rolled back on error) after
    the request handler returns.

    Yields:
        Session: A SQLAlchemy ``Session`` bound to the Ingestion Service database.

    Example::

        @router.post("/upload")
        async def upload(file: UploadFile, db: Session = Depends(get_db)):
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


# ---------------------------------------------------------------------------
# FastAPI dependency: settings
# ---------------------------------------------------------------------------


def get_settings() -> Settings:
    """Return the shared Settings singleton.

    Injected into route handlers that need to read configuration values
    (e.g. data_root, max_upload_size, allowed hosts) without importing
    the global directly.

    Returns:
        The application-wide ``Settings`` instance loaded from ``.env``.
    """
    return _default_settings


# ---------------------------------------------------------------------------
# FastAPI dependency: GDAL metadata extractor pipeline
# ---------------------------------------------------------------------------


def get_metadata_extractor():
    """Return the GDAL metadata extractor function.

    Provides the ``extract_metadata`` callable from the GDAL pipelines
    module, ensuring GDAL env vars are applied before use.

    Returns:
        The ``extract_metadata`` function from
        ``src_new.services.ingestion.gdal_pipelines.metadata_extractor``.
    """
    from src_new.services.ingestion.gdal_pipelines.metadata_extractor import (
        extract_metadata,
    )

    # Apply GDAL env vars from config (Requirement 9.4)
    _default_settings.apply_gdal_env()
    return extract_metadata


# ---------------------------------------------------------------------------
# FastAPI dependency: format handler dispatch
# ---------------------------------------------------------------------------


def get_format_handler(file_extension: str) -> Optional[object]:
    """Return the appropriate format handler module for a given file extension.

    Dispatches to the correct handler based on the file extension:
    - ``.tif`` / ``.tiff`` → ``geotiff_handler``
    - ``.jp2`` / ``.j2k``  → ``jpeg2000_handler``
    - ``.mbtiles``         → ``mbtiles_handler``

    Args:
        file_extension: Lowercase file extension including the leading dot
                        (e.g. ``".tif"``).

    Returns:
        The handler module with ``validate`` and ``extract_metadata`` functions,
        or ``None`` if the extension is not supported.
    """
    ext = file_extension.lower()

    if ext in {".tif", ".tiff"}:
        from src_new.services.ingestion.format_handlers import geotiff_handler
        return geotiff_handler

    if ext in {".jp2", ".j2k"}:
        from src_new.services.ingestion.format_handlers import jpeg2000_handler
        return jpeg2000_handler

    if ext == ".mbtiles":
        from src_new.services.ingestion.format_handlers import mbtiles_handler
        return mbtiles_handler

    return None


# ---------------------------------------------------------------------------
# FastAPI dependency: data root path
# ---------------------------------------------------------------------------


def get_data_root() -> Path:
    """Return the configured data root directory.

    Reads ``DATA_ROOT`` from the centralized settings and ensures the
    directory exists before returning it.

    Returns:
        ``Path`` to the data root directory.
    """
    data_root = Path(_default_settings.data_root)
    data_root.mkdir(parents=True, exist_ok=True)
    return data_root


# ---------------------------------------------------------------------------
# Type aliases for cleaner route signatures
# ---------------------------------------------------------------------------

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]

__all__ = [
    "get_db",
    "get_settings",
    "get_metadata_extractor",
    "get_format_handler",
    "get_data_root",
    "DbSession",
    "AppSettings",
]
