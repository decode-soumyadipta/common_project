"""Ingestion workflow stages and pipeline."""

from core_shared.ingestion.services.ingestion_service.context import (
    IngestionContext,
)
from core_shared.ingestion.services.ingestion_service.contracts import (
    IngestionStage,
)
from core_shared.ingestion.services.ingestion_service.pipeline import (
    IngestionPipeline,
)
from core_shared.ingestion.services.ingestion_service.stages import (
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
