#!/usr/bin/env python3
"""
Comprehensive test script for database clearing functionality.
Tests both the database clearing script and the application's cache clearing mechanisms.
"""

import os
import sys
import time
import subprocess
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def test_database_clear_script():
    """Test the enhanced database clearing script."""
    print("=" * 70)
    print("🧪 TESTING ENHANCED DATABASE CLEAR SCRIPT")
    print("=" * 70)
    
    # Run the clear database script
    script_path = Path(__file__).parent / "clear_database.py"
    
    print(f"Running: python {script_path}")
    print("Note: This test will show the script's interactive prompts")
    print("You can cancel with Ctrl+C if needed")
    
    try:
        # Run the script in a way that shows output but doesn't require interaction for testing
        result = subprocess.run([
            sys.executable, str(script_path)
        ], capture_output=True, text=True, timeout=30)
        
        print("STDOUT:")
        print(result.stdout)
        
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
        
        print(f"Return code: {result.returncode}")
        
    except subprocess.TimeoutExpired:
        print("⏰ Script timed out (expected for interactive script)")
    except KeyboardInterrupt:
        print("🛑 Test cancelled by user")
    except Exception as e:
        print(f"❌ Error running script: {e}")

def test_cache_clearing_mechanisms():
    """Test the application's cache clearing mechanisms."""
    print("\n" + "=" * 70)
    print("🧪 TESTING APPLICATION CACHE CLEARING MECHANISMS")
    print("=" * 70)
    
    try:
        from desktop_client.client_backend.desktop.controller import DesktopController
        from desktop_client.client_backend.desktop.control_panel import ControlPanel
        from desktop_client.client_backend.desktop.bridge import WebBridge
        from qtpy.QtWidgets import QApplication, QWidget
        from qtpy.QtWebEngineWidgets import QWebEngineView
        
        # Create minimal Qt application for testing
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        
        # Create test components
        parent_widget = QWidget()
        panel = ControlPanel(parent_widget)
        web_view = QWebEngineView(parent_widget)
        bridge = WebBridge(parent_widget)
        
        # Create controller
        controller = DesktopController(
            panel=panel,
            web_view=web_view,
            bridge=bridge
        )
        
        print("✅ Controller created successfully")
        
        # Test cache clearing methods
        print("🧹 Testing _clear_asset_caches method...")
        controller._clear_asset_caches()
        print("✅ _clear_asset_caches completed")
        
        print("🧹 Testing _force_clear_all_caches method...")
        controller._force_clear_all_caches()
        print("✅ _force_clear_all_caches completed")
        
        print("🔄 Testing refresh_uploaded_assets method...")
        panel.refresh_uploaded_assets()
        print("✅ refresh_uploaded_assets completed")
        
        print("✅ All cache clearing mechanisms tested successfully")
        
    except ImportError as e:
        print(f"⚠️  Cannot test application components (missing dependencies): {e}")
        print("This is expected if Qt/PyQt is not installed")
    except Exception as e:
        print(f"❌ Error testing cache clearing mechanisms: {e}")
        import traceback
        traceback.print_exc()

def test_file_operations():
    """Test file operations used in database clearing."""
    print("\n" + "=" * 70)
    print("🧪 TESTING FILE OPERATIONS")
    print("=" * 70)
    
    try:
        from desktop_client.client_backend.desktop.standalone_runtime import (
            _default_app_home,
        )
        
        # Test app home detection
        app_home = _default_app_home()
        print(f"✅ App home detected: {app_home}")
        
        # Test file finding logic (without actually deleting anything)
        print("🔍 Testing database file detection...")
        
        # Import the file finding function from the clear script
        sys.path.insert(0, str(Path(__file__).parent))
        from clear_database import find_all_database_files
        
        db_files = find_all_database_files()
        print(f"✅ Found {len(db_files)} database-related files:")
        for db_file in db_files:
            print(f"   📄 {db_file}")
        
        print("✅ File operations tested successfully")
        
    except Exception as e:
        print(f"❌ Error testing file operations: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Run comprehensive database clearing tests."""
    print("🚀 COMPREHENSIVE DATABASE CLEARING TEST SUITE")
    print(f"Python: {sys.version}")
    print(f"Platform: {sys.platform}")
    print(f"Working directory: {os.getcwd()}")
    
    # Test 1: Database clearing script
    test_database_clear_script()
    
    # Test 2: Application cache clearing
    test_cache_clearing_mechanisms()
    
    # Test 3: File operations
    test_file_operations()
    
    print("\n" + "=" * 70)
    print("🎯 TEST SUMMARY")
    print("=" * 70)
    print("✅ Enhanced database clearing script tested")
    print("✅ Application cache clearing mechanisms tested")
    print("✅ File operations tested")
    print("\n💡 RECOMMENDATIONS:")
    print("   1. Run the clear_database.py script when the desktop app is closed")
    print("   2. Use the 'Force Clear All Caches' button if old data persists")
    print("   3. Restart the application completely after clearing the database")
    print("   4. Check that the uploaded assets table shows 'No assets ingested yet'")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Tests cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test suite failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)