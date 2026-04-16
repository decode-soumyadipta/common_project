from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SqlEnum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from offline_gis_app.db.base import Base


class RasterKind(str, Enum):
    GEOTIFF = "geotiff"
    JPEG2000 = "jpeg2000"
    MBTILES = "mbtiles"
    DEM = "dem"
    UNKNOWN = "unknown"


class RasterAsset(Base):
    __tablename__ = "raster_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    raster_kind: Mapped[RasterKind] = mapped_column(
        SqlEnum(RasterKind),
        nullable=False,
        default=RasterKind.UNKNOWN,
    )
    crs: Mapped[str] = mapped_column(String(128), nullable=False)
    bounds_wkt: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_x: Mapped[float] = mapped_column(nullable=False)
    resolution_y: Mapped[float] = mapped_column(nullable=False)
    width: Mapped[int] = mapped_column(nullable=False)
    height: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

