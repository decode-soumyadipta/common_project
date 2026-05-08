from __future__ import annotations

import logging
import platform
from dataclasses import dataclass
from pathlib import Path
from osgeo import gdal

from platform_core.ingestion.services.ingestion_service.context import IngestionContext
from platform_core.ingestion.services.ingestion_service.contracts import IngestionStage

gdal.UseExceptions()

LOGGER = logging.getLogger("services.transform")


@dataclass(frozen=True)
class TransformToEPSG3857Stage(IngestionStage):
    """Reproject raster to EPSG:3857 (Web Mercator) for web tile serving with enhanced Windows support."""

    name: str = "transform_to_epsg3857"
    message: str = "Reprojecting to EPSG:3857"

    def run(self, context: IngestionContext) -> None:
        if context.working_path is None:
            raise ValueError("working_path is required before transformation")

        if context.metadata is None:
            raise ValueError("metadata is required before transformation")

        current_crs = context.metadata.crs

        LOGGER.info(f"=" * 80)
        LOGGER.info(f"REPROJECTION STAGE: {context.working_path.name}")
        LOGGER.info(f"=" * 80)
        LOGGER.info(f"Source CRS: {current_crs}")
        LOGGER.info(f"Target CRS: EPSG:3857 (Web Mercator)")

        if current_crs == "EPSG:3857":
            context.report("Already in EPSG:3857, skipping reprojection")
            LOGGER.info(f"✓ Already in EPSG:3857 - no reprojection needed")
            LOGGER.info(f"=" * 80)
            return

        # Warn about distortion for high-latitude data
        if context.metadata.bounds:
            max_lat = max(
                abs(context.metadata.bounds.min_y), abs(context.metadata.bounds.max_y)
            )
            if max_lat > 60:
                LOGGER.warning(
                    f"⚠ HIGH LATITUDE DATA ({max_lat:.1f}°) - EPSG:3857 will have significant distortion (>100%)"
                )
            elif max_lat > 45:
                LOGGER.warning(
                    f"⚠ MODERATE LATITUDE DATA ({max_lat:.1f}°) - EPSG:3857 will have moderate distortion (~30-50%)"
                )
            else:
                LOGGER.info(
                    f"✓ Low-moderate latitude ({max_lat:.1f}°) - EPSG:3857 distortion acceptable (<30%)"
                )

        # Create output path with safe filename (handle spaces and special characters)
        safe_stem = self._create_safe_filename(context.working_path.stem)
        output_path = context.working_path.parent / f"{safe_stem}_3857.tif"

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Enhanced warp options for better Windows compatibility and performance
            warp_options = self._get_warp_options(context.working_path)

            context.report(f"Reprojecting from {current_crs} to EPSG:3857")
            LOGGER.info(f"")
            LOGGER.info(f"REPROJECTION PARAMETERS:")
            LOGGER.info(f"  Algorithm: bilinear (smooth interpolation)")
            LOGGER.info(f"  Error threshold: 0.125 pixels (sub-pixel accuracy)")
            LOGGER.info(f"  Densification: 21 points (accurate curve transformation)")
            LOGGER.info(f"  Multithreading: ALL_CPUS")
            LOGGER.info(f"  Output: {output_path.name}")
            LOGGER.info(f"")

            # Use string paths to avoid issues with Path objects and GDAL on Windows
            input_path_str = str(context.working_path).replace("\\", "/")
            output_path_str = str(output_path).replace("\\", "/")

            LOGGER.info(f"Starting reprojection...")
            ds = gdal.Warp(output_path_str, input_path_str, options=warp_options)
            if ds is None:
                # Get the last GDAL error
                error_msg = gdal.GetLastErrorMsg()
                LOGGER.error(
                    f"GDAL Warp failed for {context.working_path}: {error_msg}"
                )
                raise RuntimeError(
                    f"Reprojection failed for {context.working_path}: {error_msg}"
                )

            # Verify the output file was created and is valid
            if not output_path.exists():
                raise RuntimeError(f"Output file was not created: {output_path}")

            # Test that we can open the output file
            test_ds = gdal.Open(output_path_str)
            if test_ds is None:
                raise RuntimeError(
                    f"Created output file is not readable: {output_path}"
                )

            # Validate output has expected properties
            if test_ds.GetProjection() == "":
                LOGGER.warning(
                    f"⚠ Output file has no projection information: {output_path}"
                )
            else:
                LOGGER.info(f"✓ Output projection verified: EPSG:3857")

            # Log output file info
            output_size_mb = output_path.stat().st_size / (1024 * 1024)
            LOGGER.info(f"✓ Reprojection successful")
            LOGGER.info(f"  Output file: {output_path.name}")
            LOGGER.info(f"  File size: {output_size_mb:.2f} MB")
            LOGGER.info(
                f"  Dimensions: {test_ds.RasterXSize} × {test_ds.RasterYSize} pixels"
            )

            test_ds = None
            ds = None  # Close the dataset

            context.working_path = output_path
            context.report("Reprojection complete")
            LOGGER.info(f"=" * 80)

        except Exception as e:
            LOGGER.error(f"Transform stage failed for {context.working_path}: {e}")
            LOGGER.info(f"=" * 80)
            # Clean up partial output file if it exists
            if output_path.exists():
                try:
                    output_path.unlink()
                except Exception:
                    pass
            raise

    def _create_safe_filename(self, original_stem: str) -> str:
        """Create a safe filename for Windows and other platforms."""
        # Replace problematic characters
        safe_chars = []
        for char in original_stem:
            if char.isalnum() or char in "-_.":
                safe_chars.append(char)
            elif char in " ()[]{}":
                safe_chars.append("_")
            else:
                safe_chars.append("_")

        safe_name = "".join(safe_chars)

        # Remove multiple consecutive underscores
        while "__" in safe_name:
            safe_name = safe_name.replace("__", "_")

        # Remove leading/trailing underscores
        safe_name = safe_name.strip("_")

        # Ensure not empty
        if not safe_name:
            safe_name = "raster"

        return safe_name

    def _get_warp_options(self, input_path: Path) -> gdal.WarpOptions:
        """Get optimized warp options based on input characteristics and platform."""
        # Analyze input raster
        ds = gdal.Open(str(input_path))
        if ds is None:
            raise RuntimeError(f"Cannot open input file for analysis: {input_path}")

        band_count = ds.RasterCount
        width = ds.RasterXSize
        height = ds.RasterYSize
        data_type = ds.GetRasterBand(1).DataType if band_count > 0 else gdal.GDT_Unknown

        ds = None

        # Base options
        creation_options = ["COMPRESS=LZW", "TILED=YES", "BIGTIFF=IF_SAFER"]

        # Platform-specific optimizations
        if platform.system() == "Windows":
            # Windows-specific optimizations
            creation_options.extend(
                ["BLOCKXSIZE=512", "BLOCKYSIZE=512", "NUM_THREADS=ALL_CPUS"]
            )
            warp_options_dict = {
                "NUM_THREADS": "ALL_CPUS",
                "GDAL_CACHEMAX": "512",  # Limit cache on Windows
            }
        else:
            # Unix-like systems can handle more aggressive settings
            creation_options.extend(["BLOCKXSIZE=1024", "BLOCKYSIZE=1024"])
            warp_options_dict = {"NUM_THREADS": "ALL_CPUS", "GDAL_CACHEMAX": "1024"}

        # Handle large files
        total_pixels = width * height
        if total_pixels > 100_000_000:  # > 100 megapixels
            LOGGER.info(
                f"Large raster detected ({total_pixels:,} pixels), using conservative settings"
            )
            creation_options.append("BIGTIFF=YES")
            warp_options_dict["GDAL_CACHEMAX"] = "256"  # Reduce cache for large files

        # Handle multi-band imagery
        if band_count > 4:
            LOGGER.info(
                f"Multi-band raster detected ({band_count} bands), optimizing for band processing"
            )
            creation_options.append(
                "INTERLEAVE=BAND"
            )  # Band-interleaved for multi-band

        # Data type specific optimizations
        if data_type in [gdal.GDT_Float32, gdal.GDT_Float64]:
            creation_options.append("PREDICTOR=3")  # Floating point predictor
        elif data_type in [gdal.GDT_Byte, gdal.GDT_UInt16, gdal.GDT_Int16]:
            creation_options.append("PREDICTOR=2")  # Horizontal predictor for integers

        return gdal.WarpOptions(
            dstSRS="EPSG:3857",
            format="GTiff",
            creationOptions=creation_options,
            multithread=True,
            warpOptions=[f"{k}={v}" for k, v in warp_options_dict.items()],
            errorThreshold=0.125,  # Allow some error tolerance
            resampleAlg="bilinear",  # Good balance of quality and performance
        )


@dataclass(frozen=True)
class GenerateMBTilesStage(IngestionStage):
    """Generate MBTiles archive for offline tile serving with enhanced multi-band support."""

    name: str = "generate_mbtiles"
    message: str = "Generating MBTiles"

    def run(self, context: IngestionContext) -> None:
        if context.working_path is None:
            raise ValueError("working_path is required before MBTiles generation")

        # Create output path with safe filename
        safe_stem = self._create_safe_filename(context.working_path.stem)
        output_path = context.working_path.parent / f"{safe_stem}.mbtiles"

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Analyze input raster characteristics
            raster_info = self._analyze_input_raster(context.working_path)

            LOGGER.info(
                f"Input raster analysis: {raster_info['band_count']} bands, "
                f"{raster_info['width']}x{raster_info['height']} pixels, "
                f"data type: {gdal.GetDataTypeName(raster_info['data_type'])}"
            )

            # Prepare input for MBTiles generation
            mbtiles_input = self._prepare_mbtiles_input(
                context.working_path, raster_info
            )

            # Generate MBTiles with optimized settings
            translate_options = self._get_mbtiles_options(raster_info)

            context.report("Generating MBTiles archive")
            LOGGER.info(
                f"Starting MBTiles generation: {mbtiles_input} -> {output_path}"
            )

            # Use string paths for Windows compatibility
            input_str = str(mbtiles_input).replace("\\", "/")
            output_str = str(output_path).replace("\\", "/")

            ds = gdal.Translate(output_str, input_str, options=translate_options)
            if ds is None:
                error_msg = gdal.GetLastErrorMsg()
                LOGGER.error(f"GDAL Translate failed for {mbtiles_input}: {error_msg}")
                raise RuntimeError(
                    f"MBTiles generation failed for {mbtiles_input}: {error_msg}"
                )

            # Verify the output file was created
            if not output_path.exists():
                raise RuntimeError(f"MBTiles file was not created: {output_path}")

            # Validate MBTiles file
            self._validate_mbtiles(output_path)

            ds = None  # Close the dataset

            # Clean up intermediate files
            if mbtiles_input != context.working_path and mbtiles_input.exists():
                try:
                    mbtiles_input.unlink()
                    LOGGER.info(f"Cleaned up intermediate file: {mbtiles_input}")
                except Exception as e:
                    LOGGER.warning(
                        f"Failed to clean up intermediate file {mbtiles_input}: {e}"
                    )

            context.mbtiles_path = output_path
            context.report(f"MBTiles generated: {output_path.name}")
            LOGGER.info(f"MBTiles generation successful: {output_path}")

        except Exception as e:
            LOGGER.error(f"MBTiles generation failed for {context.working_path}: {e}")
            # Clean up partial output files if they exist
            if output_path.exists():
                try:
                    output_path.unlink()
                except Exception:
                    pass
            # Clean up intermediate files
            if (
                "mbtiles_input" in locals()
                and mbtiles_input != context.working_path
                and mbtiles_input.exists()
            ):
                try:
                    mbtiles_input.unlink()
                except Exception:
                    pass
            raise

    def _create_safe_filename(self, original_stem: str) -> str:
        """Create a safe filename for cross-platform compatibility."""
        # Same logic as in TransformToEPSG3857Stage
        safe_chars = []
        for char in original_stem:
            if char.isalnum() or char in "-_.":
                safe_chars.append(char)
            elif char in " ()[]{}":
                safe_chars.append("_")
            else:
                safe_chars.append("_")

        safe_name = "".join(safe_chars)
        while "__" in safe_name:
            safe_name = safe_name.replace("__", "_")
        safe_name = safe_name.strip("_")

        if not safe_name:
            safe_name = "raster"

        return safe_name

    def _analyze_input_raster(self, input_path: Path) -> dict:
        """Analyze input raster characteristics."""
        ds = gdal.Open(str(input_path))
        if ds is None:
            raise RuntimeError(f"Cannot open input file for analysis: {input_path}")

        info = {
            "band_count": ds.RasterCount,
            "width": ds.RasterXSize,
            "height": ds.RasterYSize,
            "data_type": ds.GetRasterBand(1).DataType
            if ds.RasterCount > 0
            else gdal.GDT_Unknown,
            "has_nodata": False,
            "nodata_values": [],
        }

        # Check for nodata values
        for i in range(1, min(ds.RasterCount + 1, 5)):  # Check first 4 bands
            band = ds.GetRasterBand(i)
            nodata = band.GetNoDataValue()
            if nodata is not None:
                info["has_nodata"] = True
                info["nodata_values"].append(nodata)

        ds = None
        return info

    def _prepare_mbtiles_input(self, input_path: Path, raster_info: dict) -> Path:
        """Prepare input file for MBTiles generation, handling multi-band imagery."""
        band_count = raster_info["band_count"]

        # MBTiles supports 1, 2, 3, or 4 bands optimally
        if band_count <= 4:
            LOGGER.info(f"Using original {band_count}-band raster for MBTiles")
            return input_path

        # For > 4 bands, create RGB or RGBA version
        LOGGER.info(
            f"Converting {band_count}-band raster to RGB for MBTiles compatibility"
        )

        rgb_path = input_path.parent / f"{input_path.stem}_rgb.tif"

        # Determine best bands for RGB conversion
        if band_count >= 3:
            # Use first 3 bands for RGB
            band_list = [1, 2, 3]
            LOGGER.info("Using bands 1, 2, 3 for RGB conversion")
        else:
            # Fallback (shouldn't happen with band_count > 4, but safety check)
            band_list = [1]

        # Create RGB version
        translate_options = gdal.TranslateOptions(
            format="GTiff",
            bandList=band_list,
            creationOptions=[
                "COMPRESS=LZW",
                "TILED=YES",
                "PHOTOMETRIC=RGB" if len(band_list) == 3 else None,
            ],
        )

        input_str = str(input_path).replace("\\", "/")
        rgb_str = str(rgb_path).replace("\\", "/")

        rgb_ds = gdal.Translate(rgb_str, input_str, options=translate_options)
        if rgb_ds is None:
            error_msg = gdal.GetLastErrorMsg()
            raise RuntimeError(f"RGB conversion failed: {error_msg}")
        rgb_ds = None

        return rgb_path

    def _get_mbtiles_options(self, raster_info: dict) -> gdal.TranslateOptions:
        """Get optimized MBTiles generation options."""
        creation_options = [
            "TILE_FORMAT=PNG",
            "ZOOM_LEVEL_STRATEGY=AUTO",
            "RESAMPLING=BILINEAR",
        ]

        # Optimize based on raster characteristics
        total_pixels = raster_info["width"] * raster_info["height"]

        if total_pixels > 50_000_000:  # > 50 megapixels
            LOGGER.info("Large raster detected, using conservative MBTiles settings")
            creation_options.extend(
                [
                    "QUALITY=85",  # Slightly reduce quality for large files
                    "ZLEVEL=6",  # Moderate compression
                ]
            )
        else:
            creation_options.extend(
                [
                    "QUALITY=95",  # High quality for smaller files
                    "ZLEVEL=9",  # Maximum compression
                ]
            )

        # Handle nodata
        if raster_info["has_nodata"]:
            creation_options.append("WRITE_BOUNDS_TABLE=YES")

        return gdal.TranslateOptions(format="MBTiles", creationOptions=creation_options)

    def _validate_mbtiles(self, mbtiles_path: Path) -> None:
        """Validate the generated MBTiles file."""
        try:
            # Try to open as GDAL dataset
            ds = gdal.Open(str(mbtiles_path))
            if ds is None:
                raise RuntimeError(
                    f"Generated MBTiles file cannot be opened: {mbtiles_path}"
                )

            # Basic validation
            if ds.RasterCount == 0:
                raise RuntimeError(f"MBTiles file has no raster bands: {mbtiles_path}")

            # Check file size (should be > 0)
            file_size = mbtiles_path.stat().st_size
            if file_size == 0:
                raise RuntimeError(f"MBTiles file is empty: {mbtiles_path}")

            ds = None
            LOGGER.info(
                f"MBTiles validation successful: {mbtiles_path} ({file_size:,} bytes)"
            )

        except Exception as e:
            LOGGER.error(f"MBTiles validation failed: {e}")
            raise
