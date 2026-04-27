from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session

from core_shared.db.models import RasterAsset, RasterKind
from core_shared.ingestion.services.metadata_models import RasterMetadata


ProgressCallback = Callable[[str], None]


@dataclass
class IngestionContext:
    source_path: Path
    session: Session
    progress_callback: ProgressCallback | None = None
    resume_from_stage: str | None = None
    working_path: Path | None = None
    raster_kind: RasterKind | None = None
    metadata: RasterMetadata | None = None
    asset: RasterAsset | None = None
    tile_url: str | None = None
    stages_completed: list[str] = field(default_factory=list)
    last_stage_completed: str | None = None

    def report(self, message: str) -> None:
        if self.progress_callback is not None:
            self.progress_callback(message)
