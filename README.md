# Offline 3D GIS Desktop App

Modular offline-first GIS system with:
- **FastAPI backend** for ingestion, search, and DEM profile APIs.
- **PySide6 desktop shell** with QWebEngine and QWebChannel bridge.
- **PostgreSQL/PostGIS-compatible metadata catalog** (SQLite default for local dev/tests).
- **Small, single-purpose Python modules** for easier maintenance and debugging.

## 1. Conda Environment (recommended)

This project uses **Python 3.11** for broad compatibility with PySide6, rasterio, and modern FastAPI stacks.

```bash
conda env create -f environment.yml
conda activate offline-3d-gis
```

If you already created the env before this fix, update it:

```bash
conda env update -f environment.yml --prune
```

## 2. Run backend API

```bash
python -m offline_gis_app.cli api
```

Open: `http://127.0.0.1:8000/docs`

## 3. Run desktop app

First install local Cesium assets (required once):

```bash
bash scripts/setup_cesium_assets.sh
```

Install packaged offline global basemap (recommended, less blur):

```bash
bash scripts/setup_global_basemap.sh
```

```bash
python -m offline_gis_app.cli desktop
```

Run the API first when using upload/catalog/profile controls:

```bash
python -m offline_gis_app.cli api
```

For raster imagery/DEM tiles, run local TiTiler in another terminal:

```bash
bash scripts/run_titiler_local.sh
```

If TiTiler is not running, the desktop app now auto-starts it when you load a layer.

Desktop panel now includes:
- file browse + raster register/load,
- catalog refresh, add-layer, fly-to,
- brightness/contrast, pitch, rotate controls,
- click markers, two-point distance update,
- annotation at clicked point,
- DEM profile extraction using last two clicks.

Desktop now emits **debug/info/warn/error logs** to terminal for:
- file selection/register/load actions,
- JS map events and layer load requests,
- tile provider errors,
- distance/profile operations.

Quick check for the desktop dependency:

```bash
python -c "from PySide6.QtWebEngineWidgets import QWebEngineView; print('QtWebEngine OK')"
```

## 4. Test

```bash
pytest -q
```

## 5. Deployment path choice

Use **path-based data registration** for raster files (`/ingest/register` accepts local file paths).  
This is the most deployment-friendly approach for secure air-gapped environments because:
- no large file copy through HTTP upload paths,
- avoids duplicate storage,
- keeps provenance and auditability of source rasters.

## 6. Environment variables

Defaults are in `offline_gis_app/config/settings.py`.

- `DATABASE_URL` (default: `sqlite:///./offline_gis.db`)
- `DATA_ROOT` (default: current project folder)
- `API_HOST` (default: `127.0.0.1`)
- `API_PORT` (default: `8000`)
- `TITILER_BASE_URL` (default: `http://127.0.0.1:8081`)
- `DESKTOP_LOG_LEVEL` (default: `INFO`, set `DEBUG` for verbose troubleshooting)

For PostgreSQL/PostGIS, set:

```bash
export DATABASE_URL="postgresql+psycopg://user:password@127.0.0.1:5432/offline_gis"
```
