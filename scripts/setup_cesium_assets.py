#!/usr/bin/env python3
"""Download and install CesiumJS build assets for the offline 3D GIS desktop app.

This script is meant to be run ONCE during initial project setup (or when
upgrading CesiumJS versions).  It downloads the CesiumJS release archive and
extracts the required build artefacts into the two directories where the
application expects them:

  1. ``src/offline_gis_app/desktop/web_assets/cesium/``
     – The canonical location for Cesium runtime files (Cesium.js, Assets/,
       Workers/, ThirdParty/, Widgets/).

  2. ``src/offline_gis_app/client_frontend/web_assets/cesium/``
     – A symlink (macOS/Linux) or copy (Windows) of directory 1, so that the
       ``index.html`` served via ``QWebEngineView`` can resolve ``./cesium/…``
       paths.

Usage::

    python scripts/setup_cesium_assets.py
    python scripts/setup_cesium_assets.py --version 1.119
"""

from __future__ import annotations

import argparse
import io
import os
import platform
import shutil
import sys
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

# Default CesiumJS version to download.
# IMPORTANT: Qt5 WebEngine uses Chromium 87, which only supports up to ES2015/ES2016.
# CesiumJS versions ≥ 1.90 use ES2020 features that crash V8 in Qt5.
# CesiumJS 1.78 is the latest confirmed compatible version.
DEFAULT_CESIUM_VERSION = "1.78"

# Where to install inside the project tree.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DESKTOP_CESIUM_DIR = PROJECT_ROOT / "src" / "offline_gis_app" / "desktop" / "web_assets" / "cesium"
FRONTEND_CESIUM_DIR = PROJECT_ROOT / "src" / "offline_gis_app" / "client_frontend" / "web_assets" / "cesium"

# Files/directories we need from the CesiumJS release.
REQUIRED_ENTRIES = [
    "Cesium.js",
    "Assets",
    "ThirdParty",
    "Widgets",
    "Workers",
]


def download_cesium(version: str, dest_dir: Path) -> None:
    """Download CesiumJS release zip and extract required files."""
    url = f"https://github.com/CesiumGS/cesium/releases/download/{version}/Cesium-{version}.zip"
    print(f"Downloading CesiumJS {version} from {url} ...")

    # Download to memory
    tmp_zip = dest_dir.parent / f"cesium-{version}-download.zip"
    try:
        urlretrieve(url, str(tmp_zip))
    except Exception as exc:
        print(f"Download failed: {exc}")
        print(f"\nAlternative: manually download from {url}")
        print(f"Then extract Cesium.js, Assets/, Workers/, ThirdParty/, Widgets/ into {dest_dir}")
        raise SystemExit(1) from exc

    print(f"Extracting to {dest_dir} ...")
    dest_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(str(tmp_zip), "r") as zf:
        # Find the prefix path inside the zip (varies by release)
        # Try common patterns: "Build/Cesium/", "Build/CesiumUnminified/", or root level
        all_names = zf.namelist()

        prefix = ""
        for candidate_prefix in ["Build/Cesium/", "Build/CesiumUnminified/", ""]:
            test_name = candidate_prefix + "Cesium.js"
            if test_name in all_names:
                prefix = candidate_prefix
                break

        if not prefix and "Cesium.js" not in all_names:
            # Try to find Cesium.js anywhere in the archive
            for name in all_names:
                if name.endswith("/Cesium.js") or name == "Cesium.js":
                    prefix = name.rsplit("Cesium.js", 1)[0]
                    break

        if prefix:
            print(f"  Found Cesium build files under prefix: '{prefix}'")
        else:
            print(f"  Cesium build files at archive root")

        extracted_count = 0
        for entry in all_names:
            if not entry.startswith(prefix):
                continue
            relative = entry[len(prefix):]
            if not relative:
                continue

            # Only extract required entries
            top_level = relative.split("/")[0]
            if top_level not in REQUIRED_ENTRIES:
                continue

            target_path = dest_dir / relative
            if entry.endswith("/"):
                target_path.mkdir(parents=True, exist_ok=True)
            else:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(entry) as src, open(str(target_path), "wb") as dst:
                    shutil.copyfileobj(src, dst)
                extracted_count += 1

        print(f"  Extracted {extracted_count} files.")

    # Clean up
    try:
        tmp_zip.unlink()
    except OSError:
        pass


def ensure_frontend_link(desktop_dir: Path, frontend_dir: Path) -> None:
    """Create symlink or copy from frontend web_assets/cesium → desktop cesium dir."""
    if frontend_dir.exists():
        if frontend_dir.is_symlink():
            current_target = os.readlink(str(frontend_dir))
            print(f"  Existing symlink: {frontend_dir} -> {current_target}")
            # Check if it points to the right place
            resolved = frontend_dir.resolve()
            if resolved == desktop_dir.resolve():
                print("  Symlink is already correct.")
                return
            else:
                print(f"  Symlink target mismatch. Removing and recreating.")
                frontend_dir.unlink()
        elif frontend_dir.is_dir():
            # Check if it has Cesium.js
            if (frontend_dir / "Cesium.js").exists():
                print(f"  Frontend cesium directory already has Cesium.js. Skipping link.")
                return
            else:
                print(f"  Frontend cesium directory exists but incomplete. Replacing.")
                shutil.rmtree(str(frontend_dir))
        else:
            print(f"  Removing unexpected file at {frontend_dir}")
            frontend_dir.unlink()

    is_windows = platform.system().lower() == "windows"
    if is_windows:
        print(f"  Windows detected: copying cesium assets to {frontend_dir}")
        shutil.copytree(str(desktop_dir), str(frontend_dir))
    else:
        # Create relative symlink
        try:
            rel_path = os.path.relpath(str(desktop_dir), str(frontend_dir.parent))
            frontend_dir.symlink_to(rel_path)
            print(f"  Created symlink: {frontend_dir} -> {rel_path}")
        except OSError as exc:
            print(f"  Symlink failed ({exc}), falling back to copy")
            shutil.copytree(str(desktop_dir), str(frontend_dir))


def verify_installation(cesium_dir: Path) -> bool:
    """Check that all required files/directories exist."""
    ok = True
    for entry in REQUIRED_ENTRIES:
        path = cesium_dir / entry
        if not path.exists():
            print(f"  MISSING: {path}")
            ok = False
        else:
            if path.is_file():
                size = path.stat().st_size
                print(f"  OK: {entry} ({size:,} bytes)")
            else:
                count = sum(1 for _ in path.rglob("*") if _.is_file())
                print(f"  OK: {entry}/ ({count} files)")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Setup CesiumJS assets for offline 3D GIS app")
    parser.add_argument(
        "--version", default=DEFAULT_CESIUM_VERSION,
        help=f"CesiumJS version to download (default: {DEFAULT_CESIUM_VERSION})"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Force re-download even if Cesium.js exists"
    )
    args = parser.parse_args()

    cesium_js_path = DESKTOP_CESIUM_DIR / "Cesium.js"
    widgets_css_path = DESKTOP_CESIUM_DIR / "Widgets" / "widgets.css"

    if cesium_js_path.exists() and widgets_css_path.exists() and not args.force:
        print(f"Cesium.js already exists at {cesium_js_path}")
        print("Use --force to re-download.")
    else:
        download_cesium(args.version, DESKTOP_CESIUM_DIR)

    print("\nVerifying desktop cesium installation:")
    desktop_ok = verify_installation(DESKTOP_CESIUM_DIR)

    print("\nSetting up frontend cesium link:")
    ensure_frontend_link(DESKTOP_CESIUM_DIR, FRONTEND_CESIUM_DIR)

    print("\nVerifying frontend cesium installation:")
    frontend_ok = verify_installation(FRONTEND_CESIUM_DIR)

    if desktop_ok and frontend_ok:
        print("\n✅ CesiumJS setup complete!")
        return 0
    else:
        print("\n❌ CesiumJS setup incomplete. Check the output above.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
