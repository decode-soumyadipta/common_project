# Windows Dual-App Packaging

This folder builds two separate desktop apps that share one local DB/runtime folder:

- `OfflineGIS-Server.exe`
- `OfflineGIS-Client.exe`

## Build

From repo root:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/build_dual_apps.ps1 -CondaEnvName offline-3d-gis -Clean
```

If Inno Setup 6 is installed, the script also creates:

- `dist/installer/OfflineGIS-Dual-Setup.exe`

To skip installer compilation:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/build_dual_apps.ps1 -CondaEnvName offline-3d-gis -SkipInstaller
```

## Runtime defaults (target machine)

- `OFFLINE_GIS_HOME = %LOCALAPPDATA%/OfflineGIS`
- `DATABASE_URL = sqlite:///%LOCALAPPDATA%/OfflineGIS/offline_gis.db`
- `DATA_ROOT = %LOCALAPPDATA%/OfflineGIS/data`
- `SERVER_API_BASE_URL = http://127.0.0.1:8000` (client default)

These values are applied by standalone launchers when not explicitly overridden.
