@echo off
set PYTHONPATH=%CD%\src
echo "Starting Search & Visualization Desktop Node..."
python -m client_desktop.apps.run_search
pause
