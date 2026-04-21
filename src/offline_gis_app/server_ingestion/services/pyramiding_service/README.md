# Pyramiding Service Template

## Responsibility
Apply overview pyramid strategy to optimize downstream tile rendering.

## Contracts
- Input: source raster path.
- Output: boolean indicating whether pyramid was created.
- Must never hard-fail ingest for non-critical overview operations.
