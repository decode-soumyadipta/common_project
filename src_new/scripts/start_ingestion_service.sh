#!/usr/bin/env bash
# =============================================================================
# Ingestion Service Startup Script
# =============================================================================
# Starts the Ingestion Service (FastAPI) on Server 1.
# Requirements: 13.1, 13.8, 20.6, 20.7
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

# Activate conda environment
if ! command -v conda &> /dev/null; then
    echo "ERROR: conda command not found"
    echo ""
    echo "Installation Instructions:"
    echo "1. Install Miniconda or Anaconda from https://docs.conda.io/en/latest/miniconda.html"
    echo "2. Initialize conda: conda init bash"
    echo "3. Restart your shell"
    echo "4. Run this script again"
    exit 1
fi

CONDA_ENV_NAME="offline-3d-gis"
if ! conda env list | grep -q "^${CONDA_ENV_NAME} "; then
    echo "ERROR: Conda environment '$CONDA_ENV_NAME' not found"
    echo ""
    echo "Installation Instructions:"
    echo "1. Create the environment from environment.yml:"
    echo "   cd $PROJECT_ROOT"
    echo "   conda env create -f environment.yml"
    echo "2. Run this script again"
    exit 1
fi

# Activate conda environment
eval "$(conda shell.bash hook)"
conda activate "$CONDA_ENV_NAME"

# Verify required environment variables
REQUIRED_VARS=(
    "API_HOST"
    "INGESTION_SERVICE_PORT"
    "DATA_ROOT"
    "DATABASE_URL"
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

# Verify DATA_ROOT exists
if [[ ! -d "$DATA_ROOT" ]]; then
    echo "WARNING: DATA_ROOT directory does not exist: $DATA_ROOT"
    echo "Creating directory..."
    mkdir -p "$DATA_ROOT"
fi

# Set GDAL environment variables if defined
export GDAL_DISABLE_READDIR_ON_OPEN="${GDAL_DISABLE_READDIR_ON_OPEN:-EMPTY_DIR}"
export GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="${GDAL_HTTP_MERGE_CONSECUTIVE_RANGES:-YES}"

echo "=========================================="
echo "Starting Ingestion Service"
echo "=========================================="
echo "Host: $API_HOST"
echo "Port: $INGESTION_SERVICE_PORT"
echo "Data Root: $DATA_ROOT"
echo "Database: $DATABASE_URL"
echo "=========================================="

# Change to project root to ensure correct module imports
cd "$PROJECT_ROOT"

# Start the service with uvicorn
exec uvicorn services.ingestion.service:app \
    --host "$API_HOST" \
    --port "$INGESTION_SERVICE_PORT" \
    --log-level "${LOG_LEVEL:-info}" \
    --access-log
