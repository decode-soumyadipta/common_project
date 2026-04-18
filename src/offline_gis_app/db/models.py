from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class IngestJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    PAUSED = "paused"


class IngestJobItemStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class IngestJob(Base):
    __tablename__ = "ingest_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[IngestJobStatus] = mapped_column(
        SqlEnum(IngestJobStatus),
        nullable=False,
        default=IngestJobStatus.QUEUED,
    )
    total_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checkpoint_item_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_checkpoint_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    items: Mapped[list["IngestJobItem"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class IngestJobItem(Base):
    __tablename__ = "ingest_job_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("ingest_jobs.id", ondelete="CASCADE"), nullable=False)
    item_index: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[IngestJobItemStatus] = mapped_column(
        SqlEnum(IngestJobItemStatus),
        nullable=False,
        default=IngestJobItemStatus.PENDING,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    asset_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("raster_assets.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    job: Mapped[IngestJob] = relationship(back_populates="items")

