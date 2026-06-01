# resGIS - Quick Start & Deployment Guide

Welcome to the official deployment guide for **resGIS**, developed by **NTRO, Gov. of India**. This document outlines how to initialize the backend services and launch the desktop workspaces.

---

## 🚀 Service & Client Orchestration

### Step 1: Start Backend Services
Launch the FastAPI microservices (Ingestion, Tile Serving, Query Services) in the background:
```bash
cd /Users/soumyadiptadey/Developer/common_project
./start_services.sh
```
This script initializes:
- **Ingestion Service**: Port 8001 (Handles raster ingest and tiling optimization)
- **Tile Serving Service**: Port 8002 (XYZ and terrain tile rendering)
- **Query Service**: Port 8003 (Catalog search and metadata queries)

*Allow 5 to 10 seconds for databases and services to initialize fully.*

---

### Step 2: Launch Workspaces

#### Option A: Data Ingestion Workspace
Use this tool to ingest new geospatial raster layers (GeoTIFFs, DEMs) into the local repository:
```bash
./start_ingestion_client.sh
```

#### Option B: Search & Visualization Workspace
The primary application interface for map visualization, spatial analysis, and project planning:
```bash
./start_search_client.sh
```

---

## 📋 Management Scripts

1. **`start_services.sh`**: Start or restart all background microservices.
2. **`start_ingestion_client.sh`**: Launch the ingestion client to process new spatial data.
3. **`start_search_client.sh`**: Launch the interactive 3D GIS workspace (resGIS).

---

## 🛠️ Manual CLI Operations (Optional)

If automated scripts are bypassed, run services individually:

### Backend Microservices
Ensure the Conda environment `offline-3d-gis` is active before running:

1. **Ingestion Service**:
   ```bash
   uvicorn src_new.services.ingestion.service:app --host 127.0.0.1 --port 8001 --reload
   ```
2. **Tile Service**:
   ```bash
   uvicorn src_new.services.tile_serving.service:app --host 127.0.0.1 --port 8002 --reload
   ```
3. **Query Service**:
   ```bash
   uvicorn src_new.services.query.service:app --host 127.0.0.1 --port 8003 --reload
   ```

### Desktop Applications
1. **Ingestion Client**:
   ```bash
   python -m src_new.clients.desktop_ingestion.main
   ```
2. **Search Client**:
   ```bash
   python -m src_new.clients.desktop_search.main
   ```

---

## 🎯 Primary Workflow

1. **Service Initialization**: Spin up local microservices via `./start_services.sh`.
2. **Data Processing**: Open `./start_ingestion_client.sh` to upload files, optimize projections, and register datasets.
3. **Spatial Analysis**: Launch `./start_search_client.sh` to explore the 3D globe, calculate distances/areas, construct overlays, annotate findings, and save project sessions.
4. **Data Export**: Export your maps and annotations to GeoPackage (GPKG) files for full cross-compatibility with other desktop GIS software.
