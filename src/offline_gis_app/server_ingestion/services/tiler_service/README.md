# Tiler Service Template

## Responsibility
Build and validate tile URLs for supported raster sources.

## Contracts
- Input: normalized source path.
- Output: deterministic XYZ URL.
- Error model: recoverable URL policy errors should raise ValueError.

## Implementation Notes
- Keep runtime policy isolated from API route logic.
- Add provider adapters under this folder as needed.
