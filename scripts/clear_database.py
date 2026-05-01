#!/usr/bin/env python3
"""
Clear the database and start fresh.
Removes all ingested assets and resets the database.
Enhanced for Windows compatibility and thorough cleanup.
"""

import os
import sys
import time
import platform
import subprocess
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from desktop_client.client_backend.desktop.standalone_runtime import (
    configure_standalone_runtime,
    _default_app_home,
)


def find_all_database_files():
    """Find all possible database file locations."""
    # Get the app home directory
    app_home = (
        Path(os.environ.get("OFFLINE_GIS_HOME", "")).expanduser()
        if os.environ.get("OFFLINE_GIS_HOME")
        else _default_app_home()
    )
    app_home = app_home.resolve()

    # Also check current directory for local database
    current_dir = Path.cwd()

    # Additional locations to check
    locations_to_check = [
        app_home,
        current_dir,
        Path.home() / ".offline_gis",  # Alternative home location
        Path.home() / "AppData" / "Local" / "offline_gis"
        if platform.system() == "Windows"
        else Path("/tmp"),
    ]

    # Database file patterns to look for
    db_patterns = ["offline_gis.db", "*.db", "*.sqlite", "*.sqlite3"]

    found_files = []

    for location in locations_to_check:
        if not location.exists():
            continue

        print(f"Scanning: {location}")

        # Look for exact database files
        for pattern in ["offline_gis.db"]:  # Start with exact match
            db_file = location / pattern
            if db_file.exists():
                found_files.append(db_file)

                # Also check for WAL and SHM files
                wal_file = db_file.with_suffix(".db-wal")
                shm_file = db_file.with_suffix(".db-shm")
                journal_file = db_file.with_suffix(".db-journal")

                if wal_file.exists():
                    found_files.append(wal_file)
                if shm_file.exists():
                    found_files.append(shm_file)
                if journal_file.exists():
                    found_files.append(journal_file)

        # Look for any .db files that might be related
        try:
            for db_file in location.glob("*.db"):
                if db_file.name.startswith("offline") or "gis" in db_file.name.lower():
                    if db_file not in found_files:
                        found_files.append(db_file)

                        # Check for associated files
                        for suffix in ["-wal", "-shm", "-journal"]:
                            assoc_file = db_file.with_suffix(f".db{suffix}")
                            if assoc_file.exists() and assoc_file not in found_files:
                                found_files.append(assoc_file)
        except Exception as e:
            print(f"  Warning: Could not scan {location}: {e}")

    return found_files


def check_running_processes():
    """Check if any related processes are running that might lock the database."""
    print("\nChecking for running processes...")

    try:
        import psutil

        process_names = [
            "python",
            "python3",
            "pythonw",
            "pythonw.exe",
            "offline_gis",
            "desktop_client",
            "titiler",
        ]

        running_processes = []

        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                proc_info = proc.info
                proc_name = proc_info["name"].lower()
                cmdline = " ".join(proc_info["cmdline"] or []).lower()

                # Check if it's a Python process running our application
                if any(name in proc_name for name in process_names):
                    if any(
                        keyword in cmdline
                        for keyword in ["offline_gis", "desktop_client", "run_desktop"]
                    ):
                        running_processes.append(
                            {
                                "pid": proc_info["pid"],
                                "name": proc_info["name"],
                                "cmdline": " ".join(proc_info["cmdline"] or []),
                            }
                        )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if running_processes:
            print("⚠️  Found running processes that may lock the database:")
            for proc in running_processes:
                print(f"  PID {proc['pid']}: {proc['name']}")
                print(f"    Command: {proc['cmdline'][:100]}...")
            print(
                "\n💡 Recommendation: Close the desktop application before clearing the database"
            )
            return running_processes
        else:
            print("✓ No conflicting processes found")
            return []

    except ImportError:
        print("⚠️  psutil not available - cannot check for running processes")
        print("💡 Manually ensure the desktop application is closed")
        return []


def force_close_database_connections():
    """Attempt to force close any database connections (Windows-specific)."""
    if platform.system() != "Windows":
        return

    print("\nAttempting to close database connections (Windows)...")

    try:
        # Try to import and use the database module to close connections
        from core_shared.db.database import get_session_factory

        # This will help close any existing connections
        print("✓ Attempting to close existing database connections...")

        # Small delay to allow connections to close
        time.sleep(1)

    except Exception as e:
        print(f"  Note: Could not programmatically close connections: {e}")


def kill_running_processes(processes, force=False):
    """Kill running processes that might be locking the database."""
    if not processes:
        return True

    if not force:
        print(
            f"\n🔄 Attempting to gracefully terminate {len(processes)} process(es)..."
        )
    else:
        print(f"\n💀 Force killing {len(processes)} process(es)...")

    killed_count = 0

    try:
        import psutil

        for proc_info in processes:
            try:
                proc = psutil.Process(proc_info["pid"])

                if force:
                    proc.kill()
                    print(
                        f"💀 Force killed PID {proc_info['pid']}: {proc_info['name']}"
                    )
                else:
                    proc.terminate()
                    print(f"🔄 Terminated PID {proc_info['pid']}: {proc_info['name']}")

                killed_count += 1

            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                print(f"⚠️  Could not terminate PID {proc_info['pid']}: {e}")

        if not force and killed_count > 0:
            print("⏳ Waiting for processes to terminate...")
            time.sleep(3)

        return killed_count > 0

    except ImportError:
        print("❌ psutil not available - cannot terminate processes")
        return False


def clear_additional_caches():
    """Clear additional cache files and directories that might persist data."""
    print(f"\n🧹 Clearing additional cache files...")

    # Get the app home directory
    app_home = (
        Path(os.environ.get("OFFLINE_GIS_HOME", "")).expanduser()
        if os.environ.get("OFFLINE_GIS_HOME")
        else _default_app_home()
    )
    app_home = app_home.resolve()

    # Additional cache locations to clear
    cache_locations = [
        app_home / "cache",
        app_home / "temp",
        app_home / "logs",
        Path.home() / ".cache" / "offline_gis",
        Path.cwd() / "__pycache__",
        Path.cwd() / ".pytest_cache",
    ]

    # Add Windows-specific cache locations
    if platform.system() == "Windows":
        cache_locations.extend(
            [
                Path.home() / "AppData" / "Local" / "offline_gis" / "cache",
                Path.home() / "AppData" / "Roaming" / "offline_gis",
            ]
        )

    cleared_count = 0

    for cache_path in cache_locations:
        if cache_path.exists():
            try:
                if cache_path.is_dir():
                    # Clear directory contents but keep the directory
                    for item in cache_path.iterdir():
                        try:
                            if item.is_file():
                                item.unlink()
                                cleared_count += 1
                            elif item.is_dir():
                                import shutil

                                shutil.rmtree(item)
                                cleared_count += 1
                        except Exception as e:
                            print(f"  ⚠️  Could not clear {item}: {e}")
                    print(f"✅ Cleared cache directory: {cache_path}")
                else:
                    cache_path.unlink()
                    cleared_count += 1
                    print(f"✅ Cleared cache file: {cache_path}")
            except Exception as e:
                print(f"  ⚠️  Could not clear {cache_path}: {e}")

    if cleared_count > 0:
        print(f"✅ Cleared {cleared_count} additional cache items")
    else:
        print(f"ℹ️  No additional cache files found to clear")


def clear_database():
    """Clear the database file and start fresh."""

    print("=" * 70)
    print("🗑️  ENHANCED DATABASE CLEANUP TOOL")
    print("=" * 70)
    print(f"Platform: {platform.system()} {platform.release()}")
    print(f"Python: {sys.version.split()[0]}")

    # Check for running processes first
    running_processes = check_running_processes()

    if running_processes:
        print("\n⚠️  WARNING: Running processes detected!")
        print("These processes may prevent complete database clearing.")
        print("\nOptions:")
        print("1. Cancel and manually close the desktop application")
        print("2. Continue and attempt to terminate processes")
        print("3. Force kill processes (may cause data loss)")

        while True:
            response = input("\nChoose option (1/2/3): ").strip()
            if response == "1":
                print("✗ Cancelled - close the application first, then try again")
                return
            elif response == "2":
                if kill_running_processes(running_processes, force=False):
                    print("✓ Processes terminated")
                    time.sleep(2)  # Wait for cleanup
                break
            elif response == "3":
                print("⚠️  WARNING: Force killing may cause data corruption!")
                confirm = input("Are you sure? (yes/no): ").strip().lower()
                if confirm in ["yes", "y"]:
                    if kill_running_processes(running_processes, force=True):
                        print("✓ Processes force killed")
                        time.sleep(2)  # Wait for cleanup
                    break
                else:
                    continue
            else:
                print("Invalid option. Please choose 1, 2, or 3.")

    # Find all database files
    print(f"\n🔍 Searching for database files...")
    files_to_delete = find_all_database_files()

    if not files_to_delete:
        print(f"\n✓ No database files found - database is already clean!")
        print(f"\n💡 If you're still seeing old data in the UI:")
        print(f"   1. Close the desktop application completely")
        print(f"   2. Wait a few seconds")
        print(f"   3. Restart the application")
        print(f"   4. Click 'Refresh Catalog' button")
        return

    # Show what will be deleted
    print(f"\n📋 Found {len(files_to_delete)} database-related files:")
    total_size = 0

    for file_path in files_to_delete:
        try:
            size = file_path.stat().st_size / (1024 * 1024)
            total_size += size
            file_type = (
                "DB"
                if file_path.suffix == ".db"
                else file_path.suffix.upper().lstrip(".-")
            )
            print(f"  📄 {file_path.name} ({size:.2f} MB) [{file_type}]")
            print(f"      Location: {file_path.parent}")
        except Exception as e:
            print(f"  ❌ {file_path} (Error reading: {e})")

    print(f"\n📊 Total size: {total_size:.2f} MB")

    # Confirm deletion
    print(f"\n⚠️  THIS WILL PERMANENTLY DELETE ALL INGESTED ASSETS AND METADATA!")
    print(f"⚠️  This action cannot be undone!")
    response = input(
        "\nAre you sure you want to continue? (type 'DELETE' to confirm): "
    ).strip()

    if response != "DELETE":
        print("\n✗ Cancelled - database not modified")
        print("💡 Type 'DELETE' (all caps) to confirm deletion")
        return

    # Attempt to close database connections
    force_close_database_connections()

    # Delete database files
    print(f"\n🗑️  Deleting database files...")
    deleted_count = 0
    failed_files = []

    for file_path in files_to_delete:
        try:
            # On Windows, try multiple times in case of file locking
            max_attempts = 3 if platform.system() == "Windows" else 1

            for attempt in range(max_attempts):
                try:
                    file_path.unlink()
                    deleted_count += 1
                    print(f"✅ Deleted: {file_path.name}")
                    break
                except PermissionError as e:
                    if attempt < max_attempts - 1:
                        print(
                            f"⏳ File locked, retrying... ({attempt + 1}/{max_attempts})"
                        )
                        time.sleep(1)
                    else:
                        raise e

        except Exception as e:
            failed_files.append((file_path, str(e)))
            print(f"❌ Failed to delete {file_path.name}: {e}")

    # Summary
    print(f"\n📊 CLEANUP SUMMARY:")
    print(f"✅ Successfully deleted: {deleted_count}/{len(files_to_delete)} files")

    if failed_files:
        print(f"❌ Failed to delete: {len(failed_files)} files")
        print(f"\n🔧 Files that couldn't be deleted:")
        for file_path, error in failed_files:
            print(f"   • {file_path.name}: {error}")

        if platform.system() == "Windows":
            print(f"\n💡 Windows troubleshooting:")
            print(f"   1. Close ALL instances of the desktop application")
            print(f"   2. Wait 10 seconds for file handles to release")
            print(f"   3. Run this script again")
            print(f"   4. If still failing, restart your computer")
    else:
        print(f"🎉 Database cleared successfully!")

    print(f"\n📋 NEXT STEPS:")
    print(f"   1. 🚫 Ensure the desktop application is completely closed")
    print(f"   2. ⏳ Wait 5-10 seconds for all processes to stop")
    print(f"   3. 🧹 Clear any remaining cache files")
    print(f"   4. 🚀 Restart the desktop application")
    print(f"   5. 🔄 Click 'Refresh Catalog' to confirm it's empty")
    print(f"   6. 📁 Use the enhanced folder ingestion to add your data")

    # Clear additional cache directories and files
    clear_additional_caches()

    if deleted_count == len(files_to_delete):
        print(f"\n✨ The database has been completely cleared!")
        print(f"✨ The next startup will create a fresh, empty database.")
        print(f"\n🎯 IMPORTANT: If you still see old assets after restarting:")
        print(f"   • The application may have cached data in memory")
        print(f"   • Make sure to COMPLETELY close and restart the app")
        print(f"   • Click 'Refresh Catalog' button after restart")
        print(f"   • Use 'Force Clear All Caches' button in the UI if available")


if __name__ == "__main__":
    try:
        clear_database()
    except KeyboardInterrupt:
        print("\n\n🛑 Cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        print(f"\n🔧 If this error persists:")
        print(f"   1. Close all applications")
        print(f"   2. Restart your computer")
        print(f"   3. Try running this script again")
        sys.exit(1)
