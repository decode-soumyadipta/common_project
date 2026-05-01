#!/usr/bin/env python3
"""
Verification script for Task 9 fixes:
1. Cesium API fix (bridge.js)
2. World file format support (controller.py, control_panel.py)
"""

import re
from pathlib import Path


def verify_cesium_fix():
    """Verify that Cesium API call has been fixed."""
    print("=" * 80)
    print("VERIFYING CESIUM API FIX")
    print("=" * 80)
    
    bridge_file = Path("src/desktop_client/client_frontend/web_assets/bridge.js")
    
    if not bridge_file.exists():
        print("❌ bridge.js not found")
        return False
    
    content = bridge_file.read_text(encoding='utf-8')
    
    # Check for incorrect API usage
    if "TileMapServiceImageryProvider.fromUrl" in content:
        print("❌ FAIL: Still using incorrect .fromUrl() syntax")
        return False
    
    # Check for correct constructor usage
    if "new Cesium.TileMapServiceImageryProvider({" in content:
        print("✅ PASS: Using correct constructor syntax")
    else:
        print("❌ FAIL: Constructor syntax not found")
        return False
    
    # Check that promise handling was removed
    if "defaultEarthProvider.then(function(provider)" in content:
        print("❌ FAIL: Still using promise handling (should be synchronous)")
        return False
    else:
        print("✅ PASS: Promise handling removed (synchronous)")
    
    print("\n✅ Cesium API fix verified successfully!\n")
    return True


def verify_world_file_support():
    """Verify that world file formats are supported."""
    print("=" * 80)
    print("VERIFYING WORLD FILE FORMAT SUPPORT")
    print("=" * 80)
    
    controller_file = Path("src/desktop_client/client_backend/desktop/controller.py")
    control_panel_file = Path("src/desktop_client/client_backend/desktop/control_panel.py")
    
    if not controller_file.exists():
        print("❌ controller.py not found")
        return False
    
    if not control_panel_file.exists():
        print("❌ control_panel.py not found")
        return False
    
    controller_content = controller_file.read_text(encoding='utf-8')
    control_panel_content = control_panel_file.read_text(encoding='utf-8')
    
    # Check controller.py file filters
    print("\n--- Checking controller.py file filters ---")
    
    # GeoTIFF filter
    if "*.tfw" in controller_content and "*.tifw" in controller_content:
        print("✅ PASS: GeoTIFF filter includes world files (.tfw, .tifw)")
    else:
        print("❌ FAIL: GeoTIFF filter missing world file extensions")
        return False
    
    # JPEG2000 filter
    if "*.j2w" in controller_content and "*.jgw" in controller_content:
        print("✅ PASS: JPEG2000 filter includes world files (.j2w, .jgw)")
    else:
        print("❌ FAIL: JPEG2000 filter missing world file extensions")
        return False
    
    # Check control_panel.py validation logic
    print("\n--- Checking control_panel.py validation logic ---")
    
    # GeoTIFF validation
    if "world_files = set()" in control_panel_content:
        print("✅ PASS: GeoTIFF validation tracks world files")
    else:
        print("❌ FAIL: GeoTIFF validation doesn't track world files")
        return False
    
    if ".tfw" in control_panel_content and ".tifw" in control_panel_content:
        print("✅ PASS: GeoTIFF validation checks for .tfw/.tifw")
    else:
        print("❌ FAIL: GeoTIFF validation missing world file checks")
        return False
    
    # JPEG2000 validation
    if "_validate_jp2_files" in control_panel_content:
        # Check for world file tracking in JP2 validation
        jp2_validation_match = re.search(
            r'def _validate_jp2_files.*?(?=def |\Z)',
            control_panel_content,
            re.DOTALL
        )
        
        if jp2_validation_match:
            jp2_validation = jp2_validation_match.group(0)
            
            if "world_files" in jp2_validation:
                print("✅ PASS: JPEG2000 validation tracks world files")
            else:
                print("❌ FAIL: JPEG2000 validation doesn't track world files")
                return False
            
            if ".j2w" in jp2_validation and ".jgw" in jp2_validation:
                print("✅ PASS: JPEG2000 validation checks for .j2w/.jgw")
            else:
                print("❌ FAIL: JPEG2000 validation missing world file checks")
                return False
        else:
            print("❌ FAIL: Could not find _validate_jp2_files method")
            return False
    
    print("\n✅ World file format support verified successfully!\n")
    return True


def verify_file_grouping_service():
    """Verify that file grouping service recognizes world files."""
    print("=" * 80)
    print("VERIFYING FILE GROUPING SERVICE")
    print("=" * 80)
    
    grouping_file = Path("src/core_shared/ingestion/services/file_grouping_service.py")
    
    if not grouping_file.exists():
        print("❌ file_grouping_service.py not found")
        return False
    
    content = grouping_file.read_text(encoding='utf-8')
    
    # Check for world file extensions in AUXILIARY_EXTENSIONS
    world_file_extensions = ['.tfw', '.jgw', '.pgw', '.bpw', '.gfw']
    
    for ext in world_file_extensions:
        if f"'{ext}': 'world_file'" in content:
            print(f"✅ PASS: {ext} recognized as world_file")
        else:
            print(f"❌ FAIL: {ext} not recognized")
            return False
    
    print("\n✅ File grouping service verified successfully!\n")
    return True


def main():
    """Run all verification checks."""
    print("\n" + "=" * 80)
    print("TASK 9 VERIFICATION SCRIPT")
    print("Checking Cesium API fix and world file format support")
    print("=" * 80 + "\n")
    
    results = []
    
    # Run all checks
    results.append(("Cesium API Fix", verify_cesium_fix()))
    results.append(("World File Support", verify_world_file_support()))
    results.append(("File Grouping Service", verify_file_grouping_service()))
    
    # Summary
    print("\n" + "=" * 80)
    print("VERIFICATION SUMMARY")
    print("=" * 80)
    
    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
        if not passed:
            all_passed = False
    
    print("=" * 80)
    
    if all_passed:
        print("\n🎉 ALL CHECKS PASSED! Task 9 fixes are complete and verified.\n")
        return 0
    else:
        print("\n❌ SOME CHECKS FAILED. Please review the output above.\n")
        return 1


if __name__ == "__main__":
    exit(main())
