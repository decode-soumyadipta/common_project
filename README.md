# resGIS

resGIS is a secure, high-performance, and completely offline 3D Geographic Information System (GIS) application suite developed by NTRO, Gov. of India. The system provides robust spatial data ingestion, tile serving, search query capabilities, and comprehensive 3D globe visualization.

## Quick Start

### 1. Start Backend Services
Start the query, tile, and ingestion microservices:
```bash
./start_services.sh
```

### 2. Launch Desktop Clients
- **Data Ingestion Client**: Launch the client to ingest and prepare raster geospatial datasets:
  ```bash
  ./start_ingestion_client.sh
  ```
- **Main GIS Client (Search & Visualization)**: Launch the main workspace to visualize, query, measure, and annotate GIS data:
  ```bash
  ./start_search_client.sh
  ```

For detailed deployment instructions and workflow guidelines, please refer to **[START_HERE.md](START_HERE.md)**.

## Core Features

- **Microservices Architecture**:
  - Ingestion Service (Dataset registry and optimization)
  - Tile Service (Efficient, localized XYZ raster tiling)
  - Query Service (Spatial querying and metadata retrieval)
- **resGIS Desktop Workspaces**:
  - CesiumJS-powered offline 3D globe visualization
  - Side-by-side Layer Comparator & Multi-layer Compositor
  - Precision Geodetic Measurement Tools (distance, area, shadow height, elevation profile)
  - Interactive Map Annotations (points, lines, polygons, custom icons, text labels)
  - GeoPackage Export (for full cross-software interoperability with standard GIS platforms)
  - Full-state serialization (`state.json`) for session recovery

## Tech Stack
- **Backend Services**: Python, FastAPI, GDAL, Rasterio, TiTiler
- **Desktop Interfaces**: Qt/PyQt5, PyQtWebEngine
- **3D Visualization Engine**: CesiumJS
- **Data Store**: PostgreSQL + PostGIS / SQLite
