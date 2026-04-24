"""Ingestion workflow stages and pipeline."""

from offline_gis_app.server_ingestion.services.ingestion_service.context import (
    IngestionContext,
)
from offline_gis_app.server_ingestion.services.ingestion_service.contracts import (
    IngestionStage,
)
from offline_gis_app.server_ingestion.services.ingestion_service.pipeline import (
    IngestionPipeline,
)
from offline_gis_app.server_ingestion.services.ingestion_service.stages import (
    BuildTileUrlStage,
    DetectRasterKindStage,
    ExtractMetadataStage,
    PersistCatalogStage,
    PrepareRasterStage,
    ValidatePathStage,
)

__all__ = [
    "IngestionContext",
    "IngestionPipeline",
    "IngestionStage",
    "ValidatePathStage",
    "DetectRasterKindStage",
    "PrepareRasterStage",
    "ExtractMetadataStage",
    "PersistCatalogStage",
    "BuildTileUrlStage",
]
