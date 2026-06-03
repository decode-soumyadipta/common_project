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
            # Layer Compositor is orchestrated by MainWindow, but keep a mapped handler label here to preserve toolbar contract coverage.
            "Layer Compositor": lambda: None,
            "Comparator": c._toolbar_toggle_comparator,
            "Distance / Azimuth": c._toolbar_measure_distance,
            "Elevation Profile": c._toolbar_elevation_profile,
            "Clear Last": c._toolbar_clear_last,
            "Add Point": c._toolbar_toggle_add_point_mode,
            "Add Line": c._toolbar_toggle_add_line_mode,
            "Add Polygon": c._toolbar_add_polygon_annotation,
            "Add Text Label": c._toolbar_toggle_add_text_mode,
            "Fly Through": c._toolbar_fly_through,
            "Zoom In": lambda: c._run_js_call("zoomIn"),
            "Zoom Out": lambda: c._run_js_call("zoomOut"),
            "Zoom to Extent": lambda: c._run_js_call("zoomToExtent"),
            "Add Vector": c.add_vector_layers,
            "Add Raster Layer": c.add_raster_layers,
            "Save Project": c._toolbar_save_project,
            "Export": c._toolbar_export_geotiff,
            "Export Asset as GeoTIFF": c._toolbar_export_geotiff,
            "Export PDF": c._toolbar_export_pdf,
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
            if action_label == "Add Point":
                return c._toolbar_toggle_add_point_mode(enabled=checked)
            if action_label == "Add Line":
                return c._toolbar_toggle_add_line_mode(enabled=checked)
            if action_label == "Add Polygon":
                return c._toolbar_add_polygon_annotation(enabled=checked)
            if action_label == "Add Text Label":
                return c._toolbar_toggle_add_text_mode(enabled=checked)
            if action_label == "Fly Through":
                return c._toolbar_fly_through(enabled=checked)
            handler()
        except Exception:  # pragma: no cover - runtime defensive branch
            c.panel.log(f"Toolbar action failed: {action_label}")
            c._logger.exception("Toolbar action failed: %s", action_label)
        return None


__all__ = ["ToolbarActionCoordinator"]
