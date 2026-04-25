#!/usr/bin/env python3
"""
Download OpenStreetMap tiles for Asia region with labels, borders, and place names.

This script downloads tiles from OpenStreetMap tile servers for the Asia region
and stores them in the basemap/xyz directory structure for offline use.

Usage:
    python scripts/download_asia_basemap.py --zoom-levels 0-8 --region asia
"""

import argparse
import math
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import sys

# Asia bounding box (approximate)
ASIA_BOUNDS = {
    "min_lat": -10.0,   # Southern Indonesia
    "max_lat": 55.0,    # Northern Russia/Mongolia
    "min_lon": 60.0,    # Western border (Iran/Pakistan)
    "max_lon": 150.0,   # Eastern border (Japan/Philippines)
}

# OpenStreetMap tile servers (use responsibly with rate limiting)
OSM_TILE_SERVERS = [
    "https://tile.openstreetmap.org/{z}/{x}/{y}.png",  # Standard OSM with labels
    # Alternative: "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
]

USER_AGENT = "Offline3DGIS/1.0 (Educational/Research Purpose)"


def lat_lon_to_tile(lat, lon, zoom):
    """Convert lat/lon to tile coordinates at given zoom level."""
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    x_tile = int((lon + 180.0) / 360.0 * n)
    y_tile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x_tile, y_tile


def get_tile_bounds_for_region(bounds, zoom):
    """Get all tile coordinates for a region at given zoom level."""
    min_x, min_y = lat_lon_to_tile(bounds["max_lat"], bounds["min_lon"], zoom)
    max_x, max_y = lat_lon_to_tile(bounds["min_lat"], bounds["max_lon"], zoom)
    
    # Ensure proper ordering
    if min_x > max_x:
        min_x, max_x = max_x, min_x
    if min_y > max_y:
        min_y, max_y = max_y, min_y
    
    return min_x, min_y, max_x, max_y


def download_tile(url, output_path, retry_count=3):
    """Download a single tile with retry logic."""
    for attempt in range(retry_count):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=30) as response:
                if response.status == 200:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(output_path, "wb") as f:
                        f.write(response.read())
                    return True
        except HTTPError as e:
            if e.code == 404:
                # Tile doesn't exist (ocean/empty area)
                return False
            elif e.code == 429:
                # Rate limited - wait longer
                wait_time = (attempt + 1) * 5
                print(f"  Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"  HTTP error {e.code}: {e.reason}")
                if attempt < retry_count - 1:
                    time.sleep(2)
        except URLError as e:
            print(f"  URL error: {e.reason}")
            if attempt < retry_count - 1:
                time.sleep(2)
        except Exception as e:
            print(f"  Unexpected error: {e}")
            if attempt < retry_count - 1:
                time.sleep(2)
    
    return False


def download_asia_tiles(output_dir, zoom_levels, tile_server, rate_limit_delay=0.1):
    """Download all tiles for Asia region at specified zoom levels."""
    output_dir = Path(output_dir)
    total_tiles = 0
    downloaded_tiles = 0
    skipped_tiles = 0
    
    for zoom in zoom_levels:
        print(f"\n{'='*60}")
        print(f"Downloading zoom level {zoom}")
        print(f"{'='*60}")
        
        min_x, min_y, max_x, max_y = get_tile_bounds_for_region(ASIA_BOUNDS, zoom)
        tiles_at_zoom = (max_x - min_x + 1) * (max_y - min_y + 1)
        total_tiles += tiles_at_zoom
        
        print(f"Tile range: X[{min_x}-{max_x}] Y[{min_y}-{max_y}]")
        print(f"Total tiles at zoom {zoom}: {tiles_at_zoom}")
        
        zoom_downloaded = 0
        zoom_skipped = 0
        
        for x in range(min_x, max_x + 1):
            for y in range(min_y, max_y + 1):
                tile_path = output_dir / str(zoom) / str(x) / f"{y}.png"
                
                # Skip if already exists
                if tile_path.exists():
                    zoom_skipped += 1
                    skipped_tiles += 1
                    continue
                
                # Download tile
                url = tile_server.format(z=zoom, x=x, y=y)
                success = download_tile(url, tile_path)
                
                if success:
                    zoom_downloaded += 1
                    downloaded_tiles += 1
                    
                    # Progress indicator
                    if zoom_downloaded % 100 == 0:
                        progress = (zoom_downloaded + zoom_skipped) / tiles_at_zoom * 100
                        print(f"  Progress: {progress:.1f}% ({zoom_downloaded} downloaded, {zoom_skipped} skipped)")
                else:
                    zoom_skipped += 1
                    skipped_tiles += 1
                
                # Rate limiting - be respectful to OSM servers
                time.sleep(rate_limit_delay)
        
        print(f"\nZoom {zoom} complete:")
        print(f"  Downloaded: {zoom_downloaded}")
        print(f"  Skipped: {zoom_skipped}")
    
    print(f"\n{'='*60}")
    print(f"Download complete!")
    print(f"{'='*60}")
    print(f"Total tiles processed: {total_tiles}")
    print(f"Downloaded: {downloaded_tiles}")
    print(f"Skipped: {skipped_tiles}")


def main():
    parser = argparse.ArgumentParser(
        description="Download OpenStreetMap tiles for Asia region"
    )
    parser.add_argument(
        "--zoom-levels",
        type=str,
        default="0-8",
        help="Zoom levels to download (e.g., '0-8' or '5,6,7')"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="src/offline_gis_app/desktop/web_assets/basemap/xyz",
        help="Output directory for tiles"
    )
    parser.add_argument(
        "--tile-server",
        type=str,
        default=OSM_TILE_SERVERS[0],
        help="Tile server URL template"
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=0.1,
        help="Delay between tile downloads in seconds (default: 0.1)"
    )
    parser.add_argument(
        "--region",
        type=str,
        default="asia",
        choices=["asia", "world"],
        help="Region to download (default: asia)"
    )
    
    args = parser.parse_args()
    
    # Parse zoom levels
    if "-" in args.zoom_levels:
        start, end = map(int, args.zoom_levels.split("-"))
        zoom_levels = list(range(start, end + 1))
    else:
        zoom_levels = [int(z) for z in args.zoom_levels.split(",")]
    
    print(f"OpenStreetMap Tile Downloader for Asia")
    print(f"{'='*60}")
    print(f"Output directory: {args.output_dir}")
    print(f"Zoom levels: {zoom_levels}")
    print(f"Tile server: {args.tile_server}")
    print(f"Rate limit: {args.rate_limit}s per tile")
    print(f"Region: {args.region}")
    print(f"\nNote: Please be respectful to OSM servers.")
    print(f"This download may take several hours depending on zoom levels.")
    print(f"{'='*60}\n")
    
    # Confirm before proceeding
    response = input("Proceed with download? (yes/no): ")
    if response.lower() not in ["yes", "y"]:
        print("Download cancelled.")
        return
    
    download_asia_tiles(
        output_dir=args.output_dir,
        zoom_levels=zoom_levels,
        tile_server=args.tile_server,
        rate_limit_delay=args.rate_limit
    )


if __name__ == "__main__":
    main()
