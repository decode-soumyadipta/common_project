from __future__ import annotations

import logging


class AnnotationCoordinator:
    """Encapsulate annotation management operations for desktop controller."""

    def __init__(self, controller):
        self._controller = controller
        self._logger = logging.getLogger("client_desktop.annotation_coordinator")

    def restore_annotations_on_map(self) -> None:
        """Restore all annotations to the map from saved state."""
        c = self._controller
        c._run_js_call("clearAnnotations")

        # Restore point annotations
        for item in c._annotation_records:
            try:
                lon = float(item.get("lon") or 0.0)
                lat = float(item.get("lat") or 0.0)
                text = str(item.get("text") or c._default_annotation_text)
            except (TypeError, ValueError):
                continue
            c._run_js_call("addAnnotation", text, lon, lat)

        # Restore icon annotations
        for item in c._annotation_icon_records:
            try:
                lon = float(item.get("lon") or 0.0)
                lat = float(item.get("lat") or 0.0)
                icon = str(item.get("icon") or "marker")
                text = str(item.get("text") or "")
            except (TypeError, ValueError):
                continue
            c._run_js_call("addIconAnnotation", lon, lat, icon, text)

        # Restore text labels
        for item in c._annotation_text_records:
            try:
                lon = float(item.get("lon") or 0.0)
                lat = float(item.get("lat") or 0.0)
                text = str(item.get("text") or "Label")
            except (TypeError, ValueError):
                continue
            c._run_js_call("addTextLabel", lon, lat, text)

        # Restore line annotations
        for item in c._annotation_line_records:
            coords = item.get("coords", [])
            if coords:
                c._run_js_call(
                    "addLineAnnotation",
                    coords,
                    str(item.get("label") or "Line"),
                )

        # Restore polygon annotations
        for item in c._annotation_polygon_records:
            coords = item.get("coords", [])
            if coords:
                # Convert list of tuples/lists or list of dicts to dict format expected by JS
                js_points = []
                for coord in coords:
                    if isinstance(coord, (list, tuple)) and len(coord) >= 2:
                        js_points.append({"lon": float(coord[0]), "lat": float(coord[1])})
                    elif isinstance(coord, dict) and "lon" in coord and "lat" in coord:
                        js_points.append({"lon": float(coord["lon"]), "lat": float(coord["lat"])})

                if js_points:
                    c._run_js_call("restoreAnnotationPolygon", js_points)

        # Restore raster stretch settings
        for layer_key, settings in c._raster_stretch_settings.items():
            stretch_type = settings.get("type")
            method = settings.get("method")
            params = settings.get("params", {})
            if stretch_type and method:
                c._run_js_call("applyRasterStretch", layer_key, stretch_type, method, params)

        # Update vector layers with annotation geometry
        annotation_geojson = self._annotation_line_polygon_geojson()
        if annotation_geojson:
            layer_key = "annotations"
            if layer_key in c._vector_layers:
                c._run_js_call("removeVectorLayer", layer_key)
            c._run_js_call("addVectorLayer", layer_key, "Annotations", annotation_geojson, {})
            c._vector_layers[layer_key] = {
                "layer_key": layer_key,
                "label": "Annotations",
                "geojson": annotation_geojson,
                "is_visible": True,
                "source": "annotations",
            }

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
