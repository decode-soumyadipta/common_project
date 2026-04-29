#!/usr/bin/env python3
"""
Prepare test data for ingestion pipeline testing.
Converts imagery to JP2 (if supported) or creates mock JP2 structure.
"""

import sys
import shutil
from pathlib import Path
from osgeo import gdal, osr

gdal.UseExceptions()


def check_jp2_support():
    """Check if GDAL has JP2 driver support."""
    drivers = ['JP2OpenJPEG', 'JP2KAK', 'JP2ECW', 'JP2MrSID']
    for driver_name in drivers:
        driver = gdal.GetDriverByName(driver_name)
        if driver is not None:
            print(f"✓ Found JP2 driver: {driver_name}")
            return driver_name
    return None


def extract_projection_wkt(tif_path: Path) -> str:
    """Extract projection WKT from GeoTIFF."""
    ds = gdal.Open(str(tif_path))
    if ds is None:
        raise ValueError(f"Could not open {tif_path}")
    
    projection = ds.GetProjection()
    ds = None
    
    if not projection:
        # Default to WGS84 if no projection found
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        projection = srs.ExportToWkt()
    
    return projection


def create_prj_file(tif_path: Path, prj_path: Path):
    """Create .prj sidecar file from GeoTIFF projection."""
    wkt = extract_projection_wkt(tif_path)
    prj_path.write_text(wkt)
    print(f"  ✓ Created {prj_path.name}")


def create_tfw_file(tif_path: Path, tfw_path: Path):
    """Create .tfw world file from GeoTIFF geotransform."""
    ds = gdal.Open(str(tif_path))
    if ds is None:
        raise ValueError(f"Could not open {tif_path}")
    
    gt = ds.GetGeoTransform()
    ds = None
    
    if gt is None:
        print(f"  WARNING: No geotransform in {tif_path.name}")
        return
    
    # World file format (6 lines)
    tfw_content = f"{gt[1]}\n{gt[2]}\n{gt[4]}\n{gt[5]}\n{gt[0]}\n{gt[3]}\n"
    tfw_path.write_text(tfw_content)
    print(f"  ✓ Created {tfw_path.name}")


def convert_to_jp2(tif_path: Path, jp2_path: Path, driver_name: str):
    """Convert GeoTIFF to JP2 using available driver."""
    print(f"  Converting to JP2 using {driver_name}...")
    
    src_ds = gdal.Open(str(tif_path))
    if src_ds is None:
        raise ValueError(f"Could not open {tif_path}")
    
    # Print info
    print(f"    - Size: {src_ds.RasterXSize} x {src_ds.RasterYSize}")
    print(f"    - Bands: {src_ds.RasterCount}")
    
    # Conversion options
    options = gdal.TranslateOptions(
        format=driver_name,
        creationOptions=['QUALITY=95'] if driver_name == 'JP2OpenJPEG' else []
    )
    
    dst_ds = gdal.Translate(str(jp2_path), src_ds, options=options)
    
    if dst_ds is None:
        raise RuntimeError("JP2 conversion failed")
    
    dst_ds = None
    src_ds = None
    
    # Get file sizes
    original_mb = tif_path.stat().st_size / (1024 * 1024)
    jp2_mb = jp2_path.stat().st_size / (1024 * 1024)
    
    print(f"  ✓ Created {jp2_path.name}")
    print(f"    - Original: {original_mb:.2f} MB")
    print(f"    - JP2: {jp2_mb:.2f} MB")


def copy_as_jp2_mock(tif_path: Path, jp2_path: Path):
    """Copy GeoTIFF as .jp2 extension (mock for testing without JP2 driver)."""
    print(f"  WARNING: No JP2 driver found - copying as .jp2 for testing")
    shutil.copy2(tif_path, jp2_path)
    print(f"  ✓ Created {jp2_path.name} (actually GeoTIFF)")


def main():
    print("=" * 70)
    print("Test Data Preparation Script")
    print("=" * 70)
    
    # Check directories
    data_dir = Path("data_test")
    if not data_dir.exists():
        print(f"\nERROR: {data_dir} not found")
        sys.exit(1)
    
    output_dir = data_dir / "converted"
    output_dir.mkdir(exist_ok=True)
    
    # Check JP2 support
    print("\nChecking GDAL JP2 support...")
    jp2_driver = check_jp2_support()
    if jp2_driver is None:
        print("  WARNING: No JP2 driver found")
        print("  Will create mock .jp2 files for testing")
    
    # Find files
    tif_files = list(data_dir.glob("*.tif"))
    if not tif_files:
        print(f"\nERROR: No .tif files found in {data_dir}")
        sys.exit(1)
    
    print(f"\nFound {len(tif_files)} file(s):")
    for f in tif_files:
        print(f"  - {f.name}")
    
    # Process each file
    for tif_file in tif_files:
        print(f"\n{'─' * 70}")
        print(f"Processing: {tif_file.name}")
        print(f"{'─' * 70}")
        
        is_dem = 'dem' in tif_file.name.lower()
        
        if is_dem:
            print("Type: DEM (keeping as GeoTIFF)")
            
            # Create output files
            output_tif = output_dir / tif_file.name
            output_tfw = output_tif.with_suffix('.tfw')
            output_prj = output_tif.with_suffix('.prj')
            
            # Copy original
            if not output_tif.exists():
                shutil.copy2(tif_file, output_tif)
                print(f"  ✓ Copied {output_tif.name}")
            
            # Create sidecar files
            create_tfw_file(tif_file, output_tfw)
            create_prj_file(tif_file, output_prj)
            
        else:
            print("Type: Imagery (converting to JP2)")
            
            # Create output files
            output_jp2 = output_dir / tif_file.with_suffix('.jp2').name
            output_prj = output_jp2.with_suffix('.prj')
            
            # Convert or mock
            try:
                if jp2_driver:
                    convert_to_jp2(tif_file, output_jp2, jp2_driver)
                else:
                    copy_as_jp2_mock(tif_file, output_jp2)
                
                # Create .prj sidecar
                create_prj_file(tif_file, output_prj)
                
            except Exception as e:
                print(f"  ERROR: {e}")
                continue
    
    # Summary
    print(f"\n{'=' * 70}")
    print("✓ Preparation complete!")
    print(f"{'=' * 70}")
    print(f"\nOutput directory: {output_dir.absolute()}")
    print("\nGenerated files:")
    
    for item in sorted(output_dir.iterdir()):
        size_mb = item.stat().st_size / (1024 * 1024)
        print(f"  - {item.name:30s} ({size_mb:6.2f} MB)")
    
    print("\nYou can now test the ingestion pipeline with these files.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
