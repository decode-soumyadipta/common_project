#!/bin/bash
# Start Desktop Ingestion Client (for uploading raster data)

PROJECT_DIR="/Users/soumyadiptadey/Developer/common_project"

echo "Starting Desktop Ingestion Client..."
echo "Use this to upload raster files to the system."
echo ""

cd "$PROJECT_DIR"
# Activate conda environment
source $(conda info --base)/etc/profile.d/conda.sh
conda activate offline-3d-gis
python -m src_new.clients.desktop_ingestion
