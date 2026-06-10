from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

from qtpy.QtCore import QMarginsF, QRect, Qt, QThread, Signal  # type: ignore
from qtpy.QtGui import QImage, QPageLayout, QPageSize, QPainter, QPdfWriter
from qtpy.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStyle,
    QVBoxLayout,
    QWidget,
)


EXPORT_ERROR_LITERAL = "Export Error"


class ExportCoordinator:
    """Handle complex export operations (GeoPackage, PDF, GeoTIFF) for GIS assets and annotations."""

    def __init__(self, controller):
        self._controller = controller
        self._logger = logging.getLogger("desktop.export")

    def export_geopackage(self) -> None:
        """Export all visible search result assets and annotations into a single GeoPackage."""
        c = self._controller
        visible_assets = self._get_visible_search_assets()

        if not visible_assets and not self._has_annotations():
            c.panel.log("Nothing to export. Load assets or add annotations first.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            c.panel,
            "Export GeoPackage",
            "gis_export.gpkg",
            "GeoPackage (*.gpkg)",
        )
        if not file_path:
            return

        output_path = Path(file_path)
        c.panel.log(f"Starting GeoPackage export to {output_path.name}...")

        try:
            # 1. Export Annotations (delegating to ProjectIO which uses Fiona if available) Since ProjectIO.export_annotations_geopackage asks for a file path, we'll use it but it might prompt again if we are not careful. Actually, I'll implement a custom logic here to avoid double prompts.
            self._export_vector_layers(output_path)

            # 2. Export Raster Layers (Original GeoTIFFs as GPKG layers)
            from osgeo import gdal
            for asset in visible_assets:
                src_path = str(asset.get("file_path", ""))
                if not src_path or not os.path.exists(src_path):
                    continue
                
                layer_name = asset.get("file_name", "layer").replace(".", "_").replace(" ", "_")
                # Ensure unique layer names to avoid "table already exists" error
                layer_name = f"raster_{layer_name}"
                c.panel.log(f"  Adding raster layer: {layer_name}")
                
                # Use GDAL to add the TIFF as a layer in the GeoPackage -update allows appending to existing GPKG
                ds = gdal.Open(src_path)
                if ds:
                    translate_options = {
                        "format": "GPKG",
                        "creationOptions": [f"RASTER_TABLE={layer_name}", "APPEND_SUBDATASET=YES"]
                    }
                    # GeoPackage raster supports max 4 bands (RGBA). If source has more (e.g. 6-band multispectral), limit to first 3 or 4.
                    if ds.RasterCount > 4:
                        translate_options["bandList"] = [1, 2, 3]
                        c.panel.log(f"    Source has {ds.RasterCount} bands; limiting to first 3 for GPKG compatibility.")
                    
                    try:
                        gdal.Translate(str(output_path), ds, **translate_options)
                    except Exception as ge:
                        self._logger.warning(f"GDAL translate failed for {layer_name}: {ge}")
                        c.panel.log(f"    Warning: Could not add {layer_name} to GPKG: {ge!s}")
                    ds = None

            c.panel.log(f"GeoPackage export successful: {output_path.name}")
            QMessageBox.information(c.panel, "Export Complete", f"Successfully exported to:\n{output_path}")

        except Exception as e:
            self._logger.exception("GeoPackage export failed")
            c.panel.log(f"GeoPackage export failed: {e!s}")
            QMessageBox.critical(c.panel, EXPORT_ERROR_LITERAL, f"Failed to export GeoPackage:\n{e!s}")

    def export_asset(self) -> None:
        """Export individual searched assets using a minimalist dialog."""
        c = self._controller
        assets = list(c._search_result_assets_by_path.values())
        dialog = ExportAssetDialog(
            c.panel,
            assets,
            resolve_source_path=c._find_best_file_version,
        )
        dialog.exec()

    def export_pdf(self) -> None:
        """Capture the current scene and annotations into a formal PDF report."""
        c = self._controller
        c.panel.log("Preparing PDF report...")

        # 1. Get snapshot from JS We use runJavaScript with a callback or use the return value if possible. Since runJavaScript is async in QtWebEngine, we'll need to use a trick or just wait. But we can use the bridge to return it.
        
        # We'll use a signal/slot pattern or a simple polling for the result if needed. Actually, let's use a simpler way: runJavaScript with a python callback.
        
        def on_snapshot_ready(data_url):
            if not data_url:
                c.panel.log("Failed to capture map snapshot.")
                return
            
            # 2. Get scene state (metadata)
            c.web_view.page().runJavaScript(
                "window.offlineGIS && window.offlineGIS.getSceneState()",
                lambda state: self._generate_pdf(data_url, state)
            )

        c.web_view.page().runJavaScript(
            "window.offlineGIS && window.offlineGIS.captureSnapshot()",
            on_snapshot_ready
        )

    def _generate_pdf(self, data_url: str, state: dict | None) -> None:
        c = self._controller
        
        file_path, _ = QFileDialog.getSaveFileName(
            c.panel,
            "Export PDF Report",
            "GIS_Report.pdf",
            "PDF Files (*.pdf)",
        )
        if not file_path:
            return

        try:
            # Parse data URL (base64)
            if "," in data_url:
                _header, encoded = data_url.split(",", 1)
            else:
                encoded = data_url
            img_data = base64.b64decode(encoded)
            image = QImage.fromData(img_data)

            writer = QPdfWriter(file_path)
            # Use robust page size and orientation
            writer.setPageSize(QPageSize(QPageSize.A4))
            writer.setPageOrientation(QPageLayout.Landscape)
            writer.setPageMargins(QMarginsF(10, 10, 10, 10))
            
            painter = QPainter()
            if not painter.begin(writer):
                c.panel.log("Failed to initialize QPainter on QPdfWriter.")
                QMessageBox.critical(c.panel, EXPORT_ERROR_LITERAL, "Failed to start PDF painter.")
                return

            try:
                # ── Drawing Logic ──
                # 1. Header
                font = painter.font()
                font.setPointSize(16)
                font.setBold(True)
                painter.setFont(font)
                painter.drawText(QRect(0, 0, 5000, 500), Qt.AlignmentFlag.AlignLeft, "resGIS EXPORT REPORT")
                
                font.setPointSize(10)
                font.setBold(False)
                painter.setFont(font)
                import datetime
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                painter.drawText(QRect(0, 500, 5000, 300), Qt.AlignmentFlag.AlignLeft, f"Generated at: {now_str} (NTRO, Gov. of India)")

                # 2. Map Snapshot
                page_rect = writer.pageLayout().paintRectPixels(writer.resolution())
                margin = 150
                img_w = page_rect.width() - (2 * margin)
                
                if not image.isNull() and image.width() > 0:
                    img_h = int(img_w * image.height() / image.width())
                    img_rect = QRect(margin, 1000, img_w, img_h)
                    painter.drawImage(img_rect, image)
                    
                    # Draw premium cartographic double border
                    from qtpy.QtGui import QColor, QPen
                    painter.setPen(QPen(QColor("#2d3748"), 6))  # Outer thicker border
                    painter.drawRect(img_rect.adjusted(-20, -20, 20, 20))
                    painter.setPen(QPen(QColor("#718096"), 2))  # Inner thin border
                    painter.drawRect(img_rect)
                    y_start = img_rect.bottom() + 350
                else:
                    y_start = 1200
                
                # 3. Metadata (if available)
                if state:
                    y = y_start
                    
                    # Draw divider line
                    from qtpy.QtGui import QColor, QPen
                    painter.setPen(QPen(QColor("#e2e8f0"), 3))
                    painter.drawLine(margin, y, page_rect.width() - margin, y)
                    y += 200
                    
                    # Setup typography
                    font.setPointSize(12)
                    font.setBold(True)
                    painter.setFont(font)
                    painter.setPen(QColor("#2d3748"))
                    
                    # Headers for metadata columns
                    painter.drawText(QRect(margin, y, 4000, 300), Qt.AlignmentFlag.AlignLeft, "GEOGRAPHIC REFERENCE FRAME")
                    painter.drawText(QRect(margin + 4500, y, 4000, 300), Qt.AlignmentFlag.AlignLeft, "CAMERA ORIENTATION")
                    
                    y += 300
                    font.setPointSize(9)
                    font.setBold(False)
                    painter.setFont(font)
                    painter.setPen(QColor("#4a5568"))
                    
                    # Column 1: CRS and View Bounding Box
                    crs_str = "CRS: WGS 84 / EPSG:4326"
                    painter.drawText(QRect(margin, y, 4000, 250), Qt.AlignmentFlag.AlignLeft, crs_str)
                    y_col1 = y + 250
                    
                    extent = state.get("extent") or {}
                    if isinstance(extent, dict) and extent:
                        def safe_float(v):
                            try:
                                return float(v)
                            except (TypeError, ValueError):
                                return 0.0
                        ext_lines = [
                            "Extent Bounds (WGS84 Degrees):",
                            f"  North Lat: {safe_float(extent.get('north')):.6f}°",
                            f"  South Lat: {safe_float(extent.get('south')):.6f}°",
                            f"  East Lon:  {safe_float(extent.get('east')):.6f}°",
                            f"  West Lon:  {safe_float(extent.get('west')):.6f}°"
                        ]
                        for line in ext_lines:
                            painter.drawText(QRect(margin, y_col1, 4000, 250), Qt.AlignmentFlag.AlignLeft, line)
                            y_col1 += 250
                    else:
                        painter.drawText(QRect(margin, y_col1, 4000, 250), Qt.AlignmentFlag.AlignLeft, "Extent: Not available")
                        y_col1 += 250
                    
                    # Column 2: Camera position and rotation info
                    y_col2 = y
                    cam = state.get("camera", {})
                    if isinstance(cam, dict) and cam:
                        pos = cam.get("position", {}) or {}
                        def safe_float(v):
                            try:
                                return float(v)
                            except (TypeError, ValueError):
                                return 0.0
                        cam_lines = [
                            f"Longitude: {safe_float(pos.get('lon')):.6f}°",
                            f"Latitude:  {safe_float(pos.get('lat')):.6f}°",
                            f"Altitude:  {safe_float(pos.get('height')):.1f} m",
                            f"Heading:   {safe_float(cam.get('heading')):.2f}°",
                            f"Pitch:     {safe_float(cam.get('pitch')):.2f}°",
                            f"Roll:      {safe_float(cam.get('roll')):.2f}°"
                        ]
                        for line in cam_lines:
                            painter.drawText(QRect(margin + 4500, y_col2, 4000, 250), Qt.AlignmentFlag.AlignLeft, line)
                            y_col2 += 250
                    else:
                        painter.drawText(QRect(margin + 4500, y_col2, 4000, 250), Qt.AlignmentFlag.AlignLeft, "Camera info not available")
                        y_col2 += 250
                    
                    # Re-align layout cursor
                    y = max(y_col1, y_col2) + 200
                    
                    # Active layers section
                    layers = state.get("visibleLayers", [])
                    if layers and isinstance(layers, list):
                        font.setPointSize(10)
                        font.setBold(True)
                        painter.setFont(font)
                        painter.setPen(QColor("#2d3748"))
                        painter.drawText(QRect(margin, y, 9000, 250), Qt.AlignmentFlag.AlignLeft, "ACTIVE RASTER / DEM LAYERS")
                        
                        y += 250
                        font.setPointSize(9)
                        font.setBold(False)
                        painter.setFont(font)
                        painter.setPen(QColor("#718096"))
                        
                        layers_str = ", ".join(str(layer) for layer in layers if layer)
                        painter.drawText(QRect(margin, y, 9000, 400), Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, layers_str)
            finally:
                painter.end()
                del painter

            c.panel.log(f"PDF Report exported: {Path(file_path).name}")
            QMessageBox.information(c.panel, "Export Complete", f"PDF Report saved to:\n{file_path}")

        except Exception as e:
            import logging
            logger = logging.getLogger("desktop.export")
            logger.exception("PDF export failed")
            c.panel.log(f"PDF export failed: {e!s}")
            QMessageBox.critical(c.panel, EXPORT_ERROR_LITERAL, f"Failed to export PDF:\n{e!s}")


    def _get_visible_search_assets(self) -> list[dict]:
        """Helper to get assets currently visible on the map."""
        c = self._controller
        visible = []
        for path, is_vis in c._search_layer_visibility.items():
            if is_vis:
                asset = c._search_result_assets_by_path.get(path)
                if asset:
                    visible.append(asset)
        return visible

    def _has_annotations(self) -> bool:
        c = self._controller
        return any([
            c._annotation_records,
            c._annotation_line_records,
            c._annotation_polygon_records,
            c._annotation_icon_records,
            c._annotation_text_records,
        ])

    def _export_vector_layers(self, output_path: Path) -> None:
        """Custom GPKG vector export using Fiona."""
        c = self._controller
        try:
            import fiona  # type: ignore
            from fiona.crs import CRS  # type: ignore
        except ImportError:
            c.panel.log("Fiona not available. Vector layers skipped in GPKG.")
            return

        crs = CRS.from_epsg(4326)
        first_layer_written = False

        # 1. Points, Icons, Texts (all as points)
        has_points = bool(c._annotation_records or c._annotation_icon_records or c._annotation_text_records)
        if has_points:
            mode = "w" if not first_layer_written else "a"
            schema = {
                "geometry": "Point",
                "properties": {
                    "category": "str",
                    "confidence": "str",
                    "height_m": "float",
                    "created_at": "str",
                    "notes": "str",
                    "class_level": "str",
                    "annotation_type": "str",
                    "icon": "str",
                },
            }
            try:
                with fiona.open(
                    str(output_path),
                    mode,
                    driver="GPKG",
                    layer="annotations_point",
                    crs=crs,
                    schema=schema,
                ) as ds:
                    for item in c._annotation_records:
                        ds.write({
                            "geometry": {
                                "type": "Point",
                                "coordinates": (
                                    float(item.get("lon") or 0.0),
                                    float(item.get("lat") or 0.0),
                                ),
                            },
                            "properties": {
                                "category": "other",
                                "confidence": "possible",
                                "height_m": -9999.0,
                                "created_at": str(item.get("created_at") or ""),
                                "notes": str(item.get("text") or ""),
                                "class_level": "UNCLASS",
                                "annotation_type": str(item.get("type") or "point"),
                                "icon": "",
                            },
                        })
                    for item in c._annotation_icon_records:
                        ds.write({
                            "geometry": {
                                "type": "Point",
                                "coordinates": (
                                    float(item.get("lon") or 0.0),
                                    float(item.get("lat") or 0.0),
                                ),
                            },
                            "properties": {
                                "category": "icon",
                                "confidence": "possible",
                                "height_m": -9999.0,
                                "created_at": str(item.get("created_at") or ""),
                                "notes": str(item.get("text") or ""),
                                "class_level": "UNCLASS",
                                "annotation_type": "icon",
                                "icon": str(item.get("icon") or ""),
                            },
                        })
                    for item in c._annotation_text_records:
                        ds.write({
                            "geometry": {
                                "type": "Point",
                                "coordinates": (
                                    float(item.get("lon") or 0.0),
                                    float(item.get("lat") or 0.0),
                                ),
                            },
                            "properties": {
                                "category": "text",
                                "confidence": "possible",
                                "height_m": -9999.0,
                                "created_at": str(item.get("created_at") or ""),
                                "notes": str(item.get("text") or ""),
                                "class_level": "UNCLASS",
                                "annotation_type": "text",
                                "icon": "",
                            },
                        })
                first_layer_written = True
            except Exception as ve:
                self._logger.warning("Failed to export annotations_point: %s", ve)

        # 2. Lines
        if c._annotation_line_records:
            mode = "w" if not first_layer_written else "a"
            schema = {
                "geometry": "LineString",
                "properties": {
                    "feature_type": "str",
                    "label": "str",
                    "length_m": "float",
                    "width_m": "float",
                    "condition": "str",
                },
            }
            try:
                with fiona.open(
                    str(output_path),
                    mode,
                    driver="GPKG",
                    layer="annotations_line",
                    crs=crs,
                    schema=schema,
                ) as ds:
                    for item in c._annotation_line_records:
                        ds.write({
                            "geometry": {
                                "type": "LineString",
                                "coordinates": item.get("coords", []),
                            },
                            "properties": {
                                "feature_type": str(item.get("feature_type") or "road"),
                                "label": str(item.get("label") or ""),
                                "length_m": float(item.get("length_m") or 0.0),
                                "width_m": float(item.get("width_m") or 0.0),
                                "condition": str(item.get("condition") or "intact"),
                            },
                        })
                first_layer_written = True
            except Exception as ve:
                self._logger.warning("Failed to export annotations_line: %s", ve)

        # 3. Polygons
        if c._annotation_polygon_records:
            mode = "w" if not first_layer_written else "a"
            schema = {
                "geometry": "Polygon",
                "properties": {
                    "feature_type": "str",
                    "condition": "str",
                    "area_m2": "float",
                    "perimeter_m": "float",
                    "orientation_deg": "float",
                    "notes": "str",
                },
            }
            try:
                with fiona.open(
                    str(output_path),
                    mode,
                    driver="GPKG",
                    layer="annotations_polygon",
                    crs=crs,
                    schema=schema,
                ) as ds:
                    for item in c._annotation_polygon_records:
                        ring = item.get("coords", [])
                        if ring and ring[0] != ring[-1]:
                            ring = [*list(ring), ring[0]]
                        ds.write({
                            "geometry": {"type": "Polygon", "coordinates": [ring]},
                            "properties": {
                                "feature_type": str(item.get("feature_type") or "building"),
                                "condition": str(item.get("condition") or "intact"),
                                "area_m2": float(item.get("area_m2") or 0.0),
                                "perimeter_m": float(item.get("perimeter_m") or 0.0),
                                "orientation_deg": float(item.get("orientation_deg") or 0.0),
                                "notes": str(item.get("notes") or ""),
                            },
                        })
                first_layer_written = True
            except Exception as ve:
                self._logger.warning("Failed to export annotations_polygon: %s", ve)

        # 4. User Vector Layers
        for layer_key, layer_val in c._vector_layers.items():
            if layer_key == "annotations":
                continue
            if not layer_val.get("is_visible", True):
                continue
            geojson = layer_val.get("geojson")
            if not isinstance(geojson, dict) or geojson.get("type") != "FeatureCollection":
                continue
            features = geojson.get("features", [])
            if not features:
                continue

            geom_to_features = {}
            for f in features:
                geom = f.get("geometry")
                if isinstance(geom, dict):
                    gtype = geom.get("type")
                    if gtype in (
                        "Point",
                        "LineString",
                        "Polygon",
                        "MultiPolygon",
                        "MultiPoint",
                        "MultiLineString",
                    ):
                        geom_to_features.setdefault(gtype, []).append(f)

            for gtype, gfeatures in geom_to_features.items():
                props_schema = {}
                first_properties = gfeatures[0].get("properties") or {}
                for pk, pv in first_properties.items():
                    if isinstance(pv, int):
                        props_schema[pk] = "int"
                    elif isinstance(pv, float):
                        props_schema[pk] = "float"
                    else:
                        props_schema[pk] = "str"

                schema = {"geometry": gtype, "properties": props_schema}
                layer_name = f"vector_{layer_key}_{gtype.lower()}"
                mode = "w" if not first_layer_written else "a"
                try:
                    with fiona.open(
                        str(output_path),
                        mode,
                        driver="GPKG",
                        layer=layer_name,
                        crs=crs,
                        schema=schema,
                    ) as ds:
                        for f in gfeatures:
                            cleaned_props = {}
                            f_props = f.get("properties") or {}
                            for pk in props_schema:
                                val = f_props.get(pk)
                                if val is None:
                                    cleaned_props[pk] = None
                                elif props_schema[pk] == "int":
                                    cleaned_props[pk] = int(val)
                                elif props_schema[pk] == "float":
                                    cleaned_props[pk] = float(val)
                                else:
                                    cleaned_props[pk] = str(val)
                            ds.write({
                                "geometry": f.get("geometry"),
                                "properties": cleaned_props,
                            })
                    first_layer_written = True
                except Exception as ve:
                    self._logger.warning(
                        "Failed to export user vector layer %s: %s", layer_name, ve
                    )

class AssetExportThread(QThread):
    progress = Signal(int)
    finished = Signal(bool, str)

    def __init__(self, src_path: str, dest_path: str):
        super().__init__()
        self.src_path = src_path
        self.dest_path = dest_path

    @staticmethod
    def _resolve_export_source(src_path: str) -> str:
        """Prefer COG/WebMercator siblings over raw JPEG2000 sources."""
        original = Path(src_path)
        candidates: list[tuple[Path, int]] = []
        stem = original.stem
        parent = original.parent
        for path, priority in (
            (parent / f"{stem}_3857.cog.tif", 4),
            (parent / f"{stem}_3857.tif", 3),
            (parent / f"{stem}.cog.tif", 2),
            (original, 1),
        ):
            if path.exists():
                candidates.append((path, priority))
        if not candidates:
            return src_path
        candidates.sort(key=lambda item: item[1], reverse=True)
        return str(candidates[0][0])

    def run(self):
        try:
            import shutil

            from osgeo import gdal

            export_src = self.src_path
            
            # If the resolved source file is already a GeoTIFF or LAS/LAZ, perform a fast direct copy
            if export_src.lower().endswith((".tif", ".tiff", ".las", ".laz")):
                self.progress.emit(10)
                shutil.copy2(export_src, self.dest_path)
                self.progress.emit(100)
                self.finished.emit(True, "")
                return

            ds = gdal.Open(export_src, gdal.GA_ReadOnly)
            if not ds:
                self.finished.emit(
                    False,
                    f"Failed to open source file: {Path(export_src).name}",
                )
                return

            def progress_callback(complete, message, cb_data):
                percent = int(complete * 100)
                self.progress.emit(percent)
                return 1

            translate_options = gdal.TranslateOptions(
                format="GTiff",
                creationOptions=["COMPRESS=DEFLATE", "TILED=YES"],
                callback=progress_callback,
            )
            try:
                result = gdal.Translate(self.dest_path, ds, options=translate_options)
            except TypeError:
                result = gdal.Translate(
                    self.dest_path,
                    ds,
                    format="GTiff",
                    creationOptions=["COMPRESS=DEFLATE", "TILED=YES"],
                )
            ds = None
            if result is None:
                self.finished.emit(False, "GDAL translate returned no output.")
                return
            result = None
            if not Path(self.dest_path).exists():
                self.finished.emit(False, "Export file was not created.")
                return

            self.finished.emit(True, "")
        except Exception as e:
            self.finished.emit(False, str(e))


class ExportAssetDialog(QDialog):
    def __init__(self, parent, assets, resolve_source_path=None):
        super().__init__(parent)
        self.assets = assets
        self._resolve_source_path = resolve_source_path
        self.threads = {}  # Keep references to running threads
        self.finished_threads = []  # Keep references to completed threads to prevent premature GC/crash
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Export Assets")
        self.resize(600, 400)
        self.setMinimumSize(500, 300)
        
        # Black text & white minimalist styling
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
                color: #000000;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            }
            QLabel {
                color: #000000;
                font-size: 13px;
            }
            QPushButton {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #d2d2d7;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #f5f5f7;
            }
            QPushButton:pressed {
                background-color: #e8e8ed;
            }
            QPushButton:disabled {
                background-color: #f5f5f7;
                color: #8e8e93;
                border-color: #e8e8ed;
            }
            QProgressBar {
                border: 1px solid #d2d2d7;
                border-radius: 4px;
                text-align: center;
                background-color: #f5f5f7;
                color: #000000;
                font-size: 10px;
                height: 14px;
            }
            QProgressBar::chunk {
                background-color: #34c759; /* Green loader */
                border-radius: 3px;
            }
            QScrollArea {
                border: 1px solid #d2d2d7;
                border-radius: 6px;
                background-color: #ffffff;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        title_label = QLabel("Searched Assets")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #000000;")
        main_layout.addWidget(title_label)

        # Scroll Area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        main_layout.addWidget(scroll_area)

        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background-color: #ffffff;")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(8, 8, 8, 8)
        scroll_layout.setSpacing(10)
        scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll_area.setWidget(scroll_widget)

        if not self.assets:
            no_assets_label = QLabel("No searched assets found.")
            no_assets_label.setStyleSheet("color: #8e8e93; font-style: italic; qproperty-alignment: AlignCenter;")
            scroll_layout.addWidget(no_assets_label)
        else:
            for _idx, asset in enumerate(self.assets):
                row_widget = QWidget()
                row_widget.setStyleSheet("""
                    QWidget {
                        background-color: #ffffff;
                        border-bottom: 1px solid #f5f5f7;
                    }
                """)
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(8, 8, 8, 8)
                row_layout.setSpacing(10)

                # Name & Kind info
                file_path = asset.get("file_path", "")
                file_name = asset.get("file_name", Path(file_path).name or "Asset")
                kind = str(asset.get("kind") or "Unknown").upper()
                name_label = QLabel(f"{file_name} [{kind}]")
                name_label.setToolTip(file_path)
                name_label.setStyleSheet("font-weight: 500;")
                row_layout.addWidget(name_label, stretch=3)

                # Progress & Loader Area
                progress_container = QWidget()
                progress_container_layout = QHBoxLayout(progress_container)
                progress_container_layout.setContentsMargins(0, 0, 0, 0)
                progress_container_layout.setSpacing(8)

                status_label = QLabel("")
                status_label.setStyleSheet("color: #8e8e93; font-size: 12px;")
                progress_container_layout.addWidget(status_label)

                progress_bar = QProgressBar()
                progress_bar.setValue(0)
                progress_bar.setVisible(False)
                progress_bar.setFixedWidth(100)
                progress_container_layout.addWidget(progress_bar)

                row_layout.addWidget(progress_container, stretch=2)

                # Download button
                download_btn = QPushButton()
                style = self.style()
                if style:
                    download_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
                download_btn.setText("Download")
                
                # Connect download action
                download_btn.clicked.connect(lambda checked=False, p=file_path, fn=file_name, btn=download_btn, pb=progress_bar, sl=status_label: self.start_download(p, fn, btn, pb, sl))
                row_layout.addWidget(download_btn)

                scroll_layout.addWidget(row_widget)

        # Close Button
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.accept)
        main_layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def start_download(self, file_path, file_name, button, progress_bar, status_label):
        # Strict guards to prevent double-click / multiple triggers
        if not button.isEnabled():
            return
        if file_path in self.threads:
            return
        if status_label.text() == "Done":
            return

        # Determine suggestion file name
        lower_path = file_path.lower()
        if lower_path.endswith((".las", ".laz")):
            sugg_name = file_name if file_name.lower().endswith((".las", ".laz")) else Path(file_name).with_suffix(Path(file_path).suffix).name
            filter_str = "LiDAR Files (*.las *.laz);;All Files (*)"
            title_str = "Save LiDAR Asset"
        else:
            sugg_name = file_name if file_name.lower().endswith((".tif", ".tiff")) else Path(file_name).with_suffix(".tif").name
            filter_str = "GeoTIFF (*.tif *.tiff);;All Files (*)"
            title_str = "Save Raster Asset"

        dest_path, _ = QFileDialog.getSaveFileName(
            self,
            title_str,
            sugg_name,
            filter_str
        )
        if not dest_path:
            return

        export_src = file_path
        if self._resolve_source_path:
            try:
                export_src = self._resolve_source_path(file_path)
            except Exception:
                export_src = AssetExportThread._resolve_export_source(file_path)
        else:
            export_src = AssetExportThread._resolve_export_source(file_path)

        if not Path(export_src).exists():
            QMessageBox.critical(
                self,
                EXPORT_ERROR_LITERAL,
                f"Source file not found:\n{export_src}",
            )
            return

        # Disable button and update UI
        button.setEnabled(False)
        status_label.setStyleSheet("color: #8e8e93;")
        status_label.setText("Preparing...")
        progress_bar.setValue(0)
        progress_bar.setVisible(True)

        # Start background thread
        thread_key = file_path
        # Clean up existing thread if any
        if thread_key in self.threads:
            existing = self.threads[thread_key]
            existing.requestInterruption()
            existing.wait(30000)

        thread = AssetExportThread(export_src, dest_path)
        thread.progress.connect(progress_bar.setValue)
        thread.progress.connect(lambda val: status_label.setText("Exporting..."))
        
        def handle_finished(success, err_msg):
            progress_bar.setVisible(False)
            if success:
                status_label.setStyleSheet("color: #34c759; font-weight: bold;")
                status_label.setText("Done")
            else:
                status_label.setStyleSheet("color: #ff3b30; font-weight: bold;")
                status_label.setText("Failed")
                QMessageBox.critical(self, EXPORT_ERROR_LITERAL, f"Failed to export asset:\n{err_msg}")
                button.setEnabled(True)
            # Move reference to finished_threads to prevent premature GC/crash
            thread_obj = self.threads.pop(thread_key, None)
            if thread_obj:
                self.finished_threads.append(thread_obj)

        thread.finished.connect(handle_finished)
        self.threads[thread_key] = thread
        thread.start()

    def accept(self):
        for thread in list(self.threads.values()):
            if thread.isRunning():
                thread.terminate()
                thread.wait()
        super().accept()

    def reject(self):
        for thread in list(self.threads.values()):
            if thread.isRunning():
                thread.terminate()
                thread.wait()
        super().reject()

    def closeEvent(self, event):
        for thread in list(self.threads.values()):
            if thread.isRunning():
                thread.terminate()
                thread.wait()
        super().closeEvent(event)


__all__ = ["ExportCoordinator"]
