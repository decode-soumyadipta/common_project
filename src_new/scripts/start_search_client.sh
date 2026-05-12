#!/usr/bin/env bash
# =============================================================================
# Search Client Startup Script
# =============================================================================
# Starts the Desktop Search Client (PySide6 + CesiumJS application).
# Requirements: 13.5, 13.8, 20.6, 20.7
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Source environment variables
ENV_FILE="$PROJECT_ROOT/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: .env file not found at $ENV_FILE"
    echo ""
    echo "Installation Instructions:"
    echo "1. Copy .env.example to .env:"
    echo "   cp $PROJECT_ROOT/.env.example $PROJECT_ROOT/.env"
    echo "2. Edit .env and configure the required variables"
    echo "3. Run this script again"
    exit 1
fi

# Load environment variables
set -a
source "$ENV_FILE"
set +a

# Verify required environment variables
REQUIRED_VARS=(
    "QUERY_SERVICE_URL"
    "TILE_SERVICE_URL"
    "CESIUM_BASE_URL"
)

MISSING_VARS=()
for var in "${REQUIRED_VARS[@]}"; do
    if [[ -z "${!var:-}" ]]; then
        MISSING_VARS+=("$var")
    fi
done

if [[ ${#MISSING_VARS[@]} -gt 0 ]]; then
    echo "ERROR: Missing required environment variables:"
    for var in "${MISSING_VARS[@]}"; do
        echo "  - $var"
    done
    echo ""
    echo "Please set these variables in $ENV_FILE"
    exit 1
fi

echo "=========================================="
echo "Starting Search Client"
echo "=========================================="
echo "Query Service: $QUERY_SERVICE_URL"
echo "Tile Service: $TILE_SERVICE_URL"
echo "Cesium Base URL: $CESIUM_BASE_URL"
echo "=========================================="

# Change to project root to ensure correct module imports
cd "$PROJECT_ROOT"

# Start the desktop client
exec python -m clients.desktop_search.main
