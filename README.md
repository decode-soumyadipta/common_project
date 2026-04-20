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

This environment now installs Qt packages from conda-forge directly (`pyside6` + `pyside6-addons`) for better Windows DLL compatibility.

If you already created the env before this fix, update it:

```bash
conda env update -f environment.yml --prune
```

### Windows notes (conda)

If desktop startup shows a Qt/WebEngine DLL load error, run:

```bash
conda install -c conda-forge pyside6 pyside6-addons
# if needed on your channel build:
conda install -c conda-forge pyside6 pyside6-webengine
```

If it still fails, install the **Microsoft Visual C++ 2015-2022 Redistributable (x64)** and recreate the environment.

## 1b. Python venv option

If you use `venv` instead of conda:

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1

pip install --upgrade pip
pip install -e .[desktop,geo,dev]
```

The `desktop` extra includes `PySide6` and Qt addons needed for `QtWebEngine`.

## 1c. One-command Windows bootstrap (auto-detect conda/venv)

From PowerShell at repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows_desktop.ps1
```

What it does:
- auto-detects active environment type (`conda` or `venv`),
- installs Windows-safe Qt WebEngine dependencies,
- validates `QWebEngineView` import,
- prints the next command to start the desktop client.

Optional flags:

```powershell
# Force conda mode
powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows_desktop.ps1 -Mode conda

# Force venv mode and create .venv if missing
powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows_desktop.ps1 -Mode venv -CreateVenv
```

## 1d. Transfer full conda env (Windows to Windows)

Cross-OS transfer is not supported (macOS env cannot be activated on Windows), but Windows-to-Windows transfer is supported.

On source Windows machine:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\pack_windows_conda_env.ps1 -EnvName offline-3d-gis -OutputPath dist\offline-3d-gis-win64.zip
```

On target Windows machine:

```powershell
# unzip to C:\offline-3d-gis
C:\offline-3d-gis\Scripts\activate
conda-unpack
python -m offline_gis_app.cli desktop-client
```

## 1e. Build Windows installer (.exe)

Build on a Windows machine (recommended inside a conda env):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows_installer.ps1
```

This script will:
- build a wheel of this project,
- place it in installer payload,
- run `constructor` to generate a Windows installer exe.

Output folder:

```text
dist\windows-installer
```

Installer config is in:

```text
installer/constructor/win-64
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
