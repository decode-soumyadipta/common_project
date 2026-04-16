#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="$ROOT_DIR/src/offline_gis_app/desktop/web_assets/basemap"
TARGET_FILE="$TARGET_DIR/world.jpg"
URL="https://eoimages.gsfc.nasa.gov/images/imagerecords/57000/57730/land_ocean_ice_2048.jpg"

mkdir -p "$TARGET_DIR"

if [[ -f "$TARGET_FILE" ]]; then
  echo "Basemap already present: $TARGET_FILE"
  exit 0
fi

echo "Downloading packaged offline world basemap..."
curl -fsSL "$URL" -o "$TARGET_FILE"
echo "Saved: $TARGET_FILE"
