#!/usr/bin/env python3
"""
Verification script for Task 3: Basemap Toggle and Performance Optimizations

This script verifies that all required changes have been made to the codebase.
"""

import re
from pathlib import Path


def check_file_contains(file_path: Path, pattern: str, description: str) -> bool:
    """Check if a file contains a specific pattern."""
    if not file_path.exists():
        print(f"❌ {description}: File not found: {file_path}")
        return False
    
    content = file_path.read_text(encoding='utf-8')
    if re.search(pattern, content, re.MULTILINE | re.DOTALL):
        print(f"✅ {description}")
        return True
    else:
        print(f"❌ {description}: Pattern not found")
        return False


def main():
    """Run all verification checks."""
    print("=" * 80)
    print("Task 3 Verification: Basemap Toggle and Performance Optimizations")
    print("=" * 80)
    print()
    
    bridge_js = Path("src/desktop_client/client_frontend/web_assets/bridge.js")
    main_window_py = Path("src/desktop_client/client_backend/desktop/main_window.py")
    
    checks = [
        # Check 1: setBasemapVisibility function exists
        (
            bridge_js,
            r"setBasemapVisibility:\s*function\s*\(\s*visible\s*\)",
            "setBasemapVisibility function added to bridge.js"
        ),
        
        # Check 2: setBasemapVisibility has lazy loading logic
        (
            bridge_js,
            r"if\s*\(\s*!osmBasemapLayer\s*\)",
            "setBasemapVisibility has lazy loading logic for OSM tiles"
        ),
        
        # Check 3: Mouse coordinate throttle optimized
        (
            bridge_js,
            r"const\s+_SB_COORD_THROTTLE_MS\s*=\s*100",
            "Mouse coordinate throttle set to 100ms (10 fps)"
        ),
        
        # Check 4: Camera change throttle constant added
        (
            bridge_js,
            r"const\s+_SB_CAMERA_THROTTLE_MS\s*=\s*100",
            "Camera change throttle constant added (100ms)"
        ),
        
        # Check 5: Camera change throttle variable added
        (
            bridge_js,
            r"let\s+_sbLastCameraEmitMs\s*=\s*0",
            "Camera change throttle tracking variable added"
        ),
        
        # Check 6: emitCameraChanged has throttling logic
        (
            bridge_js,
            r"if\s*\(\s*now\s*-\s*_sbLastCameraEmitMs\s*<\s*_SB_CAMERA_THROTTLE_MS\s*\)\s*return",
            "emitCameraChanged function has throttling logic"
        ),
        
        # Check 7: Basemap visibility dropdown exists in Python
        (
            main_window_py,
            r"self\.basemap_visibility_combo\s*=\s*QComboBox\(\)",
            "Basemap visibility dropdown exists in main_window.py"
        ),
        
        # Check 8: Basemap visibility handler exists in Python
        (
            main_window_py,
            r"def\s+_on_basemap_visibility_changed\s*\(",
            "Basemap visibility handler exists in main_window.py"
        ),
        
        # Check 9: Handler calls setBasemapVisibility
        (
            main_window_py,
            r"window\.offlineGIS\.setBasemapVisibility",
            "Handler calls window.offlineGIS.setBasemapVisibility"
        ),
    ]
    
    results = []
    for file_path, pattern, description in checks:
        result = check_file_contains(file_path, pattern, description)
        results.append(result)
    
    print()
    print("=" * 80)
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"✅ ALL CHECKS PASSED ({passed}/{total})")
        print()
        print("Task 3 implementation is complete and ready for testing!")
    else:
        print(f"⚠️  SOME CHECKS FAILED ({passed}/{total})")
        print()
        print("Please review the failed checks above and ensure all changes are in place.")
    
    print("=" * 80)
    
    return passed == total


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
