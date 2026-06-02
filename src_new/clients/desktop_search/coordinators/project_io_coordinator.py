from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

from qtpy.QtWidgets import QFileDialog


class ProjectIoCoordinator:
    """Handle toolbar export/save actions without bloating the desktop controller."""

    def __init__(self, controller):
        self._controller = controller

    def _panel(self):
        return self._controller.panel

    def build_project_payload(self) -> dict:
        """Build project payload for saving."""
        c = self._controller
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        order_registry = getattr(c.panel, "_layer_order_registry", {}) or {}

        raster_layers: list[dict[str, object]] = []
        for path, asset in c._search_result_assets_by_path.items():
            normalized_path = str(path or "").replace("\\", "/")
            if not normalized_path:
                continue
            entry = order_registry.get(normalized_path, {})
            raster_layers.append(
                {
                    "file_path": normalized_path,
                    "file_name": asset.get("file_name"),
                    "kind": asset.get("kind"),
                    "crs": asset.get("crs"),
                    "bounds_wkt": asset.get("bounds_wkt"),
                    "tile_url": asset.get("tile_url"),
                    "resolution_x": asset.get("resolution_x"),
                    "resolution_y": asset.get("resolution_y"),
                    "width": asset.get("width"),
                    "height": asset.get("height"),
                    "created_at": asset.get("created_at"),
                    "is_visible": bool(
                        c._search_layer_visibility.get(normalized_path, True)
                    ),
                    "order": entry.get("order", 0),
                    "source": "user"
                    if normalized_path in c._user_added_assets
                    else "search",
                }
            )

        # Exclude auto-generated annotation vector layers — annotations are stored
        # separately under "annotations" key and restored as Cesium entities, not
        # as filled GeoJSON vector layers.  Saving these would cause doubled rendering.
        vector_layers = [
            dict(layer) for layer in c._vector_layers.values()
            if not (
                "annotation" in str(layer.get("layer_key") or "").lower() or
                "annotation" in str(layer.get("source") or "").lower() or
                "annotation" in str(layer.get("label") or "").lower()
            )
        ]

        layer_order = [
            path
            for path, entry in sorted(
                order_registry.items(), key=lambda item: item[1].get("order", 0)
            )
        ]

        scene_mode = "3D Globe"
        basemap_visible = True
        main_win = c.panel.window()
        if hasattr(main_win, "map_overlay_controls") and main_win.map_overlay_controls:
            scene_mode = main_win.map_overlay_controls.scene_mode_combo.currentText()
            basemap_visible = "Show" in main_win.map_overlay_controls.basemap_visibility_combo.currentText()

        dem_color_mode = None
        if hasattr(c.panel, "dem_color_mode_combo") and c.panel.dem_color_mode_combo:
            dem_color_mode = c.panel.dem_color_mode_combo.currentData()

        dem_stretch_mode = None
        if hasattr(c.panel, "dem_stretch_mode_combo") and c.panel.dem_stretch_mode_combo:
            dem_stretch_mode = c.panel.dem_stretch_mode_combo.currentData()

        stretch_mode = None
        if hasattr(c.panel, "stretch_mode_combo") and c.panel.stretch_mode_combo:
            stretch_mode = c.panel.stretch_mode_combo.currentData()

        return {
            "version": 1,
            "saved_at": now,
            "selected_asset_path": (
                c.state.selected_asset.get("file_path")
                if isinstance(c.state.selected_asset, dict)
                else None
            ),
            "clicked_points": list(c.state.clicked_points),
            "camera": getattr(c, "_last_camera_state", None),
            "scene_mode": scene_mode,
            "basemap_visible": basemap_visible,
            "active_dem_color_mode": dem_color_mode,
            "active_dem_stretch_mode": dem_stretch_mode,
            "stretch_mode": stretch_mode,
            "search": {
                "geometry_type": c.state.search_geometry_type,
                "geometry_payload": c.state.search_geometry_payload,
                "visibility": dict(c._search_layer_visibility),
                "layer_order": layer_order,
                "active_dem": c._active_dem_search_layer_key,
                "aoi_visible": bool(c.panel.search_aoi_visible_check.isChecked()) if hasattr(c.panel, "search_aoi_visible_check") else True,
            },
            "annotations": {
                "points": list(c._annotation_records),
                "lines": list(c._annotation_line_records),
                "polygons": list(c._annotation_polygon_records),
                "icons": list(c._annotation_icon_records),
                "text_labels": list(c._annotation_text_records),
            },
            "raster_stretch": dict(c._raster_stretch_settings),
            "layers": {
                "rasters": raster_layers,
                "vectors": vector_layers,
            },
        }

    def clear_project_state(self) -> None:
        """Clear all project state and reset to a clean new-project baseline.

        Clears JS-side layers, geometry, markers, and annotations; then resets
        all Python-side state dictionaries and UI widgets to empty defaults.
        """
        c = self._controller
        if not c._undo_redo_in_progress:
            c._undo_stack.clear()
            c._redo_stack.clear()
        # JS-side: clear in dependency order
        c._run_js_call("clearAllLayers")          # layers + annotations + markers (via updated clearAllLayers)
        c._run_js_call("clearVectorLayers")        # belt-and-suspenders for vector sources
        c._run_js_call("clearSearchGeometry")      # AOI polygon / rectangle draw state
        c._run_js_call("clearAnnotations")         # measurement / annotation entities
        c._run_js_call("clearSearchResultMarkers") # belt-and-suspenders for billboard pins
        c._run_js_call("clearComparatorExplicitKeys")  # reset comparator layer selection
        c._run_js_call("resetDefaultView")         # fly back to default camera position

        # Python-side: reset all state dictionaries
        c._search_result_assets_by_path = {}
        c._search_layer_visibility = {}
        c._loaded_search_layer_keys = set()
        c._last_synced_visibility = {}
        c._active_dem_search_layer_key = None
        c._explicit_imagery_layer_visible = False
        c._explicit_dem_layer_visible = False
        c._user_added_assets = {}
        c._vector_layers = {}
        c._annotation_records = []
        c._annotation_line_records = []
        c._annotation_polygon_records = []
        c._annotation_icon_records = []
        c._annotation_text_records = []
        c._raster_stretch_settings = {}
        # Reset comparator snapshot so old layer selection doesn't leak
        c._comparator_visibility_snapshot = None
        c._swipe_comparator_enabled = False
        c.state.selected_asset = None
        c.state.clicked_points = []
        c.state.search_geometry_type = None
        c.state.search_geometry_payload = None
        # Reset AOI visibility checkbox to checked (default for a fresh project)
        if hasattr(c.panel, "search_aoi_visible_check"):
            c.panel.search_aoi_visible_check.setChecked(True)
        c.panel.assets_combo.clear()
        if hasattr(c.panel, "_layer_order_registry"):
            c.panel._layer_order_registry = {}
        c.panel.update_search_results([], {})
        c.panel.update_vector_layers([])
        c.clear_all_measurement_results()
        c._apply_display_control_mode()
        if not c._undo_redo_in_progress:
            c._last_state_snapshot = c.build_project_payload()

    def export_profile_csv(self) -> None:
        controller = self._controller
        if not controller._last_profile_values:
            controller.panel.log(
                "No profile values available. Run Elevation Profile first."
            )
            return
        file_path, _ = QFileDialog.getSaveFileName(
            controller.panel,
            "Export Profile CSV",
            "profile_export.csv",
            "CSV Files (*.csv)",
        )
        if not file_path:
            return
        output_path = Path(file_path)
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["index", "elevation_m"])
            for idx, value in enumerate(controller._last_profile_values):
                writer.writerow([idx, f"{value:.6f}"])
        controller.panel.log(f"Profile CSV exported: {output_path}")

    def export_annotations_geojson(self) -> None:
        controller = self._controller
        if (
            not controller._annotation_records
            and not controller._annotation_line_records
            and not controller._annotation_polygon_records
            and not controller._annotation_icon_records
            and not controller._annotation_text_records
        ):
            controller.panel.log("No annotations captured yet.")
            return
        file_path, _ = QFileDialog.getSaveFileName(
            controller.panel,
            "Export Annotation GeoJSON",
            "annotations.geojson",
            "GeoJSON (*.geojson)",
        )
        if not file_path:
            return
        features = []
        for item in controller._annotation_records:
            lon = float(item.get("lon") or 0.0)
            lat = float(item.get("lat") or 0.0)
            properties = {
                "type": item.get("type", "point"),
                "text": item.get("text", ""),
                "created_at": item.get("created_at", ""),
            }
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": properties,
                }
            )
        for item in controller._annotation_icon_records:
            lon = float(item.get("lon") or 0.0)
            lat = float(item.get("lat") or 0.0)
            properties = {
                "type": "icon",
                "icon": item.get("icon", ""),
                "text": item.get("text", ""),
                "created_at": item.get("created_at", ""),
            }
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": properties,
                }
            )
        for item in controller._annotation_text_records:
            lon = float(item.get("lon") or 0.0)
            lat = float(item.get("lat") or 0.0)
            properties = {
                "type": "text",
                "text": item.get("text", ""),
                "created_at": item.get("created_at", ""),
            }
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": properties,
                }
            )
        for item in controller._annotation_line_records:
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": item.get("coords", []),
                    },
                    "properties": {
                        "feature_type": item.get("feature_type", "road"),
                        "label": item.get("label", ""),
                        "length_m": item.get("length_m", 0.0),
                        "width_m": item.get("width_m", 0.0),
                        "condition": item.get("condition", "intact"),
                        "created_at": item.get("created_at", ""),
                    },
                }
            )
        for item in controller._annotation_polygon_records:
            ring = item.get("coords", [])
            if ring and ring[0] != ring[-1]:
                ring = list(ring) + [ring[0]]
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [ring]},
                    "properties": {
                        "feature_type": item.get("feature_type", "building"),
                        "condition": item.get("condition", "intact"),
                        "area_m2": item.get("area_m2", 0.0),
                        "perimeter_m": item.get("perimeter_m", 0.0),
                        "orientation_deg": item.get("orientation_deg", 0.0),
                        "notes": item.get("notes", ""),
                        "created_at": item.get("created_at", ""),
                    },
                }
            )
        payload = {"type": "FeatureCollection", "features": features}
        Path(file_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        controller.panel.log(f"Annotation export complete: {file_path}")

    def export_annotations_geopackage(self) -> None:
        controller = self._controller
        if (
            not controller._annotation_records
            and not controller._annotation_line_records
            and not controller._annotation_polygon_records
            and not controller._annotation_icon_records
            and not controller._annotation_text_records
        ):
            controller.panel.log("No annotations captured yet.")
            return
        file_path, _ = QFileDialog.getSaveFileName(
            controller.panel,
            "Export Annotation GeoPackage",
            "annotations.gpkg",
            "GeoPackage (*.gpkg)",
        )
        if not file_path:
            return

        try:
            import fiona
            from fiona.crs import CRS as FionaCRS
        except Exception:
            controller.panel.log(
                "Fiona is unavailable. Falling back to GeoJSON export."
            )
            self.export_annotations_geojson()
            return

        point_schema = {
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
        with fiona.open(
            file_path,
            "w",
            driver="GPKG",
            layer="annotations_point",
            crs=FionaCRS.from_epsg(4326),
            schema=point_schema,
        ) as sink:
            for item in controller._annotation_records:
                lon = float(item.get("lon") or 0.0)
                lat = float(item.get("lat") or 0.0)
                sink.write(
                    {
                        "geometry": {"type": "Point", "coordinates": (lon, lat)},
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
                    }
                )
            for item in controller._annotation_icon_records:
                lon = float(item.get("lon") or 0.0)
                lat = float(item.get("lat") or 0.0)
                sink.write(
                    {
                        "geometry": {"type": "Point", "coordinates": (lon, lat)},
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
                    }
                )
            for item in controller._annotation_text_records:
                lon = float(item.get("lon") or 0.0)
                lat = float(item.get("lat") or 0.0)
                sink.write(
                    {
                        "geometry": {"type": "Point", "coordinates": (lon, lat)},
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
                    }
                )

        line_schema = {
            "geometry": "LineString",
            "properties": {
                "feature_type": "str",
                "label": "str",
                "length_m": "float",
                "width_m": "float",
                "condition": "str",
            },
        }
        with fiona.open(
            file_path,
            "a",
            driver="GPKG",
            layer="annotations_line",
            crs=FionaCRS.from_epsg(4326),
            schema=line_schema,
        ) as sink:
            for item in controller._annotation_line_records:
                sink.write(
                    {
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
                    }
                )

        polygon_schema = {
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
        with fiona.open(
            file_path,
            "a",
            driver="GPKG",
            layer="annotations_polygon",
            crs=FionaCRS.from_epsg(4326),
            schema=polygon_schema,
        ) as sink:
            for item in controller._annotation_polygon_records:
                ring = item.get("coords", [])
                if ring and ring[0] != ring[-1]:
                    ring = list(ring) + [ring[0]]
                sink.write(
                    {
                        "geometry": {"type": "Polygon", "coordinates": [ring]},
                        "properties": {
                            "feature_type": str(item.get("feature_type") or "building"),
                            "condition": str(item.get("condition") or "intact"),
                            "area_m2": float(item.get("area_m2") or 0.0),
                            "perimeter_m": float(item.get("perimeter_m") or 0.0),
                            "orientation_deg": float(
                                item.get("orientation_deg") or 0.0
                            ),
                            "notes": str(item.get("notes") or ""),
                        },
                    }
                )

        controller.panel.log(f"GeoPackage export complete: {file_path}")

    def save_project(self) -> None:
        controller = self._controller
        if controller._project_path is None:
            self.save_project_as()
            return
        try:
            payload = self.build_project_payload()
            controller._project_path.write_text(
                json.dumps(payload, indent=2), encoding="utf-8"
            )
            controller.panel.log(f"Project saved: {controller._project_path}")
            controller._set_project_modified(False)
            from qtpy.QtWidgets import QMessageBox
            QMessageBox.information(
                controller.panel, "Project Saved", f"Project successfully saved to:\n{controller._project_path}"
            )
        except Exception as e:
            from qtpy.QtWidgets import QMessageBox
            QMessageBox.critical(
                controller.panel, "Save Failed", f"Failed to save project:\n{str(e)}"
            )

    def save_project_as(self) -> None:
        controller = self._controller
        file_path, _ = QFileDialog.getSaveFileName(
            controller.panel,
            "Save Project",
            "offline_gis_project.json",
            "JSON Files (*.json)",
        )
        if not file_path:
            return
        try:
            payload = self.build_project_payload()
            target = Path(file_path)
            target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            controller._project_path = target
            controller.panel.log(f"Project saved: {target}")
            controller._set_project_modified(False)
            from qtpy.QtWidgets import QMessageBox
            QMessageBox.information(
                controller.panel, "Project Saved", f"Project successfully saved to:\n{target}"
            )
        except Exception as e:
            from qtpy.QtWidgets import QMessageBox
            QMessageBox.critical(
                controller.panel, "Save Failed", f"Failed to save project:\n{str(e)}"
            )

    def open_project(self) -> None:
        controller = self._controller
        file_path, _ = QFileDialog.getOpenFileName(
            controller.panel,
            "Open Project",
            "",
            "JSON Files (*.json)",
        )
        if not file_path:
            return

        # Show loading overlay immediately — user sees "Opening Project — <name>"
        project_name = Path(file_path).name
        main_win = controller.panel.window()
        if hasattr(main_win, "set_busy_overlay"):
            main_win.set_busy_overlay(True, f"Opening Project \u2014 {project_name}")

        try:
            payload = json.loads(Path(file_path).read_text(encoding="utf-8"))
        except Exception as exc:
            if hasattr(main_win, "set_busy_overlay"):
                main_win.set_busy_overlay(False)
            controller.panel.log(f"Failed to open project: {exc}")
            from qtpy.QtWidgets import QMessageBox
            QMessageBox.critical(
                controller.panel, "Open Failed",
                f"Could not read project file:\n{exc}"
            )
            return

        self.apply_project_payload(payload, source_path=Path(file_path))

    def apply_project_payload(self, payload: dict, source_path: Path | None = None) -> None:
        """Apply project payload to restore project state.

        The restoration is split into two phases:
        1. Synchronous phase – Python state reset + UI combo/label updates.
        2. Deferred phase  – All JS entity calls happen 400 ms later so the
           WebEngine IPC pipe can drain the clear* calls before new entities
           are pushed.  Without this delay, restore calls can execute BEFORE
           the clears, producing duplicated or distorted annotations.
        """
        c = self._controller
        c._loading_project = True
        if not c._undo_redo_in_progress:
            c._undo_stack.clear()
            c._redo_stack.clear()
            c._last_state_snapshot = payload

        # ── Phase 1: clear everything ────────────────────────────────────────
        self.clear_project_state()
        if source_path:
            c._project_path = source_path

        # ── Phase 1a: restore Python-side state from payload ─────────────────
        search_payload = payload.get("search") if isinstance(payload, dict) else {}
        if not isinstance(search_payload, dict):
            search_payload = {}

        geometry_type = search_payload.get("geometry_type")
        geometry_payload = search_payload.get("geometry_payload")
        c.state.search_geometry_type = geometry_type
        c.state.search_geometry_payload = geometry_payload
        # Queue the AOI polygon restore JS call now (harmless if executed before clears)
        if geometry_type == "polygon" and isinstance(geometry_payload, dict):
            points = geometry_payload.get("points", [])
            if isinstance(points, list):
                c._run_js_call("loadSearchPolygon", points)
                c._update_coordinate_inputs_from_polygon({"points": points})

        # Restore annotation records into Python state
        annotations = payload.get("annotations") if isinstance(payload, dict) else {}
        if isinstance(annotations, dict):
            c._annotation_records = list(annotations.get("points") or [])
            c._annotation_line_records = list(annotations.get("lines") or [])
            c._annotation_polygon_records = list(annotations.get("polygons") or [])
            c._annotation_icon_records = list(annotations.get("icons") or [])
            c._annotation_text_records = list(annotations.get("text_labels") or [])
        else:
            c._annotation_records = []
            c._annotation_line_records = []
            c._annotation_polygon_records = []
            c._annotation_icon_records = []
            c._annotation_text_records = []

        # Raster stretch settings
        raster_stretch = payload.get("raster_stretch") if isinstance(payload, dict) else {}
        if isinstance(raster_stretch, dict):
            c._raster_stretch_settings = dict(raster_stretch)
        else:
            c._raster_stretch_settings = {}

        # Build Python-side raster layer registry
        layers_payload = payload.get("layers") if isinstance(payload, dict) else {}
        raster_layers = []
        if isinstance(layers_payload, dict):
            raster_layers = layers_payload.get("rasters") or []
        if not isinstance(raster_layers, list):
            raster_layers = []

        c._search_result_assets_by_path = {}
        c._search_layer_visibility = {}
        c._loaded_search_layer_keys = set()
        c._last_synced_visibility = {}
        c._user_added_assets = {}

        from src_new.clients.desktop_search.tile_url_builder import build_xyz_url

        order_registry: dict = {}
        for entry in raster_layers:
            if not isinstance(entry, dict):
                continue
            fp = str(entry.get("file_path") or "").replace("\\", "/")
            if not fp:
                continue
            file_name = str(entry.get("file_name") or Path(fp).name)
            tile_url = entry.get("tile_url") or build_xyz_url(fp)
            asset = {
                "file_path": fp,
                "file_name": file_name,
                "kind": entry.get("kind") or "unknown",
                "crs": entry.get("crs") or "-",
                "bounds_wkt": entry.get("bounds_wkt") or "",
                "tile_url": tile_url,
                "resolution_x": entry.get("resolution_x"),
                "resolution_y": entry.get("resolution_y"),
                "width": entry.get("width"),
                "height": entry.get("height"),
                "created_at": entry.get("created_at"),
            }
            c._search_result_assets_by_path[fp] = asset
            c._search_layer_visibility[fp] = bool(entry.get("is_visible", True))
            if str(entry.get("source") or "") == "user":
                c._user_added_assets[fp] = asset
            order_registry[fp] = {
                "file_name": file_name,
                "kind": str(asset.get("kind") or "-"),
                "crs": str(asset.get("crs") or "-"),
                "created_at": str(entry.get("created_at") or "-"),
                "is_visible": bool(entry.get("is_visible", True)),
                "order": int(entry.get("order", 0)),
            }

        c.panel._layer_order_registry = order_registry

        # Restore combo-box selections (pure UI, no JS calls needed)
        dem_color = payload.get("active_dem_color_mode")
        if dem_color and hasattr(c.panel, "dem_color_mode_combo"):
            idx = c.panel.dem_color_mode_combo.findData(dem_color)
            if isinstance(idx, int) and idx >= 0:
                c.panel.dem_color_mode_combo.setCurrentIndex(idx)

        dem_stretch = payload.get("active_dem_stretch_mode")
        if dem_stretch and hasattr(c.panel, "dem_stretch_mode_combo"):
            idx = c.panel.dem_stretch_mode_combo.findData(dem_stretch)
            if isinstance(idx, int) and idx >= 0:
                c.panel.dem_stretch_mode_combo.setCurrentIndex(idx)

        stretch = payload.get("stretch_mode")
        if stretch and hasattr(c.panel, "stretch_mode_combo"):
            idx = c.panel.stretch_mode_combo.findData(stretch)
            if isinstance(idx, int) and idx >= 0:
                c.panel.stretch_mode_combo.setCurrentIndex(idx)

        # Restore scene mode and basemap visibility (combo boxes)
        main_win = c.panel.window()
        if hasattr(main_win, "map_overlay_controls") and main_win.map_overlay_controls:
            controls = main_win.map_overlay_controls
            scene_mode = payload.get("scene_mode", "3D Globe")
            controls.scene_mode_combo.setCurrentText(scene_mode)
            basemap_visible = payload.get("basemap_visible", True)
            basemap_text = "Show Map" if basemap_visible else "Hide Map"
            controls.basemap_visibility_combo.setCurrentText(basemap_text)

        c._active_dem_search_layer_key = search_payload.get("active_dem")
        if (
            c._active_dem_search_layer_key
            and c._active_dem_search_layer_key not in c._search_result_assets_by_path
        ):
            c._active_dem_search_layer_key = None

        # Update the search results panel (pure Qt, no JS)
        c.panel.update_search_results(
            list(c._search_result_assets_by_path.values()),
            c._search_layer_visibility,
        )

        # Collect data needed for the deferred JS restore
        vectors = []
        if isinstance(layers_payload, dict):
            vectors = layers_payload.get("vectors") or []
        if not isinstance(vectors, list):
            vectors = []

        c._vector_layers = {}

        layer_order = search_payload.get("layer_order")

        aoi_visible = True
        if isinstance(search_payload, dict) and "aoi_visible" in search_payload:
            aoi_visible = bool(search_payload["aoi_visible"])
        elif isinstance(payload, dict) and "aoi_visible" in payload:
            aoi_visible = bool(payload["aoi_visible"])

        selected_path = payload.get("selected_asset_path")
        if isinstance(selected_path, str) and selected_path:
            selected_asset = c._search_result_assets_by_path.get(
                selected_path.replace("\\", "/")
            )
            if selected_asset:
                c.state.selected_asset = selected_asset

        c.state.clicked_points = list(payload.get("clicked_points") or [])
        c._set_project_modified(False)

        camera = payload.get("camera")

        # ── Phase 2: Deferred JS restoration (400 ms later) ──────────────────
        # All clear* JS calls were queued in clear_project_state() above.
        # We wait 400 ms so the WebEngine IPC pipe drains those calls BEFORE
        # we push new entities.  Without this, restore calls can execute BEFORE
        # the clears, leaving distorted / duplicated annotations and layers.
        def _deferred_restore() -> None:
            try:
                # Sync raster layers → JS
                if c._event_driven_enabled:
                    c._sync_search_visibility_layers_event_driven()
                else:
                    c._sync_search_visibility_layers()

                # Enforce display order
                if isinstance(layer_order, list) and layer_order:
                    ordered_keys = [
                        str(p).replace("\\", "/")
                        for p in layer_order
                        if str(p or "").strip()
                    ]
                    if ordered_keys:
                        c._run_js_call("enforceLayerDisplayOrder", ordered_keys)

                # Restore vector layers
                c._run_js_call("clearVectorLayers")
                for entry in vectors:
                    if not isinstance(entry, dict):
                        continue
                    layer_key = str(entry.get("layer_key") or "").strip()
                    label = str(entry.get("label") or "Vector")
                    geojson = entry.get("geojson")
                    # Skip the auto-generated "annotations" vector layer — annotations are
                    # restored as individual Cesium entities by _restore_annotations_on_map().
                    # Loading this layer causes doubled rendering, filled polygons, and
                    # overlapping labels.
                    if (
                        "annotation" in layer_key.lower() or
                        "annotation" in str(entry.get("source") or "").lower() or
                        "annotation" in label.lower()
                    ):
                        continue
                    if not layer_key or not isinstance(geojson, dict):
                        continue
                    c._run_js_call("addVectorLayer", layer_key, label, geojson, {})
                    is_visible = bool(entry.get("is_visible", True))
                    if not is_visible:
                        c._run_js_call("setVectorLayerVisibility", layer_key, False)
                    c._vector_layers[layer_key] = dict(entry)
                    c._vector_layers[layer_key]["is_visible"] = is_visible

                # Restore all annotations: points, lines, polygons, icons, text labels
                c._restore_annotations_on_map()
                c._refresh_vector_layers_ui()

                # Rebuild search result markers on the map
                c._refresh_search_result_markers()

                # AOI polygon visibility
                c._set_search_aoi_visible(aoi_visible)

                # Restore camera position last
                if isinstance(camera, dict):
                    c._last_camera_state = camera
                    c._run_js_call(
                        "setCameraState",
                        camera.get("lon"),
                        camera.get("lat"),
                        camera.get("height"),
                        camera.get("heading"),
                        camera.get("pitch"),
                        camera.get("roll"),
                    )

                name = source_path.name if source_path else "payload"
                c.panel.log(f"Project loaded: {name}")

            except Exception as _ex:
                import logging
                logging.getLogger("client_desktop.project_io").error(
                    "Deferred project restore failed: %s", _ex
                )
            finally:
                # Always hide the loading overlay regardless of success/failure
                _mw = c.panel.window()
                if hasattr(_mw, "set_busy_overlay"):
                    _mw.set_busy_overlay(False)
                c._loading_project = False

        from qtpy.QtCore import QTimer
        QTimer.singleShot(400, _deferred_restore)


__all__ = ["ProjectIoCoordinator"]
