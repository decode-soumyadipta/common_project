# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


ROOT = Path(SPECPATH).resolve().parents[1]
SRC = ROOT / "src"

datas = [
    (
        str(SRC / "offline_gis_app" / "desktop" / "web_assets"),
        "offline_gis_app/desktop/web_assets",
    ),
    (
        str(SRC / "offline_gis_app" / "desktop" / "icons"),
        "offline_gis_app/desktop/icons",
    ),
]

hiddenimports = [
    "qtpy",
    "qtpy.QtCore",
    "qtpy.QtGui",
    "qtpy.QtWidgets",
    "qtpy.QtWebEngineWidgets",
    "qtpy.QtWebChannel",
    "shapely",
    "rasterio",
    "titiler.application",
    "titiler.application.main",
    "titiler.core",
    "titiler.core.factory",
    "uvicorn",
    "uvicorn.lifespan",
]


a = Analysis(
    [str(SRC / "offline_gis_app" / "desktop" / "apps" / "server_app.py")],
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
    [],
    exclude_binaries=True,
    name="OfflineGIS-Server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="OfflineGIS-Server",
)
