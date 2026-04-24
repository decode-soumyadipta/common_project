from pathlib import Path
import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from offline_gis_app.server_ingestion.services.cog_service import CogPreparationService
from offline_gis_app.server_ingestion.services.ingestion_service import (
    BuildTileUrlStage,
    DetectRasterKindStage,
    ExtractMetadataStage,
    IngestionContext,
    IngestionPipeline,
    PersistCatalogStage,
    PrepareRasterStage,
    ValidatePathStage,
)
from offline_gis_app.server_ingestion.services.pyramiding_service import (
    RasterPyramidingService,
)
from offline_gis_app.server_ingestion.services.tiler_service import TiTilerUrlPolicy


LOGGER = logging.getLogger("services.ingest")


def _build_pipeline() -> IngestionPipeline:
    return IngestionPipeline(
        stages=[
            ValidatePathStage(),
            DetectRasterKindStage(),
            PrepareRasterStage(
                cog_service=CogPreparationService(),
                pyramiding_service=RasterPyramidingService(),
            ),
            ExtractMetadataStage(),
            PersistCatalogStage(),
            BuildTileUrlStage(url_policy=TiTilerUrlPolicy()),
        ]
    )


def register_raster(
    path: Path,
    session: Session,
    progress_callback: Callable[[str], None] | None = None,
    *,
    resume_from_stage: str | None = None,
    stage_checkpoint_callback: Callable[[str], None] | None = None,
) -> dict:
    """Register a raster in the catalog and return its API-facing payload."""
    context = IngestionContext(
        source_path=Path(path),
        session=session,
        progress_callback=progress_callback,
        resume_from_stage=resume_from_stage,
    )
    context = _build_pipeline().run(
        context, on_stage_completed=stage_checkpoint_callback
    )

    if context.metadata is None or context.asset is None or context.tile_url is None:
        raise RuntimeError(
            "Ingestion pipeline did not produce a complete asset payload"
        )

    if progress_callback:
        progress_callback("Metadata committed (source file remains on secure storage)")

    centroid_x, centroid_y = context.metadata.bounds.centroid()
    return {
        "id": context.asset.id,
        "file_name": context.asset.file_name,
        "file_path": context.asset.file_path,
        "kind": context.asset.raster_kind.value,
        "crs": context.asset.crs,
        "centroid": {"lon": centroid_x, "lat": centroid_y},
        "bounds_wkt": context.asset.bounds_wkt,
        "tile_url": context.tile_url,
    }
