#!/usr/bin/env python3
"""
Clear the database and start fresh.
Removes all ingested assets and resets the database.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from desktop_client.client_backend.desktop.standalone_runtime import (
    configure_standalone_runtime,
    _default_app_home,
)


def clear_database():
    """Clear the database file and start fresh."""
    
    # Get the app home directory
    app_home = (
        Path(os.environ.get("OFFLINE_GIS_HOME", "")).expanduser()
        if os.environ.get("OFFLINE_GIS_HOME")
        else _default_app_home()
    )
    app_home = app_home.resolve()
    
    # Also check current directory for local database
    current_dir = Path.cwd()
    
    print("=" * 60)
    print("Database Cleanup Tool")
    print("=" * 60)
    print(f"\nApp Home: {app_home}")
    print(f"Current Directory: {current_dir}")
    
    # List of database locations to check
    db_locations = [
        app_home / "offline_gis.db",
        current_dir / "offline_gis.db",
    ]
    
    files_to_delete = []
    total_size = 0
    
    # Find all database files
    for db_path in db_locations:
        if db_path.exists():
            size = db_path.stat().st_size / (1024 * 1024)
            total_size += size
            files_to_delete.append(db_path)
            print(f"\n✓ Found database: {db_path} ({size:.2f} MB)")
            
            # Check for WAL and SHM files
            db_wal = db_path.with_suffix('.db-wal')
            db_shm = db_path.with_suffix('.db-shm')
            
            if db_wal.exists():
                wal_size = db_wal.stat().st_size / (1024 * 1024)
                total_size += wal_size
                files_to_delete.append(db_wal)
                print(f"  + WAL file: {db_wal.name} ({wal_size:.2f} MB)")
            
            if db_shm.exists():
                shm_size = db_shm.stat().st_size / (1024 * 1024)
                total_size += shm_size
                files_to_delete.append(db_shm)
                print(f"  + SHM file: {db_shm.name} ({shm_size:.2f} MB)")
    
    if not files_to_delete:
        print(f"\n✓ No database files found - nothing to clear")
        print(f"\nNote: If you're seeing old data in the UI:")
        print(f"  1. Close the desktop application completely")
        print(f"  2. Restart it")
        print(f"  3. The cache will be cleared automatically")
        return
    
    print(f"\nTotal size: {total_size:.2f} MB")
    print(f"Files to delete: {len(files_to_delete)}")
    
    # Confirm deletion
    print("\n⚠️  This will DELETE all ingested assets and metadata!")
    response = input("Are you sure you want to continue? (yes/no): ").strip().lower()
    
    if response not in ["yes", "y"]:
        print("\n✗ Cancelled - database not modified")
        return
    
    # Delete database files
    deleted_count = 0
    
    for file_path in files_to_delete:
        try:
            file_path.unlink()
            deleted_count += 1
            print(f"✓ Deleted: {file_path}")
        except Exception as e:
            print(f"✗ Failed to delete {file_path}: {e}")
    
    print(f"\n✓ Database cleared successfully!")
    print(f"  Deleted {deleted_count}/{len(files_to_delete)} file(s)")
    print(f"\nNext steps:")
    print(f"  1. Close the desktop application if it's running")
    print(f"  2. Restart the desktop application")
    print(f"  3. A fresh database will be created automatically")
    print(f"  4. Ingest your data again")


if __name__ == "__main__":
    try:
        clear_database()
    except KeyboardInterrupt:
        print("\n\n✗ Cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
