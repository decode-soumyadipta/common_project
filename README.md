# Offline 3D GIS System

Complete offline 3D GIS system with microservices architecture and full-featured desktop clients.

## Quick Start

```bash
# 1. Start all backend services
./start_services.sh

# 2. Start desktop client (choose one)
./start_ingestion_client.sh   # Upload raster data
./start_search_client.sh       # Search & visualize (full 3D GIS)
```

See **[START_HERE.md](START_HERE.md)** for complete documentation.

## Features

- ✅ 3 Backend Services (Ingestion, Tile, Query)
- ✅ Desktop Ingestion Client (upload rasters)
- ✅ Desktop Search Client (full-featured 3D GIS)
  - CesiumJS 3D Globe
  - Layer Comparator & Compositor
  - Measurement Tools
  - Annotation Tools
  - Search & Visualization

## Architecture

- **Backend**: FastAPI microservices (Python)
- **Frontend**: Qt/PyQt5 desktop clients
- **3D Visualization**: CesiumJS
- **Database**: PostgreSQL + PostGIS
- **Geospatial**: GDAL, Rasterio, TiTiler

## Requirements

- Python 3.11+
- PostgreSQL 14+ with PostGIS
- Conda environment: `offline-3d-gis`
- PyQt5 + PyQtWebEngine

## Documentation

- **[START_HERE.md](START_HERE.md)** - Complete guide with all commands
