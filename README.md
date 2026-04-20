# Offline 3D GIS Desktop App

Modular offline-first GIS system with:
- **FastAPI backend** for ingestion, search, and DEM profile APIs.
- **PySide6 desktop shell** with QWebEngine and QWebChannel bridge.
- **PostgreSQL/PostGIS metadata catalog by default** (SQLite still supported via `DATABASE_URL` override for local dev/tests).
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

Pre-download full-world satellite XYZ tiles for offline globe rendering (recommended before first run):

```bash
bash scripts/setup_global_basemap.sh 7
```

To sharpen only Asia without downloading the whole world again:

```bash
bash scripts/setup_global_basemap.sh --asia 10
```

Optional (for RGB overlays on real 3D terrain offline): install a local quantized-mesh terrain pack:

```bash
bash scripts/setup_offline_terrain_pack.sh /path/to/local/terrain-pack
```

Or auto-download an Asia terrain-rgb pack (offline runtime after download):

```bash
bash scripts/setup_offline_terrain_pack.sh --asia 8
```

Full world terrain-rgb preset is also available (large download):

```bash
bash scripts/setup_offline_terrain_pack.sh --world 7
```

Notes:
- The argument is max zoom level for world tile cache (default `7` if omitted).
- `--asia` augments the existing globe cache with deeper zoom tiles only over Asia, which is the practical path for very high resolution overlays.
- Higher zoom gives sharper offline imagery but uses more disk space and download time.
- Runtime globe now uses local tiles only (`web_assets/basemap/xyz`) and does not depend on network access.
- If `web_assets/basemap/terrain/layer.json` exists, RGB in 3D mode uses that offline quantized-mesh terrain.
- If `web_assets/basemap/terrain-rgb/metadata.json` exists, RGB in 3D mode uses that offline terrain-rgb pack.
- Preview and load actions drape the uploaded raster over the offline 3D globe terrain in `3D Terrain Scene` mode by default.
- If local offline tiles are missing, the app falls back to built-in NaturalEarth texture.

```bash
python -m offline_gis_app.cli desktop
```

For split local workflow (two terminals):

```bash
python -m offline_gis_app.cli desktop-server
```

```bash
python -m offline_gis_app.cli desktop-client
```

`desktop-server` now auto-starts local API on `127.0.0.1:8000` when needed.
If API is still unavailable, the UI logs a concise retry message instead of a full traceback.

For secure LAN deployment (recommended for very large raster/tile datasets):
- Run `desktop-server` on the data host that has direct access to shared storage.
- Point clients to that server using `SERVER_API_BASE_URL` and run `desktop-client`.
- Keep ingest path-based (no HTTP file uploads) so terabyte-scale sources stay in place and are cataloged by reference.

You can still run API manually when required:

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
- catalog refresh + add-layer,
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

- `DATABASE_URL` (default: `postgresql+psycopg://localhost/offline_gis`)
- `DATA_ROOT` (default: current project folder)
- `API_HOST` (default: `127.0.0.1`)
- `API_PORT` (default: `8000`)
- `DEPLOYMENT_TOPOLOGY` (default: `same-machine`)
- `SERVER_API_BASE_URL` (default: empty; set in split-LAN mode)
- `TITILER_BASE_URL` (default: `http://127.0.0.1:8081`)
- `DESKTOP_LOG_LEVEL` (default: `INFO`, set `DEBUG` for verbose troubleshooting)

For PostgreSQL/PostGIS, set:

```bash
export DATABASE_URL="postgresql+psycopg://user:password@127.0.0.1:5432/offline_gis"
```
