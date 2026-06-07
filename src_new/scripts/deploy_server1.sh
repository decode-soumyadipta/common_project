#!/usr/bin/env bash
# =============================================================================
# Server 1 Deployment Script
# =============================================================================
# Deploys both Ingestion Service and Tile Service on Server 1.
# Starts services in background and logs their PIDs.
# Requirements: 13.6, 13.8
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Log directory
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"

# PID file
PID_FILE="$LOG_DIR/server1.pids"

echo "=========================================="
echo "Deploying Server 1 Components"
echo "=========================================="
echo "Components: Ingestion Service + Tile Service"
echo "Log Directory: $LOG_DIR"
echo "PID File: $PID_FILE"
echo "=========================================="

# Clean up old PID file
rm -f "$PID_FILE"

# Function to cleanup on exit
cleanup() {
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        echo ""
        echo "ERROR: Deployment failed with exit code $exit_code"
        echo "Cleaning up any started services..."
        
        # Kill any services that were started
        if [[ -f "$PID_FILE" ]]; then
            while IFS= read -r line; do
                if [[ $line =~ ^([^:]+):([0-9]+)$ ]]; then
                    local service="${BASH_REMATCH[1]}"
                    local pid="${BASH_REMATCH[2]}"
                    if kill -0 "$pid" 2>/dev/null; then
                        echo "Stopping $service (PID: $pid)..."
                        kill "$pid" 2>/dev/null || true
                    fi
                fi
            done < "$PID_FILE"
            rm -f "$PID_FILE"
        fi
    fi
}

trap cleanup EXIT

# Start Ingestion Service
echo ""
echo "Starting Ingestion Service..."
"$SCRIPT_DIR/start_ingestion_service.sh" > "$LOG_DIR/ingestion_service.log" 2>&1 &
INGESTION_PID=$!

# Wait a moment and check if it's still running
sleep 2
if ! kill -0 "$INGESTION_PID" 2>/dev/null; then
    echo "ERROR: Ingestion Service failed to start"
    echo "Check logs at: $LOG_DIR/ingestion_service.log"
    tail -n 20 "$LOG_DIR/ingestion_service.log"
    exit 1
fi

echo "Ingestion Service started (PID: $INGESTION_PID)"
echo "ingestion_service:$INGESTION_PID" >> "$PID_FILE"

# Start Tile Service
echo ""
echo "Starting Tile Service..."
"$SCRIPT_DIR/start_tile_service.sh" > "$LOG_DIR/tile_service.log" 2>&1 &
TILE_PID=$!

# Wait a moment and check if it's still running
sleep 2
if ! kill -0 "$TILE_PID" 2>/dev/null; then
    echo "ERROR: Tile Service failed to start"
    echo "Check logs at: $LOG_DIR/tile_service.log"
    tail -n 20 "$LOG_DIR/tile_service.log"
    exit 1
fi

echo "Tile Service started (PID: $TILE_PID)"
echo "tile_service:$TILE_PID" >> "$PID_FILE"

echo ""
echo "=========================================="
echo "Server 1 Deployment Successful"
echo "=========================================="
echo "Ingestion Service: PID $INGESTION_PID (log: $LOG_DIR/ingestion_service.log)"
echo "Tile Service: PID $TILE_PID (log: $LOG_DIR/tile_service.log)"
echo ""
echo "To stop services, run:"
echo "  kill $INGESTION_PID $TILE_PID"
echo ""
echo "Or use the PID file:"
echo "  while IFS=: read service pid; do kill \$pid; done < $PID_FILE"
echo "=========================================="

# Keep the script running to maintain the trap
wait
