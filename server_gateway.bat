@echo off
set PYTHONPATH=%CD%\src
echo Starting Distributed GIS Gateway (Server A)...
python -m server_gateway.api.app
pause
