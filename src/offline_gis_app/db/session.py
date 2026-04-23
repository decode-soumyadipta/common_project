import logging
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from offline_gis_app.config.settings import settings
from offline_gis_app.db.base import Base
from offline_gis_app.db.migrations.runner import apply_migrations


LOGGER = logging.getLogger("db.session")

engine = create_engine(settings.database_url, future=True)

# Enable PostGIS extension on PostgreSQL
if 'postgresql' in settings.database_url:
    @event.listens_for(engine, "connect")
    def enable_postgis(dbapi_conn, _connection_record):
        try:
            with dbapi_conn.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
                dbapi_conn.commit()
        except Exception:  # noqa: BLE001
            dbapi_conn.rollback()
            LOGGER.debug("PostGIS extension activation skipped during connection setup", exc_info=True)

# Enable WAL mode on SQLite for concurrent read/write (Server/Client processes)
if 'sqlite' in settings.database_url:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        try:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.close()
        except Exception:
            pass

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


def init_db() -> None:
    """Initialize database: create tables and apply migrations."""
    Base.metadata.create_all(bind=engine)
    try:
        apply_migrations(engine)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Migration failed during database initialization: %s", exc)


def get_session() -> Generator[Session, None, None]:
    """Yield a transactional SQLAlchemy session for request handlers."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

