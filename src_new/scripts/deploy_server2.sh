#!/usr/bin/env bash
# =============================================================================
# Server 2 Deployment Script
# =============================================================================
# Deploys the Query Service on Server 2.
# Requirements: 13.7, 13.8
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Log directory
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"

echo "=========================================="
echo "Deploying Server 2 Components"
echo "=========================================="
echo "Components: Query Service"
echo "Log Directory: $LOG_DIR"
echo "=========================================="

# Function to cleanup on exit
cleanup() {
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        echo ""
        echo "ERROR: Deployment failed with exit code $exit_code"
    fi
}

trap cleanup EXIT

# Start Query Service (foreground)
echo ""
echo "Starting Query Service..."
exec "$SCRIPT_DIR/start_query_service.sh"
