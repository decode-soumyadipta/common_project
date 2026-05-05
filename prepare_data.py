from osgeo import gdal
import os
import sys
from pathlib import Path

def prepare_raster_for_offline(input_path, output_path=None):
    """
    Convert a raster image (JP2, J2K, or TIFF) to a Cloud Optimized GeoTIFF (COG).
    COGs are the gold standard for offline GIS apps because they are universally 
    supported by GDAL and include internal tiling/overviews for fast rendering.

    Args:
        input_path  : Path to the input file
        output_path : Path to the output .tif file (defaults to input_name.cog.tif)
    """
    # Register all GDAL drivers
    gdal.AllRegister()
    gdal.UseExceptions()

    if not output_path:
        p = Path(input_path)
        output_path = str(p.parent / f"{p.stem}.cog.tif")

    print(f"\n{'='*60}")
    print(f"PREPARING ASSET FOR OFFLINE SYSTEM")
    print(f"{'='*60}")
    print(f"Input  : {input_path}")
    print(f"Output : {output_path}")

    try:
        src_ds = gdal.Open(input_path, gdal.GA_ReadOnly)
    except Exception as e:
        print(f"ERROR: Could not open input file. {e}")
        print("Tip: If this is a .j2k file, ensure your current environment has the JP2OpenJPEG driver.")
        return

    # Check for JP2/J2K specifically to warn about driver issues
    driver_name = src_ds.GetDriver().ShortName
    print(f"Current Driver: {driver_name}")

    # Define COG creation options
    # We use DEFLATE compression for excellent space saving without losing quality (lossless)
    # TILING and OVERVIEWS are built-in.
    creation_options = [
        "DRIVER=COG",
        "COMPRESS=DEFLATE",
        "PREDICTOR=2",      # Good for imagery and DEMs
        "LEVEL=9",          # Max compression
        "SPARSE_OK=YES",
        "BIGTIFF=YES",      # Handle files > 4GB
    ]

    print(f"Converting to Cloud Optimized GeoTIFF (COG)...")
    
    try:
        # Create the COG
        # The 'COG' driver in GDAL 3.1+ handles overviews and tiling in one pass
        driver = gdal.GetDriverByName("COG")
        if not driver:
            # Fallback for older GDAL: use GTiff with specific options
            print("Warning: COG driver not found. Falling back to GTiff with COG-like settings.")
            driver = gdal.GetDriverByName("GTiff")
            creation_options = [
                "TILED=YES",
                "COMPRESS=DEFLATE",
                "PREDICTOR=2",
                "COPY_SRC_OVERVIEWS=YES"
            ]
            # We would need to build overviews first for GTiff
            print("Building overviews...")
            src_ds.BuildOverviews("NEAREST", [2, 4, 8, 16, 32, 64])

        out_ds = driver.CreateCopy(
            output_path,
            src_ds,
            strict=0,
            options=creation_options,
            callback=gdal.TermProgress_nocb
        )

        if out_ds:
            out_ds.FlushCache()
            out_ds = None
            print(f"\n✓ SUCCESS: Created {os.path.basename(output_path)}")
            print(f"  Size: {os.path.getsize(output_path) / (1024*1024):.2f} MB")
            print(f"  Tip: This .tif file will work on ANY system with basic GDAL/rasterio.")
        else:
            print(f"\n✗ FAILED: Creation returned None.")

    except Exception as e:
        print(f"\n✗ ERROR during conversion: {e}")
    finally:
        src_ds = None

if __name__ == "__main__":
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    else:
        # Default test file from user workspace
        input_file = r"C:\Users\Jitaditya Ray\common_project\data_test\T44SND_20250706T052241_AOT_10m.jp2"
    
    if os.path.exists(input_file):
        prepare_raster_for_offline(input_file)
    else:
        print(f"File not found: {input_file}")
        print("Usage: python prepare_data.py <path_to_image>")
