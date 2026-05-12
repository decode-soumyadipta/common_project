# Offline 3D GIS - Quick Start Guide

## 🚀 How to Run Everything

### Step 1: Start Backend Services
```bash
cd /Users/soumyadiptadey/Developer/common_project
./start_services.sh
```
This opens 3 terminal tabs with:
- Ingestion Service (Port 8001)
- Tile Service (Port 8002)
- Query Service (Port 8003)

**Wait 5-10 seconds** for services to start.

---

### Step 2: Start Desktop Clients

#### Option A: Upload Data (Ingestion Client)
```bash
./start_ingestion_client.sh
```
Use this to upload raster files.

#### Option B: Search & Visualize (Search Client)
```bash
./start_search_client.sh
```
Full-featured 3D GIS with:
- ✅ CesiumJS 3D Globe
- ✅ All Toolbars (Display, Measurement, Visualization, Navigation, File)
- ✅ Layer Comparator & Compositor
- ✅ Measurement Tools (Distance, Elevation, Volume)
- ✅ Annotation Tools (Point, Line, Polygon, Text)
- ✅ Search & Visualization

---

## 📋 Scripts Created

1. **`start_services.sh`** - Starts all 3 backend services
2. **`start_ingestion_client.sh`** - Starts Desktop Ingestion Client
3. **`start_search_client.sh`** - Starts Desktop Search Client (full features)

---

## 🔍 Manual Commands (if scripts don't work)

### Start Services Manually (3 separate terminals)

**Terminal 1 - Ingestion Service:**
```bash
cd /Users/soumyadiptadey/Developer/common_project
conda activate offline-3d-gis
uvicorn src_new.services.ingestion.service:app --host 127.0.0.1 --port 8001 --reload
```

**Terminal 2 - Tile Service:**
```bash
cd /Users/soumyadiptadey/Developer/common_project
conda activate offline-3d-gis
uvicorn src_new.services.tile_serving.service:app --host 127.0.0.1 --port 8002 --reload
```

**Terminal 3 - Query Service:**
```bash
cd /Users/soumyadiptadey/Developer/common_project
conda activate offline-3d-gis
uvicorn src_new.services.query.service:app --host 127.0.0.1 --port 8003 --reload
```

### Start Clients Manually

**Desktop Ingestion Client:**
```bash
cd /Users/soumyadiptadey/Developer/common_project
conda activate offline-3d-gis
python -m src_new.clients.desktop_ingestion.main
```

**Desktop Search Client:**
```bash
cd /Users/soumyadiptadey/Developer/common_project
conda activate offline-3d-gis
python -m src_new.clients.desktop_search.main
```

---

## ✅ Health Checks

Check if services are running:
```bash
curl http://127.0.0.1:8001/health  # Ingestion
curl http://127.0.0.1:8002/health  # Tile
curl http://127.0.0.1:8003/health  # Query
```

---

## 🎯 Typical Workflow

1. **Start services**: `./start_services.sh`
2. **Upload data**: `./start_ingestion_client.sh`
   - Browse and select raster files
   - Click Upload
3. **Search & visualize**: `./start_search_client.sh`
   - Use search panel to query by coordinates
   - Use toolbars for measurements, annotations, etc.
   - Explore the 3D globe!

---

## 🛠️ Troubleshooting

### Port Already in Use
```bash
# Find what's using the port
lsof -i :8001  # or :8002, :8003

# Kill the process
kill -9 <PID>
```

### Services Won't Start
- Check PostgreSQL is running: `pg_ctl status`
- Check conda environment: `conda activate offline-3d-gis`

### Desktop Client Won't Start
- Ensure all 3 services are running first
- Check for missing dependencies: `pip install python-multipart Pillow pyproj`

---

## 📁 Project Structure

```
/Users/soumyadiptadey/Developer/common_project/
├── start_services.sh              # Start all backend services
├── start_ingestion_client.sh      # Start ingestion client
├── start_search_client.sh         # Start search client (full features)
├── src_new/                       # New microservices implementation
│   ├── services/                  # Backend services
│   │   ├── ingestion/             # Port 8001
│   │   ├── tile_serving/          # Port 8002
│   │   └── query/                 # Port 8003
│   └── clients/                   # Desktop clients
│       ├── desktop_ingestion/     # Upload client
│       └── desktop_search/        # Search client (FULL FEATURES)
└── data_test/                     # Test raster files
```

---

## 🎉 What's Working

✅ All 3 backend services (Ingestion, Tile, Query)
✅ Desktop Ingestion Client
✅ Desktop Search Client with **FULL FEATURES**:
  - Complete CesiumJS 3D globe
  - All toolbars and tools
  - Layer Comparator & Compositor
  - Measurement & Annotation tools
  - Search & Visualization

---

## 📝 Notes

- **Desktop Search Client** has the complete implementation from old `src/client_desktop/`
- All ~10,000+ lines of code copied with full features
- 100% feature parity with original desktop client
- Uses new microservices architecture (3 separate backend services)

---

That's it! Run `./start_services.sh` and then `./start_search_client.sh` to get started! 🚀
