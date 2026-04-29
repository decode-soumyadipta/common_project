#!/usr/bin/env python3
"""
Debug script to test single file ingestion and identify GDAL issues.
"""

import sys
import logging
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_single_file_ingestion():
    """Test ingestion of a single file to debug issues."""
    
    # Initialize database
    try:
        from core_shared.db.session import init_db, SessionLocal
        init_db()
        print("✅ Database initialized successfully")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False
    
    # Test with a simple file
    test_files = [
        "data_test/images/coal 12_2024_0.tif",
        "data_test/images/coal 12_2024_0.cog.tif",
        "data_test/images/coal 12_2024_0_3857.tif",
    ]
    
    for test_file in test_files:
        test_path = Path(test_file)
        if not test_path.exists():
            print(f"⚠️ Test file not found: {test_file}")
            continue
            
        print(f"\n🧪 Testing ingestion of: {test_file}")
        
        try:
            from core_shared.ingestion.services.ingest_service import register_raster
            
            with SessionLocal() as session:
                def progress_callback(message: str):
                    print(f"   📊 {message}")
                
                result = register_raster(
                    path=test_path,
                    session=session,
                    progress_callback=progress_callback
                )
                
                print(f"✅ Ingestion successful!")
                print(f"   Asset ID: {result['id']}")
                print(f"   File: {result['file_name']}")
                print(f"   Kind: {result['kind']}")
                print(f"   CRS: {result['crs']}")
                
                return True
                
        except Exception as e:
            print(f"❌ Ingestion failed: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    return False

def test_gdal_operations():
    """Test basic GDAL operations."""
    print("\n🔧 Testing GDAL operations...")
    
    try:
        from osgeo import gdal
        gdal.UseExceptions()
        
        # Test opening a file
        test_files = [
            "data_test/images/coal 12_2024_0.tif",
            "data_test/images/coal 12_2024_0.cog.tif",
        ]
        
        for test_file in test_files:
            test_path = Path(test_file)
            if not test_path.exists():
                continue
                
            print(f"   Testing: {test_file}")
            
            # Test opening
            ds = gdal.Open(str(test_path))
            if ds is None:
                print(f"   ❌ Cannot open file: {test_file}")
                continue
            
            # Get basic info
            print(f"   ✅ Size: {ds.RasterXSize}x{ds.RasterYSize}")
            print(f"   ✅ Bands: {ds.RasterCount}")
            
            # Get projection
            proj = ds.GetProjection()
            if proj:
                print(f"   ✅ Has projection")
            else:
                print(f"   ⚠️ No projection")
            
            # Test reprojection
            try:
                output_path = test_path.parent / f"debug_test_{test_path.stem}_3857.tif"
                
                warp_options = gdal.WarpOptions(
                    dstSRS="EPSG:3857",
                    format='GTiff',
                    creationOptions=['COMPRESS=LZW', 'TILED=YES'],
                )
                
                result_ds = gdal.Warp(str(output_path), str(test_path), options=warp_options)
                if result_ds is None:
                    error_msg = gdal.GetLastErrorMsg()
                    print(f"   ❌ Reprojection failed: {error_msg}")
                else:
                    print(f"   ✅ Reprojection successful: {output_path}")
                    result_ds = None
                    
                    # Clean up test file
                    if output_path.exists():
                        output_path.unlink()
                        
            except Exception as e:
                print(f"   ❌ Reprojection error: {e}")
            
            ds = None
            break
            
    except Exception as e:
        print(f"❌ GDAL test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🐛 Debug Single File Ingestion")
    print("=" * 50)
    
    # Test GDAL first
    test_gdal_operations()
    
    # Test ingestion
    success = test_single_file_ingestion()
    
    if success:
        print("\n🎉 Debug test completed successfully!")
    else:
        print("\n❌ Debug test failed - check logs above")