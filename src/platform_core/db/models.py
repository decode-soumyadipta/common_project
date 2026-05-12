from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_core.db.base import Base


class RasterKind(str, Enum):
    """Supported raster source categories."""

    GEOTIFF = "geotiff"
    JPEG2000 = "jpeg2000"
    MBTILES = "mbtiles"
    DEM = "dem"
    UNKNOWN = "unknown"
    
    @classmethod
    def _missing_(cls, value):
        """Handle case-insensitive enum lookup."""
        if isinstance(value, str):
            value_lower = value.lower()
            for member in cls:
                if member.value.lower() == value_lower:
                    return member
        return cls.UNKNOWN


class RasterAsset(Base):
    """Catalog entry for an ingested raster source."""

    __tablename__ = "raster_assets"

    # Map to actual database column names
    id: Mapped[str] = mapped_column("raster_id", String(36), primary_key=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    raster_kind: Mapped[str] = mapped_column(
        "kind",
        String(20),
        nullable=False,
        default="unknown",
    )
    crs: Mapped[str] = mapped_column(String(128), nullable=False)
    # Store bounds as separate columns instead of WKT
    min_lon: Mapped[float] = mapped_column(nullable=False)
    min_lat: Mapped[float] = mapped_column(nullable=False)
    max_lon: Mapped[float] = mapped_column(nullable=False)
    max_lat: Mapped[float] = mapped_column(nullable=False)
    resolution_x: Mapped[float] = mapped_column(nullable=False)
    resolution_y: Mapped[float] = mapped_column(nullable=False)
    width: Mapped[int] = mapped_column(nullable=False)
    height: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column("upload_date", DateTime, default=datetime.utcnow)
    # Note: updated_at column doesn't exist in the legacy schema, so we make it optional and don't query it
    # updated_at: Mapped[datetime] = mapped_column(
    #     DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True
    # )
    
    @property
    def bounds_wkt(self) -> str:
        """Generate WKT polygon from bounding box coordinates."""
        return (
            f"POLYGON(("
            f"{self.min_lon} {self.min_lat}, "
            f"{self.max_lon} {self.min_lat}, "
            f"{self.max_lon} {self.max_lat}, "
            f"{self.min_lon} {self.max_lat}, "
            f"{self.min_lon} {self.min_lat}"
            f"))"
        )


class IngestJobStatus(str, Enum):
    """Lifecycle states for background ingest jobs."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    PAUSED = "paused"


class IngestJobItemStatus(str, Enum):
    """Processing states for individual files in an ingest job."""

    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class IngestJob(Base):
    """Top-level ingest queue job with progress counters and timestamps."""

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
    checkpoint_item_index: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_checkpoint_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    items: Mapped[list["IngestJobItem"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class IngestJobItem(Base):
    """Per-file work item associated with an ingest job."""

    __tablename__ = "ingest_job_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ingest_jobs.id", ondelete="CASCADE"), nullable=False
    )
    item_index: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[IngestJobItemStatus] = mapped_column(
        SqlEnum(IngestJobItemStatus),
        nullable=False,
        default=IngestJobItemStatus.PENDING,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checkpoint_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stage_attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_checkpoint_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    asset_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("raster_assets.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    job: Mapped[IngestJob] = relationship(back_populates="items")
