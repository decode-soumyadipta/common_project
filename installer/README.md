# Offline 3D GIS Desktop — Windows Installer

## What this produces

A single `.exe` installer built with **NSIS** + **conda-pack** that:

- Bundles the entire Python environment (Python 3.11, Qt5, GDAL, rasterio, pyproj, scipy, shapely, FastAPI, TiTiler) — **no internet required on the target machine**
- Installs to `C:\Program Files\OfflineGIS\` with a desktop shortcut and Start Menu entry
- Registers in Windows Add/Remove Programs for clean uninstall
- Configures NVIDIA/AMD GPU acceleration automatically via environment variables

## Prerequisites (build machine only — Windows with conda)

```powershell
# Install build tools into base conda env
conda install -c conda-forge conda-pack nsis
```

NSIS must also be on PATH. If `makensis` is not found after conda install, add the NSIS bin directory to PATH manually.

## Build

```powershell
cd installer
.\build_windows_installer.ps1
# Output: dist\OfflineGIS_Setup_0.1.0.exe
```

Options:
```powershell
.\build_windows_installer.ps1 -CondaEnvName offline-3d-gis -AppVersion 1.2.0 -OutDir dist
```

## What happens during install

1. Extracts the conda-pack `.tar.gz` archive into `<InstallDir>\env\`
2. Runs `conda-unpack.exe` to fix all hardcoded paths in the environment
3. Installs the app wheel via pip (offline, from bundled `wheels\` directory)
4. Creates launcher `.cmd` with GPU environment variables pre-set
5. Creates desktop + Start Menu shortcuts

## GPU configuration

The launcher sets these automatically:

| Variable | Value | Purpose |
|---|---|---|
| `NvOptimusEnablement` | `0x00000001` | Force NVIDIA discrete GPU (Optimus laptops) |
| `AmdPowerXpressRequestHighPerformance` | `1` | Force AMD discrete GPU |
| `QT_OPENGL` | `angle` | Use ANGLE (D3D11) backend for Qt |
| `QT_ANGLE_PLATFORM` | `d3d11` | Direct3D 11 — best WebGL path on Windows |
| `QTWEBENGINE_DISABLE_SANDBOX` | `1` | Required for offline/restricted environments |

Chromium flags set at runtime:
- `--use-gl=angle --use-angle=d3d11` — hardware WebGL via D3D11
- `--ignore-gpu-blocklist` — bypass Qt's conservative GPU denylist
- `--enable-gpu-rasterization` — GPU-accelerated 2D canvas
- `--enable-zero-copy` — zero-copy texture uploads (NVIDIA)

## Offline data setup (post-install)

After installing, copy your data files:

```
<InstallDir>\
  env\                    ← Python environment (auto-created)
  offline_gis.exe.cmd     ← Launcher
  data\                   ← Put your GeoTIFF / COG files here (optional)
```

Basemap tiles (optional, for offline background map):
```powershell
# Run from the install directory
.\env\python.exe -m offline_gis_app.cli download-basemap --region asia
```

## Uninstall

Use Windows Add/Remove Programs, or run `<InstallDir>\Uninstall.exe`.

## Troubleshooting

**App doesn't start / blank window:**
- Check `%USERPROFILE%\OfflineGIS\client_startup_trace.log`
- Install [Microsoft Visual C++ 2015-2022 Redistributable (x64)](https://aka.ms/vs/17/release/vc_redist.x64.exe)

**No 3D map / WebGL error:**
- Right-click desktop → Display settings → Graphics → set `offline_gis.exe.cmd` to High Performance
- Update NVIDIA drivers to latest Game Ready or Studio driver

**Slow performance:**
- Ensure NVIDIA Control Panel → Manage 3D Settings → Power management mode = "Prefer maximum performance"
