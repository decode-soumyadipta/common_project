from __future__ import annotations

from dataclasses import dataclass
import logging

from core_shared.ingestion.services.cog_service import CogPreparationService
from core_shared.ingestion.services.file_kind import detect_raster_kind
from core_shared.ingestion.services.ingestion_service.context import (
    IngestionContext,
)
from core_shared.ingestion.services.ingestion_service.contracts import (
    IngestionStage,
)
from core_shared.ingestion.services.metadata_extractor import (
    extract_metadata,
)
from core_shared.ingestion.services.pyramiding_service import (
    RasterPyramidingService,
)
from core_shared.ingestion.services.tiler_service import TiTilerUrlPolicy

LOGGER = logging.getLogger("services.ingest.stages")


@dataclass(frozen=True)
class ValidatePathStage(IngestionStage):
    name: str = "validate_source_path"
    message: str = "Validating source path"

    def run(self, context: IngestionContext) -> None:
        if not context.source_path.exists():
            raise FileNotFoundError(
                f"Raster path does not exist: {context.source_path}"
            )
        resolved = context.source_path.resolve()
        if resolved.suffix.lower() == ".j2k":
            jp2_candidate = resolved.with_suffix(".jp2")
            if jp2_candidate.exists():
                LOGGER.info(
                    "Preferring JP2 container over J2K codestream for %s -> %s",
                    resolved.name,
                    jp2_candidate.name,
                )
                resolved = jp2_candidate.resolve()
        context.working_path = resolved


@dataclass(frozen=True)
class DetectRasterKindStage(IngestionStage):
    name: str = "detect_raster_kind"
    message: str = "Classifying raster type"

    def run(self, context: IngestionContext) -> None:
        if context.working_path is None:
            raise ValueError("working_path is required before kind detection")
        context.raster_kind = detect_raster_kind(context.working_path)


@dataclass(frozen=True)
class PrepareRasterStage(IngestionStage):
    cog_service: CogPreparationService
    pyramiding_service: RasterPyramidingService
    name: str = "prepare_raster"
    message: str = "Preparing COG/overviews for large-raster tiling"

    def run(self, context: IngestionContext) -> None:
        if context.working_path is None:
            raise ValueError("working_path is required before preparation")
        prepared = self.cog_service.prepare(context.working_path)
        context.working_path = prepared.working_path
        self.pyramiding_service.ensure(context.working_path)


@dataclass(frozen=True)
class ExtractMetadataStage(IngestionStage):
    name: str = "extract_metadata"
    message: str = "Extracting raster metadata"

    def run(self, context: IngestionContext) -> None:
        if context.working_path is None:
            raise ValueError("working_path is required before metadata extraction")
        context.metadata = extract_metadata(context.working_path)


@dataclass(frozen=True)
class PersistCatalogStage(IngestionStage):
    name: str = "persist_catalog"
    message: str = "Writing metadata to catalog"

    def run(self, context: IngestionContext) -> None:
        if context.metadata is None:
            raise ValueError("metadata is required before catalog persistence")
        from server_vm.server_backend.catalog.catalog_repository import (
            CatalogRepository,
        )

        repo = CatalogRepository(context.session)
        context.asset = repo.upsert_asset(context.metadata)


@dataclass(frozen=True)
class BuildTileUrlStage(IngestionStage):
    url_policy: TiTilerUrlPolicy
    name: str = "publish_tile_url"
    message: str = "Building tile URL"

    def run(self, context: IngestionContext) -> None:
        if context.asset is None:
            raise ValueError("asset is required before tile URL generation")
        context.tile_url = self.url_policy.build_url(context.asset.file_path)
