@echo off
set PYTHONPATH=%CD%\src
echo "Starting Ingestion Control Desktop Node..."
python -m client_desktop.apps.run_ingest
pause
