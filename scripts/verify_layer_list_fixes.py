#!/usr/bin/env python3
"""
Verification script for layer list fixes.

This script checks that all the critical fixes are in place:
1. QBrush import at module level
2. CSS without !important
3. Custom drop handler with pre-capture
4. file_path storage in table items
5. Visibility tracking optimization

Run this before testing to ensure all code changes are present.
"""

import re
from pathlib import Path


def check_file_contains(file_path: Path, pattern: str, description: str) -> bool:
    """Check if a file contains a specific pattern."""
    try:
        content = file_path.read_text(encoding='utf-8')
        if re.search(pattern, content, re.MULTILINE | re.DOTALL):
            print(f"✅ {description}")
            return True
        else:
            print(f"❌ {description}")
            return False
    except Exception as e:
        print(f"❌ {description} - Error: {e}")
        return False


def main():
    """Run all verification checks."""
    print("=" * 80)
    print("Layer List Fixes Verification")
    print("=" * 80)
    print()
    
    control_panel = Path("src/desktop_client/client_backend/desktop/control_panel.py")
    controller = Path("src/desktop_client/client_backend/desktop/controller.py")
    
    if not control_panel.exists():
        print(f"❌ File not found: {control_panel}")
        return False
    
    if not controller.exists():
        print(f"❌ File not found: {controller}")
        return False
    
    print("Checking control_panel.py...")
    print("-" * 80)
    
    checks = [
        # Fix 1: QBrush import
        (control_panel, r"from qtpy\.QtGui import.*QBrush", "Fix 1: QBrush imported at module level"),
        
        # Fix 2: CSS without !important
        (control_panel, r"selection-background-color:\s*#e8f4ff", "Fix 2: CSS has selection-background-color"),
        (control_panel, r"selection-color:\s*#000000", "Fix 2: CSS has selection-color"),
        
        # Fix 3: Custom drop handler with pre-capture
        (control_panel, r"self\._pre_drop_row_data\s*=\s*\[\]", "Fix 3: Pre-drop data storage initialized"),
        (control_panel, r"def _create_table_drop_handler\(self\):", "Fix 3: Custom drop handler exists"),
        (control_panel, r"Capture all row data BEFORE Qt's internal drop", "Fix 3: Pre-capture comment present"),
        
        # Fix 4: file_path storage
        (control_panel, r"file_item\.setData\(Qt\.ItemDataRole\.UserRole,\s*normalized_path\)", "Fix 4: file_path stored in UserRole"),
        (control_panel, r"file_path.*=.*file_item\.data\(Qt\.ItemDataRole\.UserRole\)", "Fix 4: file_path retrieved from UserRole"),
        
        # Fix 5: Reorder handler using pre-captured data
        (control_panel, r"data_by_filename\s*=\s*\{\}", "Fix 5: Filename mapping created"),
        (control_panel, r"if file_name in data_by_filename:", "Fix 5: Filename lookup used"),
    ]
    
    print()
    print("Checking controller.py...")
    print("-" * 80)
    
    checks.extend([
        # Visibility tracking
        (controller, r"self\._last_synced_visibility:\s*dict\[str,\s*bool\]\s*=\s*\{\}", "Optimization: Visibility tracking dict"),
        (controller, r"SKIP:\s*Visibility unchanged", "Optimization: Skip logic present"),
    ])
    
    print()
    
    all_passed = True
    for file_path, pattern, description in checks:
        if not check_file_contains(file_path, pattern, description):
            all_passed = False
    
    print()
    print("=" * 80)
    if all_passed:
        print("✅ ALL CHECKS PASSED - All fixes are in place!")
        print()
        print("Next steps:")
        print("1. Restart the application")
        print("2. Load 2+ layers")
        print("3. Test text visibility (should be black in all states)")
        print("4. Test drag-and-drop (should extract all layers)")
        print("5. Check console for 'Captured X rows' and 'Extracted X layers'")
        print("6. Verify no 'Layer not found' errors in JavaScript")
    else:
        print("❌ SOME CHECKS FAILED - Review the code changes")
        print()
        print("Please ensure all fixes from LAYER_LIST_FINAL_FIXES_COMPLETE.md are applied.")
    print("=" * 80)
    
    return all_passed


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
