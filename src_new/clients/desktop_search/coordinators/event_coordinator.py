from __future__ import annotations

import logging


class EventCoordinator:
    """Encapsulate event handling for map clicks, measurements, and JS logs."""

    def __init__(self, controller):
        self._controller = controller
        self._logger = logging.getLogger("client_desktop.event_coordinator")

    def on_map_click(self, lon: float, lat: float) -> None:
        """Handle map click events with routing to active modes."""
        c = self._controller
        c.state.clicked_points.append((lon, lat))
        c.state.clicked_points = c.state.clicked_points[-2:]
        c.panel.click_label.setText(f"Last click: lon={lon:.6f}, lat={lat:.6f}")

        # Route to elevation profile coordinator first (it manages its own click state)
        if c._elevation_profile.active:
            c._elevation_profile.on_map_click(lon, lat)
            return

        if c._add_text_mode_enabled:
            c._add_text_label_at(lon, lat, "Label")
            return

        if c._add_line_mode_enabled:
            if c._annotation_line_start is None:
                c._annotation_line_start = (lon, lat)
                c._run_js_call("setLineDrawStart", lon, lat)
                c._logger.debug(
                    "Add Line anchor set lon=%.6f lat=%.6f line_mode=%s",
                    lon,
                    lat,
                    c._add_line_mode_enabled,
                )
                c.panel.log("Line start set. Click the end point to finish.")
                return
            start_lon, start_lat = c._annotation_line_start
            c._annotation_line_start = None
            c._logger.debug(
                "Add Line finalize start_lon=%.6f start_lat=%.6f end_lon=%.6f end_lat=%.6f",
                start_lon,
                start_lat,
                lon,
                lat,
            )
            c._add_line_annotation_between((start_lon, start_lat), (lon, lat))
            c._run_js_call("clearLineDrawPreview")
            return

        if c._add_point_mode_enabled:
            c._add_annotation_at(lon, lat)
            return

        if c._viewshed_mode_enabled:
            c.panel.log(
                f"Observer point selected at lon={lon:.6f}, lat={lat:.6f}. Computing viewshed..."
            )
            c._toolbar_measure_viewshed()
            c.state.clicked_points.clear()
            return

        if c._shadow_height_mode_enabled:
            if len(c.state.clicked_points) < 2:
                c.panel.log(
                    "Shadow Height: base point captured. Click shadow tip point."
                )
                return
            c._toolbar_measure_shadow_height()
            c.state.clicked_points.clear()

    def on_measurement(self, meters: float) -> None:
        """Handle measurement updates from the map."""
        c = self._controller
        c.panel.measure_label.setText(f"Last distance: {meters:.2f} m")
        self._logger.info("Measurement updated distance_m=%.2f", meters)
        if not c._distance_measure_mode_enabled:
            return

        # Measurement handling continues in MeasurementCoordinator
        c._measure.on_measurement_update(meters)

    def on_js_log(self, level: str, message: str) -> None:
        """Handle JavaScript log messages with appropriate routing."""
        c = self._controller
        normalized = level.lower().strip()
        msg_lower = message.lower()
        
        if c._layer_loading_active and (
            "fly-through started" in msg_lower
            or "fly-to bounds" in msg_lower
            or "fly-to lon=" in msg_lower
            or "fly-to: complete" in msg_lower
            or "flight started" in msg_lower
        ):
            c._set_layer_loading(False, "Layer ready")

        if normalized == "debug" and (
            "SCENE_DEBUG" in message
            or "addTileLayer request" in message
            or "addDemLayer request" in message
            or "Imagery provider configured" in message
        ):
            self._logger.info("JS(debug): %s", message)
            return

        if "Tile provider error for" in message:
            self._logger.warning("JS: %s", message)
            return
        if normalized == "debug":
            return
        if normalized in {"warn", "warning"}:
            self._logger.warning("JS: %s", message)
            return
        if normalized == "error":
            self._logger.error("JS: %s", message)
            if c._layer_loading_active:
                c._set_layer_loading(False, "Layer load failed")
            return
        self._logger.info("JS: %s", message)


__all__ = ["EventCoordinator"]
