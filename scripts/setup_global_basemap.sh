#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_ROOT="$ROOT_DIR/src/offline_gis_app/client_frontend/web_assets/basemap/xyz"
SOURCE_URL="${BASE_URL:-https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile}"
SOURCE_URL="${SOURCE_URL//$'\r'/}"
CONCURRENCY="${CONCURRENCY:-12}"

usage() {
  cat >&2 <<'EOF'
Usage:
  bash scripts/setup_global_basemap.sh [max_zoom]
  bash scripts/setup_global_basemap.sh --world [max_zoom]
  bash scripts/setup_global_basemap.sh --asia [max_zoom]

Examples:
  bash scripts/setup_global_basemap.sh 7
  bash scripts/setup_global_basemap.sh --world 7
  bash scripts/setup_global_basemap.sh --asia 10
EOF
}

resolve_python() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    echo "$PYTHON_BIN"
    return
  fi
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

REGION="world"
MAX_ZOOM="7"

if [[ $# -ge 1 ]]; then
  case "$1" in
    --world)
      REGION="world"
      MAX_ZOOM="${2:-7}"
      ;;
    --asia)
      REGION="asia"
      MAX_ZOOM="${2:-10}"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      MAX_ZOOM="$1"
      ;;
  esac
fi

if ! [[ "$MAX_ZOOM" =~ ^[0-9]+$ ]]; then
  echo "MAX_ZOOM must be an integer, got: $MAX_ZOOM" >&2
  exit 1
fi

mkdir -p "$TARGET_ROOT"

manifest_file="$(mktemp)"
failed_file="$(mktemp)"
trap 'rm -f "$manifest_file" "$failed_file"' EXIT

case "$REGION" in
  world)
    WEST="-180.0"
    SOUTH="-85.0"
    EAST="180.0"
    NORTH="85.0"
    ;;
  asia)
    WEST="25.0"
    SOUTH="-12.0"
    EAST="180.0"
    NORTH="82.0"
    ;;
  *)
    echo "Unsupported region: $REGION" >&2
    exit 1
    ;;
esac

PYTHON_BIN="$(resolve_python)"

echo "Preparing $REGION XYZ tile manifest for zoom levels 0..$MAX_ZOOM"
"$PYTHON_BIN" - "$WEST" "$SOUTH" "$EAST" "$NORTH" "$MAX_ZOOM" > "$manifest_file" <<'PY'
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

tr -d '\r' < "$manifest_file" > "${manifest_file}.tmp"
mv "${manifest_file}.tmp" "$manifest_file"

sort -u "$manifest_file" -o "$manifest_file"

manifest_count=$(wc -l < "$manifest_file" | tr -d ' ')
scan_progress_interval=5000
processed_count=0

missing_count=0
existing_count=0
while read -r z x y; do
  processed_count=$((processed_count + 1))
  tile_file="$TARGET_ROOT/$z/$x/$y.jpg"
  if [[ -f "$tile_file" ]]; then
    existing_count=$((existing_count + 1))
  else
    missing_count=$((missing_count + 1))
  fi
  if (( processed_count % scan_progress_interval == 0 )); then
    echo "Scan progress: $processed_count/$manifest_count"
  fi
done < "$manifest_file"

total_count=$((existing_count + missing_count))
echo "Tiles total=$total_count existing=$existing_count missing=$missing_count"

if [[ "$missing_count" -gt 0 ]]; then
  echo "Downloading missing tiles with concurrency=$CONCURRENCY"
  export SOURCE_URL TARGET_ROOT failed_file
  cat "$manifest_file" | xargs -P "$CONCURRENCY" -n 3 bash -c '
    z="$1"
    x="$2"
    y="$3"
    tile_dir="$TARGET_ROOT/$z/$x"
    mkdir -p "$tile_dir"
    tile_file="$tile_dir/$y.jpg"
    tmp_file="$tile_file.part"
    url="$SOURCE_URL/$z/$y/$x"
    for attempt in 1 2 3; do
      if curl --connect-timeout 12 --max-time 90 -fsSL "$url" -o "$tmp_file"; then
        mv "$tmp_file" "$tile_file"
        exit 0
      fi
    done
    rm -f "$tmp_file"
    echo "$z/$x/$y" >> "$failed_file"
  ' _
fi

failed_count=$(wc -l < "$failed_file" | tr -d ' ')
if [[ "$failed_count" -gt 0 ]]; then
  echo "Warning: $failed_count tiles failed to download."
  echo "First failed tiles:"
  head -n 15 "$failed_file"
fi

cat > "$TARGET_ROOT/metadata.json" <<EOF
{
  "scheme": "xyz",
  "source": "$SOURCE_URL",
  "max_zoom": $MAX_ZOOM,
  "region": "$REGION",
  "bounds": {
    "west": $WEST,
    "south": $SOUTH,
    "east": $EAST,
    "north": $NORTH
  }
}
EOF

echo "Offline basemap ready at: $TARGET_ROOT"
echo "Metadata written to: $TARGET_ROOT/metadata.json"
