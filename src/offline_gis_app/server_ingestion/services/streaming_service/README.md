# Streaming Service

## Responsibility
Provide memory-safe chunked reads for ultra-large rasters.

## Behavior
- Iterates raster windows using a configurable chunk size.
- Supplies coarse memory estimates for workload planning.
- Intended for profile, analytics, and preprocessing flows that must avoid loading full rasters.

## Configuration
- `ingest_window_chunk_size`
- `ingest_memory_budget_mb`
