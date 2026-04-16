from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from offline_gis_app.config.settings import settings
from offline_gis_app.db.base import Base


engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

