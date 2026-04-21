from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from offline_gis_app.db.base import Base
from offline_gis_app.server_backend.catalog.catalog_repository import CatalogRepository
from offline_gis_app.db.models import RasterKind
from offline_gis_app.server_ingestion.services.metadata_models import RasterMetadata
from offline_gis_app.utils.geometry import Bounds


def test_upsert_and_list_assets():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        repo = CatalogRepository(session)
        metadata = RasterMetadata(
            file_path=Path("/tmp/a.tif"),
            file_name="a.tif",
            kind=RasterKind.GEOTIFF,
            crs="EPSG:4326",
            bounds=Bounds(1, 2, 3, 4),
            resolution_x=0.2,
            resolution_y=0.2,
            width=256,
            height=256,
        )
        saved = repo.upsert_asset(metadata)
        assert saved.file_name == "a.tif"
        assert len(repo.list_assets()) == 1

