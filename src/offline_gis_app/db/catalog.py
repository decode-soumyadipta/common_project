from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from offline_gis_app.db.models import RasterAsset
from offline_gis_app.services.metadata_models import RasterMetadata


class CatalogRepository:
    def __init__(self, session: Session):
        self._session = session

    def upsert_asset(self, metadata: RasterMetadata) -> RasterAsset:
        existing = self.get_by_path(str(metadata.file_path))
        if existing:
            existing.crs = metadata.crs
            existing.bounds_wkt = metadata.bounds.to_wkt_polygon()
            existing.resolution_x = metadata.resolution_x
            existing.resolution_y = metadata.resolution_y
            existing.width = metadata.width
            existing.height = metadata.height
            existing.raster_kind = metadata.kind
            self._session.add(existing)
            self._session.commit()
            self._session.refresh(existing)
            return existing

        asset = RasterAsset(
            id=str(uuid4()),
            file_path=str(metadata.file_path),
            file_name=metadata.file_name,
            raster_kind=metadata.kind,
            crs=metadata.crs,
            bounds_wkt=metadata.bounds.to_wkt_polygon(),
            resolution_x=metadata.resolution_x,
            resolution_y=metadata.resolution_y,
            width=metadata.width,
            height=metadata.height,
        )
        self._session.add(asset)
        self._session.commit()
        self._session.refresh(asset)
        return asset

    def get_by_path(self, file_path: str) -> RasterAsset | None:
        stmt = select(RasterAsset).where(RasterAsset.file_path == file_path)
        return self._session.scalar(stmt)

    def list_assets(self) -> list[RasterAsset]:
        stmt = select(RasterAsset).order_by(RasterAsset.created_at.desc())
        return list(self._session.scalars(stmt))

