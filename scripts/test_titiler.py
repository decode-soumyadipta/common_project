#!/usr/bin/env python3
"""
Test TiTiler server connectivity and tile generation.
"""

import sys
import requests
import math
from pathlib import Path
from urllib.parse import quote


def deg2num(lat_deg, lon_deg, zoom):
    """Convert lat/lon to tile coordinates for given zoom level."""
    lat_rad = math.radians(lat_deg)
    n = 2.0**zoom
    x = int((lon_deg + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return (x, y)


def num2deg(x, y, zoom):
    """Convert tile coordinates to lat/lon bounds."""
    n = 2.0**zoom
    lon_deg = x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat_deg = math.degrees(lat_rad)
    return (lat_deg, lon_deg)


def test_titiler_server():
    """Test if TiTiler server is running and can generate tiles."""

    base_url = "http://127.0.0.1:8081"

    print("=" * 60)
    print("TiTiler Server Test")
    print("=" * 60)

    # Test 1: Server health check
    try:
        response = requests.get(f"{base_url}/healthz", timeout=5)
        if response.status_code == 200:
            print("✓ TiTiler server is running")
        else:
            print(f"✗ TiTiler server returned status {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"✗ TiTiler server is not reachable: {e}")
        print("\nTo start TiTiler server:")
        print("  uvicorn titiler.application.main:app --host 127.0.0.1 --port 8081")
        return False

    # Test 2: Check available endpoints
    try:
        response = requests.get(f"{base_url}/docs", timeout=5)
        if response.status_code == 200:
            print("✓ TiTiler API documentation is available")
        else:
            print(f"⚠ TiTiler docs returned status {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"⚠ TiTiler docs not accessible: {e}")

    # Test 3: Test with actual data files
    data_dir = Path("data_test")
    if not data_dir.exists():
        print(f"⚠ Test data directory not found: {data_dir}")
        return True

    tif_files = list(data_dir.glob("*.tif"))
    if not tif_files:
        print(f"⚠ No .tif files found in {data_dir}")
        return True

    # Test with first TIF file
    test_file = tif_files[0]
    file_url = quote(str(test_file.resolve()), safe=":/")

    print(f"\nTesting with file: {test_file}")
    print(f"Encoded URL: {file_url}")

    # Use the actual WGS84 bounds from the application logs
    # These are the bounds that the application is using
    actual_bounds = {
        "west": 87.1702693776709,
        "south": 23.65950239174837,
        "east": 87.2703836042859,
        "north": 23.752047794413638,
    }

    print(f"\n📍 Using actual WGS84 bounds from application:")
    print(
        f"  - Bounds: west={actual_bounds['west']:.6f}, south={actual_bounds['south']:.6f}"
    )
    print(
        f"           east={actual_bounds['east']:.6f}, north={actual_bounds['north']:.6f}"
    )

    # Calculate center point
    center_lon = (actual_bounds["west"] + actual_bounds["east"]) / 2
    center_lat = (actual_bounds["south"] + actual_bounds["north"]) / 2
    print(f"  - Center: lon={center_lon:.6f}, lat={center_lat:.6f}")

    # Test tiles at different zoom levels for the actual data bounds
    print(f"\n📍 Testing tiles at data center coordinates:")
    for zoom in [10, 11, 12, 13, 14]:
        x, y = deg2num(center_lat, center_lon, zoom)
        print(f"  - Zoom {zoom}: x={x}, y={y}")

        # Test this specific tile
        tile_url = (
            f"{base_url}/cog/tiles/WebMercatorQuad/{zoom}/{x}/{y}.png?url={file_url}"
        )
        try:
            tile_response = requests.get(tile_url, timeout=10)
            if tile_response.status_code == 200:
                print(
                    f"    ✓ Tile z={zoom}/x={x}/y={y} SUCCESS ({len(tile_response.content)} bytes)"
                )
            elif tile_response.status_code == 404:
                print(f"    ✗ Tile z={zoom}/x={x}/y={y} NOT FOUND (404)")
            else:
                print(
                    f"    ✗ Tile z={zoom}/x={x}/y={y} ERROR ({tile_response.status_code})"
                )
        except requests.exceptions.RequestException as e:
            print(f"    ✗ Tile z={zoom}/x={x}/y={y} FAILED: {e}")

    # Test corner tiles
    print(f"\n📍 Testing corner tiles:")
    for zoom in [11, 12]:
        # Southwest corner
        sw_x, sw_y = deg2num(actual_bounds["south"], actual_bounds["west"], zoom)
        # Northeast corner
        ne_x, ne_y = deg2num(actual_bounds["north"], actual_bounds["east"], zoom)

        print(f"  - Zoom {zoom}: SW=({sw_x},{sw_y}) NE=({ne_x},{ne_y})")

        # Test southwest corner tile
        tile_url = f"{base_url}/cog/tiles/WebMercatorQuad/{zoom}/{sw_x}/{sw_y}.png?url={file_url}"
        try:
            tile_response = requests.get(tile_url, timeout=10)
            status = (
                "✓ SUCCESS"
                if tile_response.status_code == 200
                else f"✗ {tile_response.status_code}"
            )
            print(f"    SW corner: {status}")
        except:
            print(f"    SW corner: ✗ FAILED")

        # Test northeast corner tile
        tile_url = f"{base_url}/cog/tiles/WebMercatorQuad/{zoom}/{ne_x}/{ne_y}.png?url={file_url}"
        try:
            tile_response = requests.get(tile_url, timeout=10)
            status = (
                "✓ SUCCESS"
                if tile_response.status_code == 200
                else f"✗ {tile_response.status_code}"
            )
            print(f"    NE corner: {status}")
        except:
            print(f"    NE corner: ✗ FAILED")

    # Test the exact tile coordinates that would be requested by Cesium
    print(f"\n📍 Testing tiles that Cesium would request:")

    # Test a range of tiles around the center at zoom 12 (which is in the minzoom/maxzoom range)
    center_x, center_y = deg2num(center_lat, center_lon, 12)
    for dx in [-1, 0, 1]:
        for dy in [-1, 0, 1]:
            test_x = center_x + dx
            test_y = center_y + dy
            tile_url = f"{base_url}/cog/tiles/WebMercatorQuad/12/{test_x}/{test_y}.png?url={file_url}"
            try:
                tile_response = requests.get(tile_url, timeout=10)
                if tile_response.status_code == 200:
                    print(
                        f"    ✓ Tile 12/{test_x}/{test_y} SUCCESS ({len(tile_response.content)} bytes)"
                    )
                elif tile_response.status_code == 404:
                    print(f"    ✗ Tile 12/{test_x}/{test_y} NOT FOUND (404)")
                else:
                    print(
                        f"    ✗ Tile 12/{test_x}/{test_y} ERROR ({tile_response.status_code})"
                    )
            except requests.exceptions.RequestException as e:
                print(f"    ✗ Tile 12/{test_x}/{test_y} FAILED: {e}")

    print(f"\n✓ TiTiler server testing completed!")
    return True


if __name__ == "__main__":
    try:
        success = test_titiler_server()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n✗ Cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
