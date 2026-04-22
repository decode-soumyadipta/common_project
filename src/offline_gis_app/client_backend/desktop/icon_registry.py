from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import urlretrieve

from qtpy.QtCore import QSize, Qt
from qtpy.QtGui import QColor, QIcon, QPainter, QPixmap

try:
    from qtpy.QtSvg import QSvgRenderer
except Exception:  # pragma: no cover - QtSvg may not be available in some runtimes
    QSvgRenderer = None

ICON_DIR = Path(__file__).resolve().parents[2] / "client_frontend" / "icons"
DEFAULT_ICON_SIZE = 28

# Logical action key -> QGIS default theme SVG filename.
ICON_MANIFEST: dict[str, str] = {
    # Visualization tools
    "layer_compositor": "mActionAddLayer.svg",
    "comparator": "mActionMapIdentification.svg",
    "swipe_comparator": "mActionShowAllLayers.svg",
    # Measurement tools
    "measure_distance": "mActionMeasure.svg",
    "measure_area": "mActionMeasureArea.svg",
    "elevation_profile": "mActionOpenTable.svg",
    "volume": "mActionCalculateField.svg",
    "viewshed": "mActionIdentify.svg",
    "slope_aspect": "mActionOptions.svg",
    "clear_last": "mActionUndo.svg",
    "clear_all": "mActionDeleteSelected.svg",
    # Annotation tools
    "annotate_point": "mActionCapturePoint.svg",
    "annotate_line": "mActionCaptureLine.svg",
    "annotate_polygon": "mActionCapturePolygon.svg",
    "shadow_height": "mActionCaptureLine.svg",
    "edit_annotation": "mActionToggleEditing.svg",
    "delete_annotation": "mActionDeleteSelected.svg",
    "lock_annotation": "mActionToggleEditing.svg",
    "save_annotations": "mActionSharingExport.svg",
    # Navigation
    "pan": "mActionPan.svg",
    "zoom_in": "mActionZoomIn.svg",
    "zoom_out": "mActionZoomOut.svg",
    "zoom_extent": "mActionZoomFullExtent.svg",
    "zoom_layer": "mActionZoomToLayer.svg",
    "zoom_selection": "mActionZoomToSelected.svg",
    "identify": "mActionIdentify.svg",
    "north_arrow": "mActionScaleBar.svg",
    # Layers/data
    "open_raster": "mActionAddRasterLayer.svg",
    "open_dem": "mActionAddOgrLayer.svg",
    "open_vector": "mActionAddOgrLayer.svg",
    "layer_properties": "mActionOptions.svg",
    "layer_order": "mActionShowAllLayers.svg",
    "remove_layer": "mActionRemoveLayer.svg",
    "toggle_layer": "mActionShowAllLayers.svg",
    # File/project
    "new_project": "mActionFileNew.svg",
    "open_project": "mActionFileOpen.svg",
    "save_project": "mActionFileSave.svg",
    "save_project_as": "mActionFileSaveAs.svg",
    "export_gpkg": "mActionFileSaveAs.svg",
    "export_csv": "mActionOpenTable.svg",
    "export_profile_csv": "mActionSaveMapAsImage.svg",
    "export_geotiff": "mActionSaveMapAsImage.svg",
    "print_layout": "mActionSaveMapAsImage.svg",
    # App/ui
    "settings": "mActionOptions.svg",
    "undo": "mActionUndo.svg",
    "redo": "mActionRedo.svg",
    "select_features": "mActionSelectRectangle.svg",
    "deselect_all": "mActionDeselectAll.svg",
    "attribute_table": "mActionOpenTable.svg",
    "map_canvas": "mActionNewMap.svg",
    "split_view": "mActionMapIdentification.svg",
    "fullscreen": "mActionMapIdentification.svg",
    "coordinate_capture": "mActionIdentify.svg",
    "scale_bar": "mActionScaleBar.svg",
    "graticule": "mActionScaleBar.svg",
    # Status
    "warning": "mIconWarning.svg",
    "info": "mActionIdentify.svg",
    "error": "mActionDeleteSelected.svg",
    "success": "mIconSuccess.svg",
}


class IconRegistry:
    """Central toolbar icon provider backed by local SVG files."""

    _cache: dict[str, QIcon] = {}

    @classmethod
    def get(
        cls,
        tool_name: str,
        size: int = DEFAULT_ICON_SIZE,
        color: Optional[str] = None,
    ) -> QIcon:
        cache_key = f"{tool_name}_{size}_{color or ''}"
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        filename = ICON_MANIFEST.get(tool_name)
        if not filename:
            icon = cls._make_placeholder(tool_name[:2].upper(), size)
            cls._cache[cache_key] = icon
            return icon

        path = ICON_DIR / filename
        if not path.exists():
            icon = cls._make_placeholder(tool_name[:2].upper(), size)
            cls._cache[cache_key] = icon
            return icon

        icon = cls._render_svg(path, size, color)
        cls._cache[cache_key] = icon
        return icon

    @classmethod
    def clear_cache(cls) -> None:
        cls._cache.clear()

    @staticmethod
    def _render_svg(path: Path, size: int, color: Optional[str]) -> QIcon:
        if QSvgRenderer is None:
            base = QIcon(str(path))
            if not color:
                return base
            # If QtSvg is unavailable and tint is requested, fall back to placeholder.
            return IconRegistry._make_placeholder(path.stem[:2].upper(), size)

        renderer = QSvgRenderer(str(path))
        pixmap = QPixmap(QSize(size, size))
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
        painter.end()

        if not color:
            return QIcon(pixmap)

        tinted = QPixmap(QSize(size, size))
        tinted.fill(Qt.GlobalColor.transparent)
        tint_painter = QPainter(tinted)
        tint_painter.drawPixmap(0, 0, pixmap)
        tint_painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        tint_painter.fillRect(tinted.rect(), QColor(color))
        tint_painter.end()
        return QIcon(tinted)

    @staticmethod
    def _make_placeholder(label: str, size: int) -> QIcon:
        pixmap = QPixmap(QSize(size, size))
        pixmap.fill(QColor("#37474F"))
        painter = QPainter(pixmap)
        painter.setPen(QColor("#ECEFF1"))
        font = painter.font()
        font.setPixelSize(max(8, size // 3))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, label[:2])
        painter.end()
        return QIcon(pixmap)


def missing_icon_files() -> list[str]:
    """Return the list of SVG filenames that are still missing locally."""
    expected = sorted(set(ICON_MANIFEST.values()))
    return [filename for filename in expected if not (ICON_DIR / filename).exists()]


def download_qgis_icons(output_dir: Path | None = None) -> tuple[int, list[str]]:
    """Download all icons in ICON_MANIFEST from the QGIS default theme."""
    output = output_dir or ICON_DIR
    output.mkdir(parents=True, exist_ok=True)

    base_url = "https://raw.githubusercontent.com/qgis/QGIS/master/images/themes/default/"
    downloaded = 0
    failed: list[str] = []

    for filename in sorted(set(ICON_MANIFEST.values())):
        destination = output / filename
        if destination.exists():
            continue
        url = base_url + filename
        try:
            urlretrieve(url, str(destination))
            downloaded += 1
        except (HTTPError, URLError, OSError):
            failed.append(filename)

    IconRegistry.clear_cache()
    return downloaded, failed


def _main() -> int:
    parser = argparse.ArgumentParser(description="QGIS icon bootstrap helper")
    parser.add_argument("--download", action="store_true", help="Download missing icons into client_frontend/icons")
    parser.add_argument("--list-missing", action="store_true", help="List unresolved icon files")
    args = parser.parse_args()

    if args.download:
        downloaded, failed = download_qgis_icons()
        print(f"Downloaded {downloaded} file(s).")
        if failed:
            print("Failed files:")
            for filename in failed:
                print(filename)
            return 1

    if args.list_missing or not args.download:
        missing = missing_icon_files()
        if not missing:
            print("All icon files are present.")
            return 0
        print("Missing icon files:")
        for filename in missing:
            print(filename)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
