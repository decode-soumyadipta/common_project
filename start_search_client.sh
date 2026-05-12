#!/bin/bash
# Start Desktop Search Client (full-featured 3D GIS with CesiumJS)

PROJECT_DIR="/Users/soumyadiptadey/Developer/common_project"

echo "Starting Desktop Search Client..."
echo "Full-featured 3D GIS with:"
echo "  - CesiumJS 3D Globe"
echo "  - Layer Comparator & Compositor"
echo "  - Measurement Tools"
echo "  - Annotation Tools"
echo "  - Search & Visualization"
echo ""

cd "$PROJECT_DIR"
python -m src_new.clients.desktop_search.main
