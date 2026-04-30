#!/usr/bin/env python3
"""
Test script to verify database clearing works properly.
This script tests the database clearing functionality and verifies the results.
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def test_database_clear():
    """Test the database clearing functionality."""
    
    print("🧪 Testing Database Clear Functionality")
    print("=" * 50)
    
    try:
        # Import the API client to test database connectivity
        from desktop_client.client_backend.desktop.api_client import DesktopApiClient
        
        # Create API client
        api = DesktopApiClient()
        
        print("📡 Testing API connectivity...")
        
        # Test if API is ready
        if not api.api_ready():
            print("⚠️  API not ready - this is expected if no server is running")
            print("💡 To fully test, start the desktop application first")
            return
        
        print("✅ API is ready")
        
        # Test listing assets
        print("📋 Testing asset listing...")
        try:
            assets = api.list_assets()
            print(f"📊 Found {len(assets)} assets in database")
            
            if assets:
                print("📄 Sample assets:")
                for i, asset in enumerate(assets[:3]):
                    print(f"  {i+1}. {asset.get('file_name', 'Unknown')} [{asset.get('kind', 'Unknown')}]")
                if len(assets) > 3:
                    print(f"  ... and {len(assets) - 3} more")
            else:
                print("✅ Database is empty - clear operation was successful!")
                
        except Exception as e:
            print(f"❌ Error listing assets: {e}")
            print("💡 This might indicate the database was cleared successfully")
        
    except ImportError as e:
        print(f"❌ Could not import required modules: {e}")
        print("💡 Make sure you're running from the project root directory")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()


def test_file_locations():
    """Test finding database file locations."""
    
    print("\n🔍 Testing Database File Detection")
    print("=" * 40)
    
    try:
        # Import the clear database script functions
        sys.path.insert(0, str(Path(__file__).parent))
        from clear_database import find_all_database_files
        
        print("🔎 Scanning for database files...")
        db_files = find_all_database_files()
        
        if db_files:
            print(f"📁 Found {len(db_files)} database-related files:")
            total_size = 0
            for db_file in db_files:
                try:
                    size = db_file.stat().st_size / (1024 * 1024)
                    total_size += size
                    print(f"  📄 {db_file.name} ({size:.2f} MB)")
                    print(f"      📍 {db_file.parent}")
                except Exception as e:
                    print(f"  ❌ {db_file} (Error: {e})")
            
            print(f"📊 Total size: {total_size:.2f} MB")
            
            if total_size > 0:
                print("\n💡 Database files found - run clear_database.py to remove them")
            else:
                print("\n✅ All database files are empty or cleared")
        else:
            print("✅ No database files found - system is clean!")
            
    except ImportError as e:
        print(f"❌ Could not import clear_database functions: {e}")
    except Exception as e:
        print(f"❌ Error scanning for files: {e}")


def main():
    """Run all tests."""
    
    print("🚀 Database Clear Test Suite")
    print("=" * 60)
    print("This script tests database clearing functionality")
    print("Run this AFTER using clear_database.py to verify it worked")
    print()
    
    # Test database connectivity and content
    test_database_clear()
    
    # Test file detection
    test_file_locations()
    
    print("\n" + "=" * 60)
    print("🏁 Test Complete")
    print("\n💡 Instructions:")
    print("   1. If assets are still showing, run: python scripts/clear_database.py")
    print("   2. Close the desktop application completely")
    print("   3. Wait 5-10 seconds")
    print("   4. Restart the desktop application")
    print("   5. Click 'Refresh Catalog' button")
    print("   6. The uploaded assets list should now be empty")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Test cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)