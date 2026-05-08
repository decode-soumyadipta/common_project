# Ingestion Service

## Responsibility
Compose deterministic ingestion stages for validation, preparation, metadata extraction, persistence, and URL publication.

## Contracts
- Stage ordering is deterministic via `IngestionPipeline`.
- Stage failures bubble with source context from `IngestionContext`.
- Retry policy remains orchestrated by queue service, not stage implementation.

## Implemented Stages
- `ValidatePathStage`
- `DetectRasterKindStage`
- `PrepareRasterStage` (COG + pyramids)
- `ExtractMetadataStage`
- `PersistCatalogStage`
- `BuildTileUrlStage`
