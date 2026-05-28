@echo off
setlocal

set "PROJECT_DIR=%~dp0.."

echo Starting Offline 3D GIS Backend Services...
echo.
echo This will open 3 terminals for:
echo   1. Ingestion Service (Port 8001)
echo   2. Tile Service (Port 8002)
echo   3. Query Service (Port 8003)
echo.

for /f "delims=" %%i in ('conda info --base 2^>nul') do set "CONDA_BASE=%%i"
if not defined CONDA_BASE (
  echo Conda not found in PATH. Please open Anaconda Prompt and run this script again.
  exit /b 1
)

set "CONDA_ACT=call \"%CONDA_BASE%\Scripts\activate.bat\" offline-3d-gis"

start "Ingestion Service" cmd /k "cd /d %PROJECT_DIR% && %CONDA_ACT% && echo Starting Ingestion Service on port 8001... && uvicorn src_new.services.ingestion.service:app --host 127.0.0.1 --port 8001 --reload"
start "Tile Service" cmd /k "cd /d %PROJECT_DIR% && %CONDA_ACT% && echo Starting Tile Service on port 8002... && uvicorn src_new.services.tile_serving.service:app --host 127.0.0.1 --port 8002 --reload"
start "Query Service" cmd /k "cd /d %PROJECT_DIR% && %CONDA_ACT% && echo Starting Query Service on port 8003... && uvicorn src_new.services.query.service:app --host 127.0.0.1 --port 8003 --reload"

echo.
echo Services started. Wait a few seconds, then run:
echo   windows\start_ingestion_client.bat
echo   windows\start_search_client.bat
