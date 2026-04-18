#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_QUANTIZED_DIR="$ROOT_DIR/src/offline_gis_app/desktop/web_assets/basemap/terrain"
TARGET_TERRAIN_RGB_DIR="$ROOT_DIR/src/offline_gis_app/desktop/web_assets/basemap/terrain-rgb"
TERRAIN_RGB_SOURCE="${TERRAIN_RGB_SOURCE:-https://s3.amazonaws.com/elevation-tiles-prod/terrarium}"
CONCURRENCY="${CONCURRENCY:-12}"

usage() {
  cat >&2 <<'EOF'
Usage:
  bash scripts/setup_offline_terrain_pack.sh /path/to/quantized-mesh-terrain
  bash scripts/setup_offline_terrain_pack.sh --asia [max_zoom]
  bash scripts/setup_offline_terrain_pack.sh --world [max_zoom]

Modes:
  1) Copy an existing quantized-mesh terrain pack (must include layer.json)
  2) Download a region terrain-rgb pack for offline runtime terrain

Examples:
  bash scripts/setup_offline_terrain_pack.sh --asia 8
  bash scripts/setup_offline_terrain_pack.sh --world 7
  bash scripts/setup_offline_terrain_pack.sh /data/offline/terrain-world
EOF
}

resolve_python() {
  if command -v python3 >/dev/null 2>&1; then
    echo "python3"
    return
  fi
  if command -v python >/dev/null 2>&1; then
    echo "python"
    return
  fi
  echo "Python is required but was not found in PATH." >&2
  exit 1
}

download_terrain_rgb_region() {
  local region="$1"
  local max_zoom="${2:-7}"
  if ! [[ "$max_zoom" =~ ^[0-9]+$ ]]; then
    echo "max_zoom must be an integer, got: $max_zoom" >&2
    exit 1
  fi

  local west
  local south
  local east
  local north
  case "$region" in
    asia)
      west="25.0"
      south="-12.0"
      east="180.0"
      north="82.0"
      ;;
    world)
      west="-180.0"
      south="-85.0"
      east="180.0"
      north="85.0"
      ;;
    *)
      echo "Unsupported terrain region: $region" >&2
      exit 1
      ;;
  esac
  local python_bin
  python_bin="$(resolve_python)"

  local manifest_file
  local failed_file
  manifest_file="$(mktemp)"
  failed_file="$(mktemp)"

  echo "Preparing $region terrain-rgb tile manifest (z=0..$max_zoom)..."
  "$python_bin" - "$west" "$south" "$east" "$north" "$max_zoom" > "$manifest_file" <<'PY'
import math
import sys

west = float(sys.argv[1])
south = float(sys.argv[2])
east = float(sys.argv[3])
north = float(sys.argv[4])
max_zoom = int(sys.argv[5])


def clamp_lat(lat: float) -> float:
    return max(-85.05112878, min(85.05112878, lat))


def lon_to_tile_x(lon: float, z: int) -> int:
    n = 1 << z
    x = int(math.floor((lon + 180.0) / 360.0 * n))
    return max(0, min(n - 1, x))


def lat_to_tile_y(lat: float, z: int) -> int:
    n = 1 << z
    lat_r = math.radians(clamp_lat(lat))
    y = int(math.floor((1.0 - math.log(math.tan(lat_r) + (1.0 / math.cos(lat_r))) / math.pi) / 2.0 * n))
    return max(0, min(n - 1, y))


for z in range(0, max_zoom + 1):
    x_min = lon_to_tile_x(min(west, east), z)
    x_max = lon_to_tile_x(max(west, east), z)
    y_min = lat_to_tile_y(max(north, south), z)
    y_max = lat_to_tile_y(min(north, south), z)
    if y_min > y_max:
        y_min, y_max = y_max, y_min
    for x in range(x_min, x_max + 1):
        for y in range(y_min, y_max + 1):
            print(f"{z} {x} {y}")
PY

  # Defensive de-duplication to avoid duplicate workers writing the same tile path.
  sort -u "$manifest_file" -o "$manifest_file"

  if [[ ! -s "$manifest_file" ]]; then
    echo "No tiles were generated for $region bbox. Nothing to download." >&2
    exit 1
  fi

  mkdir -p "$TARGET_TERRAIN_RGB_DIR"

  local missing_count=0
  local existing_count=0
  while read -r z x y; do
    local tile_file="$TARGET_TERRAIN_RGB_DIR/$z/$x/$y.png"
    if [[ -f "$tile_file" ]]; then
      existing_count=$((existing_count + 1))
      continue
    fi
    missing_count=$((missing_count + 1))
  done < "$manifest_file"

  local total_count=$((existing_count + missing_count))
  echo "Terrain tiles total=$total_count existing=$existing_count missing=$missing_count"

  if [[ "$missing_count" -gt 0 ]]; then
    export TARGET_TERRAIN_RGB_DIR TERRAIN_RGB_SOURCE failed_file
    xargs -P "$CONCURRENCY" -n 3 -r bash -c '
      z="$1"
      x="$2"
      y="$3"
      tile_dir="$TARGET_TERRAIN_RGB_DIR/$z/$x"
      tile_file="$tile_dir/$y.png"
      if [[ -f "$tile_file" ]]; then
        exit 0
      fi
      mkdir -p "$tile_dir"
      url="$TERRAIN_RGB_SOURCE/$z/$x/$y.png"
      for attempt in 1 2 3; do
        tmp_file="$(mktemp "$tile_file.part.XXXXXX")"
        if curl -fsSL --connect-timeout 20 "$url" -o "$tmp_file" && [[ -s "$tmp_file" ]]; then
          mv -f "$tmp_file" "$tile_file"
          exit 0
        fi
        rm -f "$tmp_file"
      done
      echo "$z/$x/$y" >> "$failed_file"
    ' _ < "$manifest_file"
  fi

  local failed_count
  failed_count="$(wc -l < "$failed_file" | tr -d ' ')"
  if [[ "$failed_count" -gt 0 ]]; then
    echo "Warning: $failed_count terrain tiles failed to download." >&2
    echo "First failed tiles:" >&2
    head -n 15 "$failed_file" >&2
  fi

  cat > "$TARGET_TERRAIN_RGB_DIR/metadata.json" <<EOF
{
  "scheme": "xyz",
  "encoding": "terrarium",
  "source": "$TERRAIN_RGB_SOURCE",
  "region": "$region",
  "max_zoom": $max_zoom,
  "bbox": {
    "west": $west,
    "south": $south,
    "east": $east,
    "north": $north
  },
  "attribution": "elevation-tiles-prod / Mapzen Terrarium"
}
EOF

  rm -f "$manifest_file" "$failed_file"

  echo "Offline $region terrain-rgb prepared at: $TARGET_TERRAIN_RGB_DIR"
  echo "Restart desktop app to activate offline terrain in RGB 3D mode."
}

copy_quantized_mesh_pack() {
  local source_dir="$1"
  if [[ ! -d "$source_dir" ]]; then
    echo "Source directory not found: $source_dir" >&2
    exit 1
  fi
  if [[ ! -f "$source_dir/layer.json" ]]; then
    echo "Invalid terrain pack: missing layer.json in $source_dir" >&2
    exit 1
  fi

  rm -rf "$TARGET_QUANTIZED_DIR"
  mkdir -p "$(dirname "$TARGET_QUANTIZED_DIR")"
  cp -R "$source_dir" "$TARGET_QUANTIZED_DIR"

  echo "Offline quantized-mesh terrain pack installed at: $TARGET_QUANTIZED_DIR"
  echo "Restart desktop app to activate offline terrain in RGB 3D mode."
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

if [[ "$1" == "--asia" ]]; then
  download_terrain_rgb_region "asia" "${2:-7}"
  exit 0
fi

if [[ "$1" == "--world" ]]; then
  download_terrain_rgb_region "world" "${2:-7}"
  exit 0
fi

if [[ "$1" == "-h" || "$1" == "--help" ]]; then
  usage
  exit 0
fi

copy_quantized_mesh_pack "$1"
