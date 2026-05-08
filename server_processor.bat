@echo off
set PYTHONPATH=%CD%\src
echo Starting Distributed GIS Processor Worker (Server B)...
python -m server_processor.workers.ingest_worker
pause
