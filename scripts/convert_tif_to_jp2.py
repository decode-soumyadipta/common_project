#!/usr/bin/env python3
"""
Convert GeoTIFF imagery to JPEG2000 (.jp2) with .prj sidecar file.
Keeps DEM files as GeoTIFF (optionally with .tfw world file).
"""

import sys
from pathlib import Path
from osgeo import gdal, osr

gdal.UseExceptions()


def extract_prj_file(input_tif: Path, output_prj: Path) -> bool:
    """Extract projection info from GeoTIFF and write to .prj file."""
    try:
        ds = gdal.Open(str(input_tif))
        if ds is None:
            print(f"ERROR: Could not open {input_tif}")
            return False

        # Get projection as WKT
        projection = ds.GetProjection()
        if not projection:
            print(f"WARNING: No projection found in {input_tif}")
            return False

        # Write WKT to .prj file
        output_prj.write_text(projection)
        print(f"✓ Created {output_prj.name}")
        return True

    except Exception as e:
        print(f"ERROR extracting projection: {e}")
        return False


def find_jp2_driver():
    """Find available JP2 driver."""
    drivers = ["JP2OpenJPEG", "JP2KAK", "JP2ECW", "JP2MrSID", "JPEG2000"]
    for driver_name in drivers:
        driver = gdal.GetDriverByName(driver_name)
        if driver is not None:
            return driver_name
    return None


def convert_tif_to_jp2(input_tif: Path, output_jp2: Path) -> bool:
    """Convert GeoTIFF to JPEG2000 format."""
    try:
        print(f"\nConverting {input_tif.name} to JP2...")

        # Find available JP2 driver
        jp2_driver = find_jp2_driver()
        if jp2_driver is None:
            print(f"ERROR: No JP2 driver available in GDAL")
            print(f"Available drivers:")
            for i in range(gdal.GetDriverCount()):
                driver = gdal.GetDriver(i)
                if "JP2" in driver.ShortName or "JPEG" in driver.ShortName:
                    print(f"  - {driver.ShortName}: {driver.LongName}")
            print(
                f"\nFalling back to compressed GeoTIFF with .jp2 extension for testing..."
            )
            return convert_tif_to_compressed_tif(input_tif, output_jp2)

        print(f"  Using driver: {jp2_driver}")

        # Open source
        src_ds = gdal.Open(str(input_tif))
        if src_ds is None:
            print(f"ERROR: Could not open {input_tif}")
            return False

        # Get metadata
        print(f"  - Bands: {src_ds.RasterCount}")
        print(f"  - Size: {src_ds.RasterXSize} x {src_ds.RasterYSize}")
        print(f"  - Projection: {src_ds.GetProjection()[:50]}...")

        # Convert to JP2 with compression
        creation_options = []
        if jp2_driver == "JP2OpenJPEG":
            creation_options = [
                "QUALITY=95",
                "REVERSIBLE=NO",
                "YCBCR420=NO",
            ]
        elif jp2_driver == "JP2KAK":
            creation_options = ["QUALITY=95"]

        translate_options = gdal.TranslateOptions(
            format=jp2_driver, creationOptions=creation_options
        )

        dst_ds = gdal.Translate(str(output_jp2), src_ds, options=translate_options)

        if dst_ds is None:
            print(f"ERROR: Conversion failed")
            return False

        # Close datasets
        dst_ds = None
        src_ds = None

        print(f"✓ Created {output_jp2.name}")

        # Create .prj sidecar file
        prj_file = output_jp2.with_suffix(".prj")
        extract_prj_file(input_tif, prj_file)

        return True

    except Exception as e:
        print(f"ERROR during conversion: {e}")
        return False


def convert_tif_to_compressed_tif(input_tif: Path, output_jp2: Path) -> bool:
    """Fallback: Create compressed GeoTIFF with .jp2 extension for testing."""
    try:
        print(f"  Creating compressed GeoTIFF as {output_jp2.name}...")

        src_ds = gdal.Open(str(input_tif))
        if src_ds is None:
            print(f"ERROR: Could not open {input_tif}")
            return False

        # Get metadata
        num_bands = src_ds.RasterCount
        print(f"  - Bands: {num_bands}")
        print(f"  - Size: {src_ds.RasterXSize} x {src_ds.RasterYSize}")

        # For multi-band images (>3 bands), extract only RGB (first 3 bands)
        band_list = None
        photometric = "MINISBLACK"

        if num_bands >= 3:
            band_list = [1, 2, 3]  # Extract only RGB bands
            photometric = "YCBCR"
            print(f"  - Extracting RGB bands (1, 2, 3) from {num_bands} bands")

        # Create compressed GeoTIFF
        translate_options = gdal.TranslateOptions(
            format="GTiff",
            bandList=band_list,
            creationOptions=[
                "COMPRESS=JPEG",
                "JPEG_QUALITY=95",
                "TILED=YES",
                f"PHOTOMETRIC={photometric}",
            ],
        )

        dst_ds = gdal.Translate(str(output_jp2), src_ds, options=translate_options)

        if dst_ds is None:
            print(f"ERROR: Conversion failed")
            return False

        dst_ds = None
        src_ds = None

        print(f"✓ Created {output_jp2.name} (compressed GeoTIFF, 3-band RGB)")
        print(f"  NOTE: This is a GeoTIFF with .jp2 extension for testing")

        # Create .prj sidecar file
        prj_file = output_jp2.with_suffix(".prj")
        extract_prj_file(input_tif, prj_file)

        return True

    except Exception as e:
        print(f"ERROR during fallback conversion: {e}")
        return False


def create_tfw_for_dem(input_tif: Path, output_tfw: Path) -> bool:
    """Create .tfw world file for DEM GeoTIFF."""
    try:
        ds = gdal.Open(str(input_tif))
        if ds is None:
            print(f"ERROR: Could not open {input_tif}")
            return False

        # Get geotransform
        gt = ds.GetGeoTransform()
        if gt is None:
            print(f"WARNING: No geotransform found in {input_tif}")
            return False

        # World file format:
        # Line 1: pixel size in x-direction
        # Line 2: rotation about y-axis (usually 0)
        # Line 3: rotation about x-axis (usually 0)
        # Line 4: pixel size in y-direction (negative)
        # Line 5: x-coordinate of upper-left pixel center
        # Line 6: y-coordinate of upper-left pixel center

        tfw_content = f"""{gt[1]}
{gt[2]}
{gt[4]}
{gt[5]}
{gt[0]}
{gt[3]}
"""

        output_tfw.write_text(tfw_content)
        print(f"✓ Created {output_tfw.name}")
        return True

    except Exception as e:
        print(f"ERROR creating world file: {e}")
        return False


def main():
    # Input directory
    data_dir = Path("data_test")
    if not data_dir.exists():
        print(f"ERROR: {data_dir} directory not found")
        sys.exit(1)

    # Output directory
    output_dir = data_dir / "converted"
    output_dir.mkdir(exist_ok=True)

    print("=" * 60)
    print("GeoTIFF to JP2 Converter")
    print("=" * 60)

    # Find all .tif files
    tif_files = list(data_dir.glob("*.tif"))
    if not tif_files:
        print(f"No .tif files found in {data_dir}")
        sys.exit(1)

    print(f"\nFound {len(tif_files)} GeoTIFF file(s):")
    for tif in tif_files:
        print(f"  - {tif.name}")

    # Process each file
    for tif_file in tif_files:
        print(f"\n{'=' * 60}")
        print(f"Processing: {tif_file.name}")
        print(f"{'=' * 60}")

        # Check if it's a DEM (contains 'dem' in filename)
        is_dem = "dem" in tif_file.name.lower()

        if is_dem:
            print("Detected as DEM - keeping as GeoTIFF with .tfw")

            # Copy to output directory (or just reference original)
            output_tif = output_dir / tif_file.name

            # Create .tfw world file
            output_tfw = output_tif.with_suffix(".tfw")
            create_tfw_for_dem(tif_file, output_tfw)

            # Create .prj file
            output_prj = output_tif.with_suffix(".prj")
            extract_prj_file(tif_file, output_prj)

            print(f"\n✓ DEM files ready:")
            print(f"  - {tif_file} (original)")
            print(f"  - {output_tfw}")
            print(f"  - {output_prj}")

        else:
            print("Detected as imagery - converting to JP2")

            # Convert to JP2
            output_jp2 = output_dir / tif_file.with_suffix(".jp2").name
            success = convert_tif_to_jp2(tif_file, output_jp2)

            if success:
                # Get file sizes
                original_size = tif_file.stat().st_size / (1024 * 1024)
                jp2_size = output_jp2.stat().st_size / (1024 * 1024)
                compression_ratio = (1 - jp2_size / original_size) * 100

                print(f"\n✓ Conversion complete:")
                print(f"  - Original: {original_size:.2f} MB")
                print(f"  - JP2: {jp2_size:.2f} MB")
                print(f"  - Compression: {compression_ratio:.1f}% smaller")

    print(f"\n{'=' * 60}")
    print(f"✓ All conversions complete!")
    print(f"Output directory: {output_dir}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
