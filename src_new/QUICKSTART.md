# Quickstart Guide: Running the Geospatial Microservices System

This guide shows you how to run the refactored `src_new/` system on your Mac laptop.

## System Architecture

The system is split into **two deployment boundaries**:

- **Server 1** (Ingestion + Tile Services): Handles raster uploads, processing, and tile serving
- **Server 2** (Query Service): Handles spatial queries and metadata retrieval
- **Desktop Clients**: Two PySide6 applications (ingestion client and search client)

---

## Prerequisites

### 1. Install Dependencies

```bash
# Navigate to project root
cd /Users/soumyadiptadey/Developer/common_project

# Create conda environment from environment.yml
conda env create -f src_new/environment.yml

# Activate the environment
conda activate geospatial-services

# OR use pip if you prefer
pip install -r src_new/requirements.txt
```

### 2. Set Up PostgreSQL/PostGIS Database

```bash
# Install PostgreSQL with PostGIS (if not already installed)
brew install postgresql postgis

# Start PostgreSQL
brew services start postgresql

# Create database and enable PostGIS
createdb geospatial_catalog
psql geospatial_catalog -c "CREATE EXTENSION postgis;"
psql geospatial_catalog -c "CREATE EXTENSION postgis_topology;"
```

### 3. Configure Environment Variables

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```bash
# Database
DATABASE_URL=postgresql://localhost:5432/geospatial_catalog

# Data Storage
DATA_ROOT=/Users/soumyadiptadey/Developer/common_project/data_test

# Network Configuration
API_HOST=127.0.0.1
INGESTION_SERVICE_PORT=8001
TILE_SERVICE_PORT=8002
QUERY_SERVICE_PORT=8003

# Service URLs
INGESTION_SERVICE_URL=http://127.0.0.1:8001
TILE_SERVICE_URL=http://127.0.0.1:8002
QUERY_SERVICE_URL=http://127.0.0.1:8003

# Security (LAN deployment)
ALLOWED_HOSTS=127.0.0.1,::1,192.168.1.0/24
BIND_ALL_INTERFACES=false

# GDAL Configuration
GDAL_DISABLE_READDIR_ON_OPEN=YES
GDAL_HTTP_MERGE_CONSECUTIVE_RANGES=YES

# Tile Cache
TILE_CACHE_SIZE=1000

# Upload Limits
MAX_UPLOAD_SIZE=5368709120

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_OUTPUT_PATH=/Users/soumyadiptadey/Developer/common_project/logs

# CesiumJS (offline)
CESIUM_BASE_URL=file:///Users/soumyadiptadey/Developer/common_project/src_new/clients/desktop_search/web_assets/vendor/cesium
```

### 4. Initialize Database Schema

```bash
# Run database migrations (if you have them)
# OR manually create tables based on your schema

# Example: Create raster_metadata table
psql geospatial_catalog << EOF
CREATE TABLE IF NOT EXISTS raster_metadata (
    raster_id VARCHAR(255) PRIMARY KEY,
    file_path TEXT NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    kind VARCHAR(50) NOT NULL,
    crs VARCHAR(50) NOT NULL,
    bbox GEOMETRY(POLYGON, 4326) NOT NULL,
    resolution_x DOUBLE PRECISION NOT NULL,
    resolution_y DOUBLE PRECISION NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    upload_date TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE INDEX idx_raster_bbox ON raster_metadata USING GIST(bbox);
EOF
```

---

## Running the System

### Option 1: Run All Services (Recommended for Development)

Open **4 separate terminal windows** and run each service:

#### Terminal 1: Ingestion Service (Server 1)

```bash
cd /Users/soumyadiptadey/Developer/common_project
conda activate geospatial-services
source .env

# Run ingestion service
uvicorn src_new.services.ingestion.service:app \
  --host $API_HOST \
  --port $INGESTION_SERVICE_PORT \
  --reload
```

#### Terminal 2: Tile Service (Server 1)

```bash
cd /Users/soumyadiptadey/Developer/common_project
conda activate geospatial-services
source .env

# Run tile service
uvicorn src_new.services.tile_serving.service:app \
  --host $API_HOST \
  --port $TILE_SERVICE_PORT \
  --reload
```

#### Terminal 3: Query Service (Server 2)

```bash
cd /Users/soumyadiptadey/Developer/common_project
conda activate geospatial-services
source .env

# Run query service
uvicorn src_new.services.query.service:app \
  --host $API_HOST \
  --port $QUERY_SERVICE_PORT \
  --reload
```

#### Terminal 4: Desktop Search Client

```bash
cd /Users/soumyadiptadey/Developer/common_project
conda activate geospatial-services
source .env

# Run search client
python -m src_new.clients.desktop_search.main
```

#### Terminal 5 (Optional): Desktop Ingestion Client

```bash
cd /Users/soumyadiptadey/Developer/common_project
conda activate geospatial-services
source .env

# Run ingestion client
python -m src_new.clients.desktop_ingestion.main
```

---

### Option 2: Use Deployment Scripts

The project includes shell scripts for easier deployment:

#### Start Server 1 (Ingestion + Tile Services)

```bash
cd /Users/soumyadiptadey/Developer/common_project
chmod +x src_new/scripts/deploy_server1.sh
./src_new/scripts/deploy_server1.sh
```

This starts both ingestion and tile services in the background.

#### Start Server 2 (Query Service)

```bash
cd /Users/soumyadiptadey/Developer/common_project
chmod +x src_new/scripts/deploy_server2.sh
./src_new/scripts/deploy_server2.sh
```

#### Start Individual Services

```bash
# Make scripts executable
chmod +x src_new/scripts/*.sh

# Start ingestion service
./src_new/scripts/start_ingestion_service.sh

# Start tile service
./src_new/scripts/start_tile_service.sh

# Start query service
./src_new/scripts/start_query_service.sh

# Start search client
./src_new/scripts/start_search_client.sh

# Start ingestion client
./src_new/scripts/start_ingestion_client.sh
```

---

## Verifying the System

### 1. Check Service Health

```bash
# Ingestion Service
curl http://127.0.0.1:8001/health

# Tile Service
curl http://127.0.0.1:8002/health

# Query Service
curl http://127.0.0.1:8003/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "ingestion_service",
  "timestamp": "2024-05-12T12:00:00Z"
}
```

### 2. Test Upload (via API)

```bash
# Upload a test raster
curl -X POST http://127.0.0.1:8001/upload \
  -F "file=@/Users/soumyadiptadey/Developer/common_project/data_test/dem.tif" \
  -F "metadata={\"description\":\"Test DEM\"}"
```

### 3. Test Query (via API)

```bash
# Query by point
curl -X POST http://127.0.0.1:8003/query/point \
  -H "Content-Type: application/json" \
  -d '{"lon": 72.5, "lat": 18.5}'

# Query by bounding box
curl -X POST http://127.0.0.1:8003/query/bbox \
  -H "Content-Type: application/json" \
  -d '{
    "min_lon": 72.0,
    "min_lat": 18.0,
    "max_lon": 73.0,
    "max_lat": 19.0
  }'
```

### 4. Test Tile Serving

```bash
# Get a tile (z/x/y format)
curl http://127.0.0.1:8002/tiles/10/512/384.png?raster_id=<your-raster-id> \
  --output test_tile.png

# Get preview
curl http://127.0.0.1:8002/preview/<your-raster-id> \
  --output preview.png
```

---

## Running Tests

### Run All Tests

```bash
cd /Users/soumyadiptadey/Developer/common_project
conda activate geospatial-services

# Run full test suite
pytest src_new/tests/ -v --tb=short

# Run with coverage
pytest src_new/tests/ --cov=src_new --cov-report=html
```

### Run Specific Test Suites

```bash
# Unit tests only
pytest src_new/tests/unit/ -v

# Integration tests only
pytest src_new/tests/integration/ -v

# End-to-end tests
pytest src_new/tests/e2e/ -v

# Specific test file
pytest src_new/tests/unit/test_models.py -v

# Specific test function
pytest src_new/tests/unit/test_models.py::TestBoundingBox::test_valid_bounding_box -v
```

---

## Troubleshooting

### Issue: Services won't start

**Check logs:**
```bash
tail -f /Users/soumyadiptadey/Developer/common_project/logs/ingestion_service.log
tail -f /Users/soumyadiptadey/Developer/common_project/logs/tile_service.log
tail -f /Users/soumyadiptadey/Developer/common_project/logs/query_service.log
```

**Check if ports are already in use:**
```bash
lsof -i :8001  # Ingestion service
lsof -i :8002  # Tile service
lsof -i :8003  # Query service
```

**Kill processes on ports:**
```bash
kill -9 $(lsof -t -i:8001)
kill -9 $(lsof -t -i:8002)
kill -9 $(lsof -t -i:8003)
```

### Issue: Database connection errors

**Check PostgreSQL is running:**
```bash
brew services list | grep postgresql
```

**Test database connection:**
```bash
psql geospatial_catalog -c "SELECT PostGIS_Version();"
```

### Issue: Import errors

**Ensure you're in the project root:**
```bash
cd /Users/soumyadiptadey/Developer/common_project
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

**Verify environment:**
```bash
conda activate geospatial-services
python -c "import src_new; print(src_new.__file__)"
```

### Issue: GDAL errors

**Check GDAL installation:**
```bash
gdalinfo --version
python -c "from osgeo import gdal; print(gdal.__version__)"
```

**Set GDAL environment variables:**
```bash
export GDAL_DATA=$(gdal-config --datadir)
export PROJ_LIB=/opt/homebrew/share/proj  # or your conda env path
```

---

## Stopping Services

### If running in foreground (Ctrl+C in each terminal)

Press `Ctrl+C` in each terminal window.

### If running in background

```bash
# Find PIDs
ps aux | grep uvicorn

# Kill specific service
kill <PID>

# Or kill all uvicorn processes
pkill -f uvicorn
```

---

## Next Steps

1. **Read the documentation:**
   - `src_new/docs/ARCHITECTURE.md` - System architecture
   - `src_new/docs/API_REFERENCE.md` - API endpoints
   - `src_new/docs/DEPLOYMENT.md` - Production deployment
   - `src_new/docs/MIGRATION_GUIDE.md` - Migrating from old src/

2. **Explore the codebase:**
   - `src_new/shared/` - Shared models and utilities
   - `src_new/services/` - Backend microservices
   - `src_new/clients/` - Desktop applications

3. **Customize configuration:**
   - Edit `.env` for your environment
   - Adjust `src_new/shared/config.py` for advanced settings

4. **Deploy to production:**
   - Follow `src_new/docs/DEPLOYMENT.md`
   - Set up proper LAN security with `ALLOWED_HOSTS`
   - Configure log rotation and monitoring

---

## Quick Reference

### Service URLs

- **Ingestion Service**: http://127.0.0.1:8001
  - Swagger docs: http://127.0.0.1:8001/docs
- **Tile Service**: http://127.0.0.1:8002
  - Swagger docs: http://127.0.0.1:8002/docs
- **Query Service**: http://127.0.0.1:8003
  - Swagger docs: http://127.0.0.1:8003/docs

### Key Directories

- **Services**: `src_new/services/`
- **Clients**: `src_new/clients/`
- **Tests**: `src_new/tests/`
- **Docs**: `src_new/docs/`
- **Scripts**: `src_new/scripts/`
- **Logs**: `/Users/soumyadiptadey/Developer/common_project/logs/`
- **Data**: `/Users/soumyadiptadey/Developer/common_project/data_test/`

### Useful Commands

```bash
# Activate environment
conda activate geospatial-services

# Run tests
pytest src_new/tests/ -v

# Check service health
curl http://127.0.0.1:8001/health

# View logs
tail -f logs/*.log

# Stop all services
pkill -f uvicorn
```

---

## Support

For issues or questions:
1. Check the logs in `/Users/soumyadiptadey/Developer/common_project/logs/`
2. Review documentation in `src_new/docs/`
3. Run tests to verify system integrity: `pytest src_new/tests/ -v`
