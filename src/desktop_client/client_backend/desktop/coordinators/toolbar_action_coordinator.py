from __future__ import annotations


class ToolbarActionCoordinator:
    """Route toolbar labels to the controller's action handlers."""

    def __init__(self, controller):
        self._controller = controller

    def handle_toolbar_action(
        self, action_label: str, checked: bool | None = None
    ) -> bool | None:
        c = self._controller
        handlers = {
            # Layer Compositor is orchestrated by MainWindow, but keep a mapped
            # handler label here to preserve toolbar contract coverage.
            "Layer Compositor": lambda: None,
            "Comparator": c._toolbar_toggle_comparator,
            "Distance / Azimuth": c._toolbar_measure_distance,
            "Polygon Area": c._toolbar_measure_polygon_area,
            "Elevation Profile": c._toolbar_elevation_profile,
            "Fill Volume": c._toolbar_measure_volume,
            "Slope & Aspect": c._toolbar_measure_slope_aspect,
            "Clear Last": c._toolbar_clear_last,
            "Clear All": c._toolbar_clear_all,
            "Add Point": c._toolbar_toggle_add_point_mode,
            "Add Polygon": c._toolbar_add_polygon_annotation,
            "Save Annotations": c._toolbar_export_geopackage,
            "Pan": c._toolbar_set_pan_mode,
            "Zoom In": lambda: c._run_js_call("zoomIn"),
            "Zoom Out": lambda: c._run_js_call("zoomOut"),
            "Zoom to Extent": lambda: c._run_js_call("zoomToExtent"),
            "Add Vector": c.browse_path,
            "Add Raster Layer": c.browse_path,
            "Save Project": c._toolbar_save_project,
            "Export": c._toolbar_export_geopackage,
            "Export GeoPackage": c._toolbar_export_geopackage,
        }
        handler = handlers.get(action_label)
        if handler is None:
            c.panel.log(f"Toolbar action not mapped: {action_label}")
            c._logger.warning("Toolbar action not mapped: %s", action_label)
            return None
        c.panel.log(f"Toolbar action: {action_label}")
        c._logger.info("Toolbar action triggered: %s", action_label)
        try:
            if action_label == "Comparator":
                return c._toolbar_toggle_comparator(enabled=checked)
            if action_label == "Distance / Azimuth":
                return c._toolbar_measure_distance(enabled=checked)
            if action_label == "Pan":
                return c._toolbar_set_pan_mode(enabled=checked)
            if action_label == "Add Point":
                return c._toolbar_toggle_add_point_mode(enabled=checked)
            if action_label == "Add Polygon":
                return c._toolbar_add_polygon_annotation(enabled=checked)
            if action_label == "Slope & Aspect":
                return c._toolbar_measure_slope_aspect(enabled=checked)
            handler()
        except Exception:  # pragma: no cover - runtime defensive branch
            c.panel.log(f"Toolbar action failed: {action_label}")
            c._logger.exception("Toolbar action failed: %s", action_label)
        return None


__all__ = ["ToolbarActionCoordinator"]