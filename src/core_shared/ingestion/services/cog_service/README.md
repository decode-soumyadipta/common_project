# COG Service

## Responsibility
Prepare large rasters for stable offline tile serving by converting non-COG sources into Cloud Optimized GeoTIFF where possible.

## Behavior
- Keeps original path when conversion is disabled or unsupported.
- Converts TIFF/JP2 sources into `.cog.tif` with deterministic COG creation options.
- Avoids overwrite by default unless `ingest_cog_overwrite=true`.

## Configuration
- `ingest_enable_cog_conversion`
- `ingest_cog_overwrite`
- `cog_blocksize`
- `cog_compression`
- `cog_overview_resampling`
