@echo off
setlocal

set "PROJECT_DIR=%~dp0.."

echo Starting Desktop Ingestion Client...
echo Use this to upload raster files to the system.
echo.

cd /d "%PROJECT_DIR%"

for /f "delims=" %%i in ('conda info --base 2^>nul') do set "CONDA_BASE=%%i"
if not defined CONDA_BASE (
  echo Conda not found in PATH. Please open Anaconda Prompt and run this script again.
  exit /b 1
)

call "%CONDA_BASE%\Scripts\activate.bat" offline-3d-gis
python -m src_new.clients.desktop_ingestion
