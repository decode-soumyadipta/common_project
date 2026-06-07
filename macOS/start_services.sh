#!/bin/bash
# Start all 3 backend services in separate terminal tabs/windows

echo "Starting Offline 3D GIS Backend Services..."
echo ""
echo "This will open 3 terminal windows for:"
echo "  1. Ingestion Service (Port 8001)"
echo "  2. Tile Service (Port 8002)"
echo "  3. Query Service (Port 8003)"
echo ""

# Get the project directory
PROJECT_DIR="/Users/soumyadiptadey/Developer/common_project"

# macOS - use osascript to open new terminal tabs
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "Opening services in new terminal tabs..."
    
    CONDA_ACTIVATE="source \$(conda info --base)/etc/profile.d/conda.sh && conda activate offline-3d-gis"
    
    # Ingestion Service
    osascript -e "tell application \"Terminal\"
        do script \"cd $PROJECT_DIR && $CONDA_ACTIVATE && echo 'Starting Ingestion Service on port 8001...' && uvicorn src_new.services.ingestion.service:app --host 127.0.0.1 --port 8001\"
    end tell"
    
    sleep 1
    
    # Tile Service
    osascript -e "tell application \"Terminal\"
        do script \"cd $PROJECT_DIR && $CONDA_ACTIVATE && echo 'Starting Tile Service on port 8002...' && uvicorn src_new.services.tile_serving.service:app --host 127.0.0.1 --port 8002 --workers 4\"
    end tell"
    
    sleep 1
    
    # Query Service
    osascript -e "tell application \"Terminal\"
        do script \"cd $PROJECT_DIR && $CONDA_ACTIVATE && echo 'Starting Query Service on port 8003...' && uvicorn src_new.services.query.service:app --host 127.0.0.1 --port 8003\"
    end tell"
    
    echo ""
    echo "✅ All services started in separate terminal tabs!"
    echo ""
    echo "Wait 5-10 seconds for services to start, then run:"
    echo "  ./start_ingestion_client.sh  (to upload data)"
    echo "  ./start_search_client.sh     (to search and visualize)"
    
else
    # Linux/Windows - print manual commands
    echo "Please open 3 separate terminals and run:"
    echo ""
    echo "Terminal 1:"
    echo "  cd $PROJECT_DIR"
    echo "  source \$(conda info --base)/etc/profile.d/conda.sh && conda activate offline-3d-gis"
    echo "  uvicorn src_new.services.ingestion.service:app --host 127.0.0.1 --port 8001 --reload"
    echo ""
    echo "Terminal 2:"
    echo "  cd $PROJECT_DIR"
    echo "  source \$(conda info --base)/etc/profile.d/conda.sh && conda activate offline-3d-gis"
    echo "  uvicorn src_new.services.tile_serving.service:app --host 127.0.0.1 --port 8002 --workers 4"
    echo ""
    echo "Terminal 3:"
    echo "  cd $PROJECT_DIR"
    echo "  source \$(conda info --base)/etc/profile.d/conda.sh && conda activate offline-3d-gis"
    echo "  uvicorn src_new.services.query.service:app --host 127.0.0.1 --port 8003 --reload"
fi
