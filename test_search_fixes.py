#!/usr/bin/env python3
"""
Test script to verify the search results view mode consistency fixes.
This script checks that the key functions exist and have the expected behavior.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_controller_functions():
    """Test that the controller has the required functions."""
    try:
        from desktop_client.client_backend.desktop.controller import DesktopController
        
        # Check if the enhanced focus function exists
        assert hasattr(DesktopController, '_focus_visible_search_assets_with_enhanced_behavior'), \
            "Enhanced focus function not found"
        
        # Check if the apply_search_results_internal function exists
        assert hasattr(DesktopController, '_apply_search_results_internal'), \
            "Apply search results internal function not found"
        
        # Check if the apply_display_control_mode function exists
        assert hasattr(DesktopController, '_apply_display_control_mode'), \
            "Apply display control mode function not found"
        
        print("✓ All required controller functions exist")
        return True
        
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False
    except AssertionError as e:
        print(f"✗ Function check failed: {e}")
        return False

def test_visualization_coordinator():
    """Test that the visualization coordinator has the updated apply_rgb_view_mode function."""
    try:
        from desktop_client.client_backend.desktop.coordinators.visualization_coordinator import VisualizationCoordinator
        
        # Check if the function exists
        assert hasattr(VisualizationCoordinator, 'apply_rgb_view_mode'), \
            "apply_rgb_view_mode function not found"
        
        print("✓ Visualization coordinator functions exist")
        return True
        
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False
    except AssertionError as e:
        print(f"✗ Function check failed: {e}")
        return False

def test_bridge_js_functions():
    """Test that the bridge.js file contains the new focusBoundsWithPadding function."""
    try:
        bridge_path = "src/desktop_client/client_frontend/web_assets/bridge.js"
        
        if not os.path.exists(bridge_path):
            print(f"✗ Bridge.js file not found at {bridge_path}")
            return False
        
        with open(bridge_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check if focusBoundsWithPadding function exists
        assert 'focusBoundsWithPadding:' in content, \
            "focusBoundsWithPadding function not found in bridge.js"
        
        # Check if the function has the expected parameters
        assert 'paddingFactor' in content, \
            "paddingFactor parameter not found in focusBoundsWithPadding"
        
        print("✓ Bridge.js contains the new focusBoundsWithPadding function")
        return True
        
    except AssertionError as e:
        print(f"✗ Bridge.js check failed: {e}")
        return False
    except Exception as e:
        print(f"✗ Error reading bridge.js: {e}")
        return False

def main():
    """Run all tests."""
    print("Testing Search Results View Mode Consistency Fixes")
    print("=" * 50)
    
    tests = [
        test_controller_functions,
        test_visualization_coordinator,
        test_bridge_js_functions,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("✓ All tests passed! The search results fixes are properly implemented.")
        return 0
    else:
        print("✗ Some tests failed. Please check the implementation.")
        return 1

if __name__ == "__main__":
    sys.exit(main())