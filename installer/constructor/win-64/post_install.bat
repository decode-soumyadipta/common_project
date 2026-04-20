@echo off
setlocal EnableExtensions EnableDelayedExpansion

echo [offline-3d-gis] Post-install started.

set "WHEEL_DIR=%PREFIX%\wheels"
if not exist "%WHEEL_DIR%" (
  echo [offline-3d-gis] ERROR: Wheel payload directory not found: %WHEEL_DIR%
  exit /b 1
)

set "WHEEL_FILE="
for %%F in ("%WHEEL_DIR%\offline_3d_gis_app-*.whl") do (
  if exist "%%~fF" (
    set "WHEEL_FILE=%%~fF"
    goto :wheel_found
  )
)
for %%F in ("%WHEEL_DIR%\offline_3d_gis-*.whl") do (
  if exist "%%~fF" (
    set "WHEEL_FILE=%%~fF"
    goto :wheel_found
  )
)
for %%F in ("%WHEEL_DIR%\offline*.whl") do (
  if exist "%%~fF" (
    set "WHEEL_FILE=%%~fF"
    goto :wheel_found
  )
)

echo [offline-3d-gis] ERROR: No project wheel found under %WHEEL_DIR%
exit /b 1

:wheel_found
echo [offline-3d-gis] Installing project wheel: %WHEEL_FILE%
"%PREFIX%\python.exe" -m pip install --no-deps "%WHEEL_FILE%"
if errorlevel 1 (
  echo [offline-3d-gis] ERROR: pip wheel install failed.
  exit /b 1
)

echo [offline-3d-gis] Verifying Qt WebEngine import.
"%PREFIX%\python.exe" -c "from PySide6.QtWebEngineWidgets import QWebEngineView; print('QtWebEngine OK')"
if errorlevel 1 (
  echo [offline-3d-gis] ERROR: Qt WebEngine verification failed.
  exit /b 1
)

echo [offline-3d-gis] Creating convenience launchers.
(
  echo @echo off
  echo "%~dp0python.exe" -m offline_gis_app.cli desktop-client %%*
) > "%PREFIX%\offline-gis-desktop-client.bat"

(
  echo @echo off
  echo "%~dp0python.exe" -m offline_gis_app.cli desktop-server %%*
) > "%PREFIX%\offline-gis-desktop-server.bat"

(
  echo @echo off
  echo "%~dp0python.exe" -m offline_gis_app.cli api %%*
) > "%PREFIX%\offline-gis-api.bat"

if exist "%PREFIX%\create_shortcuts.ps1" (
  echo [offline-3d-gis] Creating Windows shortcuts.
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PREFIX%\create_shortcuts.ps1" -InstallPrefix "%PREFIX%"
  if errorlevel 1 (
    echo [offline-3d-gis] WARNING: shortcut creation failed. Launchers are still available in %PREFIX%.
  )
) else (
  echo [offline-3d-gis] WARNING: create_shortcuts.ps1 not found; skipping shortcut creation.
)

echo [offline-3d-gis] Post-install complete.
exit /b 0
