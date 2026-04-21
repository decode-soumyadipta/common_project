from __future__ import annotations

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


ROOT = Path(SPECPATH).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Bundle frontend assets and migrations required at runtime.
datas = collect_data_files(
    "offline_gis_app",
    includes=[
        "client_frontend/web_assets/**/*",
        "client_frontend/icons/*",
        "db/migrations/*",
    ],
)

hiddenimports = []
hiddenimports += collect_submodules("qtpy")


a = Analysis(
    [str(SRC / "offline_gis_app" / "client_backend" / "desktop" / "apps" / "client_app.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    exclude_binaries=False,
    name="client",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)
