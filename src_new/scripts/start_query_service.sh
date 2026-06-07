#!/usr/bin/env bash
# =============================================================================
# Query Service Startup Script
# =============================================================================
# Starts the Query Service (FastAPI) on Server 2.
# Requirements: 13.3, 13.8, 20.6, 20.7
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
    "API_HOST"
    "QUERY_SERVICE_PORT"
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

echo "=========================================="
echo "Starting Query Service"
echo "=========================================="
echo "Host: $API_HOST"
echo "Port: $QUERY_SERVICE_PORT"
echo "Database: $DATABASE_URL"
echo "=========================================="

# Change to project root to ensure correct module imports
cd "$PROJECT_ROOT"

# Start the service with uvicorn
exec uvicorn services.query.service:app \
    --host "$API_HOST" \
    --port "$QUERY_SERVICE_PORT" \
    --log-level "${LOG_LEVEL:-info}" \
    --access-log
