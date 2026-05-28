@echo off
setlocal

set "PROJECT_DIR=%~dp0.."

echo Starting Desktop Search Client...
echo Full-featured 3D GIS with:
echo   - CesiumJS 3D Globe
echo   - Layer Comparator and Compositor
echo   - Measurement Tools
echo   - Annotation Tools
echo   - Search and Visualization
echo.

cd /d "%PROJECT_DIR%"

for /f "delims=" %%i in ('conda info --base 2^>nul') do set "CONDA_BASE=%%i"
if not defined CONDA_BASE (
  echo Conda not found in PATH. Please open Anaconda Prompt and run this script again.
  exit /b 1
)

call "%CONDA_BASE%\Scripts\activate.bat" offline-3d-gis
python -m src_new.clients.desktop_search
