# Offline 3D GIS App

Offline-first desktop + API GIS stack for high-resolution raster workflows.

## Architecture

The codebase follows a strict four-domain split:

- `src/offline_gis_app/server_backend`: FastAPI routes, schemas, catalog query services.
- `src/offline_gis_app/server_ingestion`: ingestion queue, raster preparation, metadata extraction, measurement services.
- `src/offline_gis_app/client_backend`: desktop runtime, Qt bridge/orchestration, local API coordination.
- `src/offline_gis_app/client_frontend`: Cesium-based web assets and visualization modules.

## Offline Deployment Policy

This repository uses source + environment packaging for offline machines:

1. Package the repository as ZIP.
2. Package the conda environment with `conda-pack`.
3. Transfer both to offline target machines.
4. Unpack environment and run from source.

Windows EXE packaging is not part of the active deployment workflow.

## Environment Setup

Create the environment:

```powershell
conda env create -f environment.yml
conda activate offline-3d-gis
```

Install the project in editable mode (already included in environment.yml via pip extras):

```powershell
pip install -e .[desktop,dev]
```

## Run

Run the desktop client mode:

```powershell
python -m offline_gis_app.client_backend.desktop.apps.client_app
```

Run API-only server mode:

```powershell
python -m offline_gis_app.client_backend.desktop.apps.server_app --api-only
```

Run test suite:

```powershell
pytest
```

## Large Raster Handling Direction

The ingestion flow now starts from deterministic stages:

- source path validation
- raster kind detection
- COG preparation
- overview pyramiding
- metadata extraction
- catalog persistence
- tile URL publication

New service folders introduced for large-raster reliability:

- `server_ingestion/services/cog_service`
- `server_ingestion/services/pyramiding_service`
- `server_ingestion/services/streaming_service`
- `server_ingestion/services/ingestion_service`
- `server_ingestion/services/tiler_service`

These services are intended for multi-TB imagery and high-resolution DEM workflows in fully offline deployments.
