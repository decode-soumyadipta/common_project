"""SQLAlchemy ORM model for raster_assets table.

This module defines the RasterAsset ORM class that matches the actual
database schema used by both the Ingestion and Query services.

The schema includes columns for:
- Asset identification: raster_id, file_path, file_name
- Asset metadata: kind, crs, resolution, dimensions
- Spatial bounds: min_lon, min_lat, max_lon, max_lat
- Timestamps: upload_date, created_at

This ORM model is used by the Query Service repository to query assets
from the raster_assets table.
"""

from sqlalchemy import Column, DateTime, Float, Integer, String
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class RasterAsset(Base):
    """SQLAlchemy ORM model for the raster_assets table.

    Matches the schema created and populated by the Ingestion Service.
    """

    __tablename__ = "raster_assets"

    # Primary key: raster_id (file name)
    raster_id = Column(String, primary_key=True, nullable=False)

    # File storage
    file_path = Column(String, nullable=False, unique=True)
    file_name = Column(String, nullable=False)

    # Asset type and spatial reference
    kind = Column(String, nullable=False)  # "dem", "geotiff", etc.
    crs = Column(String, nullable=False)  # e.g. "EPSG:4326"

    # Spatial bounds (bounding box in WGS84)
    min_lon = Column(Float, nullable=False)
    min_lat = Column(Float, nullable=False)
    max_lon = Column(Float, nullable=False)
    max_lat = Column(Float, nullable=False)

    # Raster dimensions and resolution
    resolution_x = Column(Float, nullable=False)
    resolution_y = Column(Float, nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)

    # Timestamps
    upload_date = Column(DateTime, nullable=True)  # ISO format timestamp from ingestion

    def __repr__(self) -> str:
        return (
            f"<RasterAsset("
            f"raster_id={self.raster_id!r}, "
            f"file_name={self.file_name!r}, "
            f"kind={self.kind!r}, "
            f"bbox=[{self.min_lon}, {self.min_lat}, "
            f"{self.max_lon}, {self.max_lat}]"
            f")>"
        )
