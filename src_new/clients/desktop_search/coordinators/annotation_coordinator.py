from __future__ import annotations

import logging
import math

from pyproj import Transformer

from src_new.clients.desktop_search.measurement_tools import measure_polygon_area


class AnnotationCoordinator:
    """Encapsulate annotation management operations for desktop controller."""

    def __init__(self, controller):
        self._controller = controller
        self._logger = logging.getLogger("client_desktop.annotation_coordinator")

    def restore_annotations_on_map(self) -> None:
        """Restore all annotations to the map from saved state.
        
        Critical: This must use the EXACT SAME JS function calls and data format
        as when annotations were originally created. Any mismatch will cause:
        - Missing annotations (lines, polygons, text labels)
        - Rendering issues (black backgrounds, floating text)
        - Duplicate entities
        """
        c = self._controller
        self._logger.debug(
            "Restoring annotations: %d points, %d lines, %d polygons, %d icons, %d texts",
            len(c._annotation_records),
            len(c._annotation_line_records),
            len(c._annotation_polygon_records),
            len(c._annotation_icon_records),
            len(c._annotation_text_records),
        )
        
        # IMPORTANT: clearAnnotations must be called ONCE before ANY restores This prevents duplication when restore is called after previous entities exist
        c._run_js_call("clearAnnotations")

        # ─── Restore point annotations ────────────────────────────────────────
        for item in c._annotation_records:
            try:
                lon = float(item.get("lon") or 0.0)
                lat = float(item.get("lat") or 0.0)
                height = float(item.get("height") or 0.0)
                text = str(item.get("text") or c._default_annotation_text)
                
                # Validate coordinates are finite and in valid range
                if not (math.isfinite(lon) and math.isfinite(lat) and math.isfinite(height)):
                    self._logger.warning("Invalid point annotation (non-finite coords): lon=%s lat=%s height=%s", lon, lat, height)
                    continue
                
                if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                    self._logger.warning("Invalid point annotation (out of range): lon=%f lat=%f", lon, lat)
                    continue
                
            except (TypeError, ValueError) as e:
                self._logger.warning("Invalid point annotation data: %s - %s", item, e)
                continue
            self._logger.debug("Restoring point annotation at lon=%.5f lat=%.5f height=%.2f text=%s", lon, lat, height, text)
            c._run_js_call("addAnnotation", text, lon, lat, height)

        # ─── Restore icon annotations ─────────────────────────────────────────
        for item in c._annotation_icon_records:
            try:
                lon = float(item.get("lon") or 0.0)
                lat = float(item.get("lat") or 0.0)
                height = float(item.get("height") or 0.0)
                icon = str(item.get("icon") or "marker")
                text = str(item.get("text") or "")
                
                # Validate coordinates are finite and in valid range
                if not (math.isfinite(lon) and math.isfinite(lat) and math.isfinite(height)):
                    self._logger.warning("Invalid icon annotation (non-finite coords): lon=%s lat=%s height=%s", lon, lat, height)
                    continue
                
                if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                    self._logger.warning("Invalid icon annotation (out of range): lon=%f lat=%f", lon, lat)
                    continue
                
            except (TypeError, ValueError) as e:
                self._logger.warning("Invalid icon annotation data: %s - %s", item, e)
                continue
            self._logger.debug("Restoring icon annotation at lon=%.5f lat=%.5f height=%.2f icon=%s text=%s", lon, lat, height, icon, text)
            c._run_js_call("addIconAnnotation", lon, lat, icon, text, height)

        # ─── Restore text labels ──────────────────────────────────────────────
        # CRITICAL: Text labels MUST be restored AFTER points and icons to prevent CSS conflicts or z-index issues that cause black backgrounds to leak
        for item in c._annotation_text_records:
            try:
                lon = float(item.get("lon") or 0.0)
                lat = float(item.get("lat") or 0.0)
                height = float(item.get("height") or 0.0)
                text = str(item.get("text") or "Label")
                
                # Validate coordinates are finite and in valid range
                if not (math.isfinite(lon) and math.isfinite(lat) and math.isfinite(height)):
                    self._logger.warning("Invalid text label (non-finite coords): lon=%s lat=%s height=%s", lon, lat, height)
                    continue
                
                if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                    self._logger.warning("Invalid text label (out of range): lon=%f lat=%f", lon, lat)
                    continue
                
            except (TypeError, ValueError) as e:
                self._logger.warning("Invalid text label data: %s - %s", item, e)
                continue
            self._logger.debug("Restoring text label at lon=%.5f lat=%.5f height=%.2f text=%s", lon, lat, height, text)
            c._run_js_call("addTextLabel", lon, lat, text, height)

        # ─── Restore line annotations ──────────────────────────────────────────
        # Lines MUST NOT have text labels pre-injected; labels come from the data
        for i, item in enumerate(c._annotation_line_records):
            coords = item.get("coords", [])
            if not coords:
                self._logger.warning("Line annotation #%d has empty coords", i)
                continue
            
            label = str(item.get("label") or f"Line {i+1}")
            
            # Validate coords format: must be list of [lon, lat] pairs
            try:
                validated_coords = []
                for coord in coords:
                    try:
                        lon = None
                        lat = None
                        
                        if isinstance(coord, (list, tuple)) and len(coord) >= 2:
                            lon = float(coord[0])
                            lat = float(coord[1])
                        elif isinstance(coord, dict) and "lon" in coord and "lat" in coord:
                            lon = float(coord["lon"])
                            lat = float(coord["lat"])
                        else:
                            self._logger.warning("Line annotation #%d: Invalid coord format: %s", i, coord)
                            continue
                        
                        # Validate lon/lat are finite numbers
                        if not (isinstance(lon, float) and isinstance(lat, float)):
                            self._logger.warning("Line annotation #%d: Non-numeric coords lon=%s lat=%s", i, lon, lat)
                            continue
                        
                        if not (math.isfinite(lon) and math.isfinite(lat)):
                            self._logger.warning("Line annotation #%d: Non-finite coords lon=%s lat=%s", i, lon, lat)
                            continue
                        
                        # Validate lon/lat are in valid ranges
                        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                            self._logger.warning("Line annotation #%d: Coords out of valid range lon=%f lat=%f", i, lon, lat)
                            continue
                        
                        height = 0.0
                        if isinstance(coord, (list, tuple)) and len(coord) >= 3:
                            height = float(coord[2])
                        elif isinstance(coord, dict) and "height" in coord:
                            height = float(coord["height"])
                        
                        validated_coords.append([lon, lat, height])
                    except (ValueError, TypeError) as coord_err:
                        self._logger.warning("Line annotation #%d: Failed to parse coord %s: %s", i, coord, coord_err)
                        continue
                
                # Remove duplicate consecutive points
                deduped_coords = []
                for coord in validated_coords:
                    if not deduped_coords or deduped_coords[-1] != coord:
                        deduped_coords.append(coord)
                
                if len(deduped_coords) < 2:
                    self._logger.warning("Line annotation #%d has < 2 unique valid coords (had %d validated)", i, len(validated_coords))
                    continue
                
                self._logger.debug("Restoring line annotation label=%s coords=%d", label, len(deduped_coords))
                c._run_js_call("addLineAnnotation", deduped_coords, label)
            except Exception as e:
                self._logger.error("Failed to restore line annotation #%d: %s", i, e)
                continue

        # ─── Restore polygon annotations ───────────────────────────────────────
        # Polygons MUST be closed rings and properly formatted
        if not c._undo_redo_in_progress:
            for i, item in enumerate(c._annotation_polygon_records):
                coords = item.get("coords", [])
                if not coords:
                    self._logger.warning("Polygon annotation #%d has empty coords", i)
                    continue

                label = str(item.get("label") or f"Polygon {i+1}")
                
                try:
                    # Convert to GeoJSON-compatible format: list of [lon, lat] pairs
                    validated_coords = []
                    for coord in coords:
                        try:
                            lon = None
                            lat = None
                            
                            if isinstance(coord, (list, tuple)) and len(coord) >= 2:
                                lon = float(coord[0])
                                lat = float(coord[1])
                            elif isinstance(coord, dict) and "lon" in coord and "lat" in coord:
                                lon = float(coord["lon"])
                                lat = float(coord["lat"])
                            else:
                                self._logger.warning("Polygon annotation #%d: Invalid coord format: %s", i, coord)
                                continue
                            
                            # Validate lon/lat are finite numbers
                            if not (isinstance(lon, float) and isinstance(lat, float)):
                                self._logger.warning("Polygon annotation #%d: Non-numeric coords lon=%s lat=%s", i, lon, lat)
                                continue
                            
                            if not (math.isfinite(lon) and math.isfinite(lat)):
                                self._logger.warning("Polygon annotation #%d: Non-finite coords lon=%s lat=%s", i, lon, lat)
                                continue
                            
                            # Validate lon/lat are in valid ranges
                            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                                self._logger.warning("Polygon annotation #%d: Coords out of valid range lon=%f lat=%f", i, lon, lat)
                                continue
                            
                            height = 0.0
                            if isinstance(coord, (list, tuple)) and len(coord) >= 3:
                                height = float(coord[2])
                            elif isinstance(coord, dict) and "height" in coord:
                                height = float(coord["height"])
                            
                            validated_coords.append([lon, lat, height])
                        except (ValueError, TypeError) as coord_err:
                            self._logger.warning("Polygon annotation #%d: Failed to parse coord %s: %s", i, coord, coord_err)
                            continue
                    
                    # Remove duplicate consecutive points
                    deduped_coords = []
                    for coord in validated_coords:
                        if not deduped_coords or deduped_coords[-1] != coord:
                            deduped_coords.append(coord)
                    
                    if len(deduped_coords) < 3:
                        self._logger.warning("Polygon annotation #%d has < 3 unique valid coords (had %d validated)", i, len(validated_coords))
                        continue
                    
                    # Ensure polygon is closed
                    if deduped_coords[0] != deduped_coords[-1]:
                        deduped_coords.append(deduped_coords[0])
                    
                    self._logger.debug("Restoring polygon annotation label=%s coords=%d", label, len(deduped_coords))
                    # restoreAnnotationPolygon expects (points, id, label) - use None for auto-generated id
                    c._run_js_call("restoreAnnotationPolygon", deduped_coords, None, label)
                except Exception as e:
                    self._logger.error("Failed to restore polygon annotation #%d: %s", i, e)
                    continue

        # ─── Restore raster stretch settings ───────────────────────────────────
        for layer_key, settings in c._raster_stretch_settings.items():
            stretch_type = settings.get("type")
            method = settings.get("method")
            params = settings.get("params", {})
            if stretch_type and method:
                self._logger.debug("Restoring raster stretch layer_key=%s type=%s method=%s", layer_key, stretch_type, method)
                c._run_js_call("applyRasterStretch", layer_key, stretch_type, method, params)
        
        self._logger.info("Annotation restoration complete")

    def _annotation_line_polygon_geojson(self) -> dict | None:
        """Build GeoJSON FeatureCollection from annotation lines and polygons."""
        c = self._controller
        features = []

        # Add line features
        for item in c._annotation_line_records:
            coords = item.get("coords", [])
            if not coords:
                continue
            # Convert to GeoJSON LineString format
            line_coords = []
            for coord in coords:
                if isinstance(coord, (list, tuple)) and len(coord) >= 2:
                    line_coords.append([float(coord[0]), float(coord[1])])
                elif isinstance(coord, dict) and "lon" in coord and "lat" in coord:
                    line_coords.append([float(coord["lon"]), float(coord["lat"])])

            if line_coords:
                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": line_coords,
                    },
                    "properties": {
                        "label": item.get("label", "Line"),
                        "type": "annotation_line",
                    },
                })

        # Add polygon features
        for item in c._annotation_polygon_records:
            coords = item.get("coords", [])
            if not coords:
                continue
            # Convert to GeoJSON Polygon format
            polygon_coords = []
            for coord in coords:
                if isinstance(coord, (list, tuple)) and len(coord) >= 2:
                    polygon_coords.append([float(coord[0]), float(coord[1])])
                elif isinstance(coord, dict) and "lon" in coord and "lat" in coord:
                    polygon_coords.append([float(coord["lon"]), float(coord["lat"])])

            if polygon_coords:
                # Close the polygon if not already closed
                if polygon_coords[0] != polygon_coords[-1]:
                    polygon_coords.append(polygon_coords[0])

                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [polygon_coords],
                    },
                    "properties": {
                        "label": item.get("label", "Polygon"),
                        "type": "annotation_polygon",
                    },
                })

        if not features:
            return None

        return {
            "type": "FeatureCollection",
            "features": features,
        }

    def set_annotation_overlay_visible(self, visible: bool) -> None:
        """Toggle visibility of annotation overlay."""
        c = self._controller
        c._run_js_call("setAnnotationVisibility", bool(visible))

    def _current_polygon_lonlat(self) -> list[tuple[float, float]] | None:
        c = self._controller
        payload = c.state.search_geometry_payload or {}
        points = payload.get("points")
        if not isinstance(points, list) or len(points) < 3:
            return None
        out: list[tuple[float, float]] = []
        for point in points:
            if not isinstance(point, dict):
                continue
            lon = point.get("lon")
            lat = point.get("lat")
            if isinstance(lon, (int, float)) and isinstance(lat, (int, float)):
                out.append((float(lon), float(lat)))
        return out if len(out) >= 3 else None

    def _polygon_metrics_for_export(
        self, polygon_points: list[tuple[float, float]]
    ) -> tuple[float, float, float]:
        c = self._controller
        if not polygon_points:
            return 0.0, 0.0, 0.0

        m = measure_polygon_area(polygon_points, dem_path=None)

        # Keep orientation logic for export
        if polygon_points[0] != polygon_points[-1]:
            polygon_points = [*polygon_points, polygon_points[0]]
        lon_c = sum(p[0] for p in polygon_points) / len(polygon_points)
        lat_c = sum(p[1] for p in polygon_points) / len(polygon_points)
        epsg = c._utm_epsg_for_lon_lat(lon_c, lat_c)
        transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
        projected = [transformer.transform(lon, lat) for lon, lat in polygon_points]

        orientation = 0.0
        longest_len = -1.0
        for i in range(len(projected) - 1):
            dx = projected[i + 1][0] - projected[i][0]
            dy = projected[i + 1][1] - projected[i][1]
            edge_len = math.sqrt(dx * dx + dy * dy)
            if edge_len <= longest_len:
                continue
            longest_len = edge_len
            orientation = (math.degrees(math.atan2(dx, dy))) % 180.0
        return m.planimetric_area_m2, m.perimeter_m, float(orientation)

    def toolbar_add_polygon_annotation(self, enabled: bool | None = None) -> bool:
        c = self._controller
        c._logger.debug(
            "toolbar_add_polygon_annotation enabled=%s polygon_draw_active=%s search_mode=%s search_points=%s",
            enabled,
            getattr(c, "_polygon_draw_mode_enabled", None),
            getattr(c.panel, "search_draw_mode", None),
            len((c.state.search_geometry_payload or {}).get("points") or []),
        )

        if enabled is False:
            # Just disable draw mode — polygons stay visible.
            c._polygon_draw_mode_enabled = False
            c._logger.debug(
                "toolbar_add_polygon_annotation disabled polygon_draw=%s line_draw=%s line_start=%s",
                c._polygon_draw_mode_enabled,
                getattr(c, "_add_line_mode_enabled", None),
                getattr(c, "_annotation_line_start", None),
            )
            c._run_js_call("setAnnotationDrawingMode", False)
            c._run_js_call("setSearchDrawMode", "none")
            c._set_measurement_cursor_enabled(False)
            c.panel.log("Polygon draw disabled.")
            return False

        c._polygon_draw_mode_enabled = True
        c._distance_measure_mode_enabled = False
        c._add_point_mode_enabled = False  # Enforce exclusivity
        c._add_line_mode_enabled = False
        c._add_text_mode_enabled = False
        c._annotation_line_start = None
        c._fly_through_mode_enabled = False  # Strict exclusivity
        c._pan_mode_enabled = False
        c._run_js_call("setDistanceMeasureMode", False)
        c._run_js_call("setPanMode", False)
        c._run_js_call("setFlyThroughMode", False)  # Sync JS state
        c._run_js_call("setLineDrawMode", False)
        c._run_js_call("clearLineDrawPreview")
        c._run_js_call("setAnnotationDrawingMode", True)
        c._run_js_call("clearSearchResultMarkers")
        if hasattr(c, "_set_fly_through_overlay_active"):
            c._set_fly_through_overlay_active(False)

        c.set_search_draw_mode("polygon")
        c._set_measurement_cursor_enabled(True)
        c.panel.log("Polygon draw enabled. Click points, right-click to finish.")
        return True

