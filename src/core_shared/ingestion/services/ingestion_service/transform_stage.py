from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from osgeo import gdal

from core_shared.ingestion.services.ingestion_service.context import IngestionContext
from core_shared.ingestion.services.ingestion_service.contracts import IngestionStage

gdal.UseExceptions()

LOGGER = logging.getLogger("services.transform")


@dataclass(frozen=True)
class TransformToEPSG3857Stage(IngestionStage):
    """Reproject raster to EPSG:3857 (Web Mercator) for web tile serving."""
    
    name: str = "transform_to_epsg3857"
    message: str = "Reprojecting to EPSG:3857"

    def run(self, context: IngestionContext) -> None:
        if context.working_path is None:
            raise ValueError("working_path is required before transformation")
        
        if context.metadata is None:
            raise ValueError("metadata is required before transformation")
        
        current_crs = context.metadata.crs
        LOGGER.info(f"Transform stage: processing {context.working_path} with CRS {current_crs}")
        
        if current_crs == "EPSG:3857":
            context.report("Already in EPSG:3857, skipping reprojection")
            LOGGER.info(f"Skipping reprojection for {context.working_path} - already in EPSG:3857")
            return
        
        # Create output path with safe filename (handle spaces and special characters)
        safe_stem = context.working_path.stem.replace(" ", "_")
        output_path = context.working_path.parent / f"{safe_stem}_3857.tif"
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            warp_options = gdal.WarpOptions(
                dstSRS="EPSG:3857",
                format='GTiff',
                creationOptions=['COMPRESS=LZW', 'TILED=YES', 'BIGTIFF=IF_SAFER'],
                multithread=True,
                warpOptions=['NUM_THREADS=ALL_CPUS'],
                errorThreshold=0.125  # Allow some error tolerance
            )
            
            context.report(f"Reprojecting from {current_crs} to EPSG:3857")
            LOGGER.info(f"Starting reprojection: {context.working_path} -> {output_path}")
            
            # Use string paths to avoid issues with Path objects and GDAL
            ds = gdal.Warp(str(output_path), str(context.working_path), options=warp_options)
            if ds is None:
                # Get the last GDAL error
                error_msg = gdal.GetLastErrorMsg()
                LOGGER.error(f"GDAL Warp failed for {context.working_path}: {error_msg}")
                raise RuntimeError(f"Reprojection failed for {context.working_path}: {error_msg}")
            
            # Verify the output file was created and is valid
            if not output_path.exists():
                raise RuntimeError(f"Output file was not created: {output_path}")
            
            # Test that we can open the output file
            test_ds = gdal.Open(str(output_path))
            if test_ds is None:
                raise RuntimeError(f"Created output file is not readable: {output_path}")
            test_ds = None
            
            ds = None  # Close the dataset
            context.working_path = output_path
            context.report("Reprojection complete")
            LOGGER.info(f"Reprojection successful: {output_path}")
            
        except Exception as e:
            LOGGER.error(f"Transform stage failed for {context.working_path}: {e}")
            # Clean up partial output file if it exists
            if output_path.exists():
                try:
                    output_path.unlink()
                except Exception:
                    pass
            raise


@dataclass(frozen=True)
class GenerateMBTilesStage(IngestionStage):
    """Generate MBTiles archive for offline tile serving."""
    
    name: str = "generate_mbtiles"
    message: str = "Generating MBTiles"

    def run(self, context: IngestionContext) -> None:
        if context.working_path is None:
            raise ValueError("working_path is required before MBTiles generation")
        
        # Create output path with safe filename
        safe_stem = context.working_path.stem.replace(" ", "_")
        output_path = context.working_path.parent / f"{safe_stem}.mbtiles"
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # Check the number of bands in the input raster
            ds_info = gdal.Open(str(context.working_path))
            if ds_info is None:
                raise RuntimeError(f"Cannot open input file for band check: {context.working_path}")
            
            band_count = ds_info.RasterCount
            ds_info = None
            
            LOGGER.info(f"Input raster has {band_count} bands")
            
            # MBTiles only supports 1, 2, 3, or 4 bands
            if band_count > 4:
                LOGGER.info(f"Converting {band_count}-band raster to 3-band RGB for MBTiles compatibility")
                context.report(f"Converting {band_count}-band raster to RGB for MBTiles")
                
                # Create intermediate RGB file
                rgb_path = context.working_path.parent / f"{safe_stem}_rgb.tif"
                
                # Use gdal_translate to select first 3 bands
                translate_rgb_options = gdal.TranslateOptions(
                    format='GTiff',
                    bandList=[1, 2, 3],  # Select first 3 bands
                    creationOptions=['COMPRESS=LZW', 'TILED=YES']
                )
                
                rgb_ds = gdal.Translate(str(rgb_path), str(context.working_path), options=translate_rgb_options)
                if rgb_ds is None:
                    error_msg = gdal.GetLastErrorMsg()
                    raise RuntimeError(f"RGB conversion failed: {error_msg}")
                rgb_ds = None
                
                # Use the RGB file as input for MBTiles
                mbtiles_input = rgb_path
            else:
                # Use original file if it has 4 or fewer bands
                mbtiles_input = context.working_path
            
            translate_options = gdal.TranslateOptions(
                format='MBTiles',
                creationOptions=[
                    'TILE_FORMAT=PNG',
                    'ZOOM_LEVEL_STRATEGY=AUTO',
                    'RESAMPLING=BILINEAR'
                ]
            )
            
            context.report("Generating MBTiles archive")
            LOGGER.info(f"Starting MBTiles generation: {mbtiles_input} -> {output_path}")
            
            ds = gdal.Translate(str(output_path), str(mbtiles_input), options=translate_options)
            if ds is None:
                error_msg = gdal.GetLastErrorMsg()
                LOGGER.error(f"GDAL Translate failed for {mbtiles_input}: {error_msg}")
                raise RuntimeError(f"MBTiles generation failed for {mbtiles_input}: {error_msg}")
            
            # Verify the output file was created
            if not output_path.exists():
                raise RuntimeError(f"MBTiles file was not created: {output_path}")
            
            ds = None  # Close the dataset
            
            # Clean up intermediate RGB file if created
            if band_count > 4 and rgb_path.exists():
                try:
                    rgb_path.unlink()
                    LOGGER.info(f"Cleaned up intermediate RGB file: {rgb_path}")
                except Exception as e:
                    LOGGER.warning(f"Failed to clean up RGB file {rgb_path}: {e}")
            
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
            # Clean up intermediate RGB file if it exists
            if 'rgb_path' in locals() and rgb_path.exists():
                try:
                    rgb_path.unlink()
                except Exception:
                    pass
            raise
