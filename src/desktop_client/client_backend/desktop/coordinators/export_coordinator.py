from __future__ import annotations

import base64
import json
import logging
import os
import shutil
from pathlib import Path

from qtpy.QtCore import QMargins, QRect, Qt, QSize, QMarginsF
from qtpy.QtGui import QImage, QPainter, QPageLayout, QPageSize, QPdfWriter
from qtpy.QtWidgets import QFileDialog, QMessageBox


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
            # 1. Export Annotations (delegating to ProjectIO which uses Fiona if available)
            # Since ProjectIO.export_annotations_geopackage asks for a file path, 
            # we'll use it but it might prompt again if we are not careful.
            # Actually, I'll implement a custom logic here to avoid double prompts.
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
                
                # Use GDAL to add the TIFF as a layer in the GeoPackage
                # -update allows appending to existing GPKG
                ds = gdal.Open(src_path)
                if ds:
                    translate_options = {
                        "format": "GPKG",
                        "creationOptions": [f"RASTER_TABLE={layer_name}", "APPEND_SUBDATASET=YES"]
                    }
                    # GeoPackage raster supports max 4 bands (RGBA). 
                    # If source has more (e.g. 6-band multispectral), limit to first 3 or 4.
                    if ds.RasterCount > 4:
                        translate_options["bandList"] = [1, 2, 3]
                        c.panel.log(f"    Source has {ds.RasterCount} bands; limiting to first 3 for GPKG compatibility.")
                    
                    try:
                        gdal.Translate(str(output_path), ds, **translate_options)
                    except Exception as ge:
                        self._logger.warning(f"GDAL translate failed for {layer_name}: {ge}")
                        c.panel.log(f"    Warning: Could not add {layer_name} to GPKG: {str(ge)}")
                    ds = None

            c.panel.log(f"GeoPackage export successful: {output_path.name}")
            QMessageBox.information(c.panel, "Export Complete", f"Successfully exported to:\n{output_path}")

        except Exception as e:
            self._logger.exception("GeoPackage export failed")
            c.panel.log(f"GeoPackage export failed: {str(e)}")
            QMessageBox.critical(c.panel, "Export Error", f"Failed to export GeoPackage:\n{str(e)}")

    def export_geotiff(self) -> None:
        """Export individual GeoTIFF files for all visible search results into a folder."""
        c = self._controller
        visible_assets = self._get_visible_search_assets()

        if not visible_assets:
            c.panel.log("No visible search results to export.")
            return

        dir_path = QFileDialog.getExistingDirectory(
            c.panel, "Select Export Directory", str(Path.home())
        )
        if not dir_path:
            return

        dest_dir = Path(dir_path)
        c.panel.log(f"Exporting {len(visible_assets)} GeoTIFFs to {dest_dir.name}...")

        success_count = 0
        for asset in visible_assets:
            src_path = Path(str(asset.get("file_path", "")))
            if not src_path.exists():
                continue
            
            dest_path = dest_dir / src_path.name
            try:
                shutil.copy2(src_path, dest_path)
                success_count += 1
                c.panel.log(f"  Exported: {src_path.name}")
            except Exception as e:
                c.panel.log(f"  Failed to export {src_path.name}: {e}")

        c.panel.log(f"GeoTIFF export complete. {success_count} files saved.")
        QMessageBox.information(c.panel, "Export Complete", f"Exported {success_count} GeoTIFF files to:\n{dest_dir}")

    def export_pdf(self) -> None:
        """Capture the current scene and annotations into a formal PDF report."""
        c = self._controller
        c.panel.log("Preparing PDF report...")

        # 1. Get snapshot from JS
        # We use runJavaScript with a callback or use the return value if possible.
        # Since runJavaScript is async in QtWebEngine, we'll need to use a trick or just wait.
        # But we can use the bridge to return it.
        
        # We'll use a signal/slot pattern or a simple polling for the result if needed.
        # Actually, let's use a simpler way: runJavaScript with a python callback.
        
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
            header, encoded = data_url.split(",", 1)
            img_data = base64.b64decode(encoded)
            image = QImage.fromData(img_data)

            writer = QPdfWriter(file_path)
            # Use robust page size and orientation
            writer.setPageSize(QPageSize(QPageSize.A4))
            writer.setPageOrientation(QPageLayout.Landscape)
            writer.setPageMargins(QMarginsF(10, 10, 10, 10))
            
            painter = QPainter(writer)
            
            # ── Drawing Logic ──
            # 1. Header
            font = painter.font()
            font.setPointSize(16)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(QRect(0, 0, 5000, 500), Qt.AlignmentFlag.AlignLeft, "GIS EXPORT REPORT")
            
            font.setPointSize(10)
            font.setBold(False)
            painter.setFont(font)
            import datetime
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            painter.drawText(QRect(0, 500, 5000, 300), Qt.AlignmentFlag.AlignLeft, f"Generated at: {now_str}")

            # 2. Map Snapshot
            # Scale image to fit page width
            page_rect = writer.pageLayout().paintRectPixels(writer.resolution())
            img_rect = QRect(0, 1000, page_rect.width(), int(page_rect.width() * image.height() / image.width()))
            painter.drawImage(img_rect, image)
            
            # 3. Metadata (if available)
            if state:
                y = img_rect.bottom() + 500
                font.setBold(True)
                painter.setFont(font)
                painter.drawText(QRect(0, y, 5000, 300), Qt.AlignmentFlag.AlignLeft, "Scene Metadata")
                
                font.setBold(False)
                painter.setFont(font)
                y += 400
                cam = state.get("camera", {})
                if cam:
                    pos = cam.get("position", {})
                    cam_str = f"Camera: Lon {pos.get('lon', 0):.4f}, Lat {pos.get('lat', 0):.4f}, Height {pos.get('height', 0):.1f}m"
                    painter.drawText(QRect(0, y, 5000, 300), Qt.AlignmentFlag.AlignLeft, cam_str)
                    y += 300
                
                layers = state.get("visibleLayers", [])
                if layers:
                    painter.drawText(QRect(0, y, 5000, 300), Qt.AlignmentFlag.AlignLeft, f"Active Layers: {len(layers)}")
                    y += 300

            painter.end()
            c.panel.log(f"PDF Report exported: {Path(file_path).name}")
            QMessageBox.information(c.panel, "Export Complete", f"PDF Report saved to:\n{file_path}")

        except Exception as e:
            self._logger.exception("PDF export failed")
            c.panel.log(f"PDF export failed: {str(e)}")

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
            c._annotation_polygon_records
        ])

    def _export_vector_layers(self, output_path: Path) -> None:
        """Custom GPKG vector export using Fiona."""
        c = self._controller
        try:
            import fiona
            from fiona.crs import CRS
        except ImportError:
            c.panel.log("Fiona not available. Vector layers skipped in GPKG.")
            return

        # Simple GPKG write logic for points, lines, polygons
        crs = CRS.from_epsg(4326)
        
        # Points
        if c._annotation_records:
            schema = {'geometry': 'Point', 'properties': {'text': 'str', 'time': 'str'}}
            with fiona.open(str(output_path), 'w', driver='GPKG', layer='annotations_point', crs=crs, schema=schema) as ds:
                for p in c._annotation_records:
                    ds.write({
                        'geometry': {'type': 'Point', 'coordinates': (float(p.get('lon', 0)), float(p.get('lat', 0)))},
                        'properties': {'text': str(p.get('text', '')), 'time': str(p.get('created_at', ''))}
                    })
        
        # Lines
        if c._annotation_line_records:
            schema = {'geometry': 'LineString', 'properties': {'length_m': 'float', 'type': 'str'}}
            mode = 'a' if c._annotation_records else 'w'
            with fiona.open(str(output_path), mode, driver='GPKG', layer='annotations_line', crs=crs, schema=schema) as ds:
                for l in c._annotation_line_records:
                    ds.write({
                        'geometry': {'type': 'LineString', 'coordinates': l.get('coords', [])},
                        'properties': {'length_m': float(l.get('length_m', 0)), 'type': str(l.get('feature_type', 'road'))}
                    })
        
        # Polygons
        if c._annotation_polygon_records:
            schema = {'geometry': 'Polygon', 'properties': {'area_m2': 'float', 'type': 'str'}}
            mode = 'a' if (c._annotation_records or c._annotation_line_records) else 'w'
            with fiona.open(str(output_path), mode, driver='GPKG', layer='annotations_polygon', crs=crs, schema=schema) as ds:
                for poly in c._annotation_polygon_records:
                    coords = poly.get('coords', [])
                    if coords and coords[0] != coords[-1]:
                        coords = list(coords) + [coords[0]]
                    ds.write({
                        'geometry': {'type': 'Polygon', 'coordinates': [coords]},
                        'properties': {'area_m2': float(poly.get('area_m2', 0)), 'type': str(poly.get('feature_type', 'building'))}
                    })

__all__ = ["ExportCoordinator"]
