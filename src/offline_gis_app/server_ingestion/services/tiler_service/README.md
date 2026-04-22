# Tiler Service

## Responsibility
Build and validate deterministic offline TiTiler URLs for supported raster sources.

## Contracts
- Input: normalized source path.
- Output: deterministic XYZ URL.
- Error model: recoverable URL policy errors should raise ValueError.

## Implementation Notes
- Runtime URL policy lives in `service.py` (`TiTilerUrlPolicy`).
- API routes and catalog serialization call a shared URL builder for consistency.
