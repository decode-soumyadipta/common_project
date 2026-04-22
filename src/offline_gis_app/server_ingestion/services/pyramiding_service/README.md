# Pyramiding Service

## Responsibility
Apply overview pyramid strategy to optimize downstream tile rendering for large rasters.

## Contracts
- Input: source raster path.
- Output: boolean indicating whether pyramid was created.
- Must never hard-fail ingest for non-critical overview operations.

## Implementation Notes
- Overviews are built only when absent.
- Factor selection uses powers-of-two until overview dimensions would drop below baseline tile size.
- Service is invoked by ingestion pipeline preparation stage.
