from __future__ import annotations

from qtpy.QtCore import QObject, Signal, Slot


class WebBridge(QObject):
    mapClicked = Signal(float, float)
    measurementUpdated = Signal(float)
    jsLogReceived = Signal(str, str)
    searchGeometryChanged = Signal(str, str)
    comparatorPaneStateChanged = Signal(str)
    aoiStatsUpdated = Signal(int, str)
    polygonListUpdated = Signal(str)
    searchResultVisibilityToggled = Signal(str, bool)

    # ── Status-bar signals ───────────────────────────────────────────────
    # Emitted continuously as the user moves the cursor over the globe.
    # lon / lat are in decimal degrees (WGS-84 / EPSG:4326).
    mouseCoordinates = Signal(float, float)

    # Emitted on every camera move: approximate scale denominator + heading + pitch.
    cameraChanged = Signal(float, float, float)

    # Emitted when the renderer starts/stops a frame batch.
    renderBusy = Signal(bool)

    # Emitted with loading progress (0-100) and status message
    loadingProgress = Signal(int, str)

    # Emitted when measurement cursor should be shown/hidden (Qt handles the cursor)
    measureCursorChanged = Signal(bool)

    # Emitted with cursor fraction (0–1) along the completed profile line
    profileCursorMoved = Signal(float)

    # Emitted when fly-through playback changes state: idle, playing, paused, ended
    flyThroughPlaybackStateChanged = Signal(str)

    # Emitted with normalized fly-through playback progress (0–1)
    flyThroughPlaybackProgressChanged = Signal(float)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._measure_cursor_enabled: bool | None = None

    # ------------------------------------------------------------------
    # Slots (called from JavaScript via QWebChannel)
    # ------------------------------------------------------------------

    @Slot(str, bool)
    def on_search_result_visibility_toggled(self, file_path: str, visible: bool) -> None:
        self.searchResultVisibilityToggled.emit(file_path, visible)

    @Slot(int, str)
    def on_aoi_stats_updated(self, vertices: int, area_text: str) -> None:
        self.aoiStatsUpdated.emit(vertices, area_text)

    @Slot(str)
    def on_polygon_list_updated(self, payload_json: str) -> None:
        self.polygonListUpdated.emit(payload_json)

    @Slot(float, float)
    def on_map_click(self, lon: float, lat: float) -> None:
        self.mapClicked.emit(lon, lat)

    @Slot(float)
    def on_measurement(self, meters: float) -> None:
        self.measurementUpdated.emit(meters)

    @Slot(str, str)
    def js_log(self, level: str, message: str) -> None:
        self.jsLogReceived.emit(level, message)

    @Slot(int, str)
    def on_loading_progress(self, percent: int, message: str) -> None:
        """Receive loading progress updates from JavaScript.

        Args:
            percent: Progress percentage (0-100).
            message: Status message describing what's loading.
        """
        self.loadingProgress.emit(percent, message)

    @Slot(str, str)
    def on_search_geometry(self, geometry_type: str, payload_json: str) -> None:
        self.searchGeometryChanged.emit(geometry_type, payload_json)

    @Slot(str)
    def on_comparator_pane_state(self, payload_json: str) -> None:
        self.comparatorPaneStateChanged.emit(payload_json)

    @Slot(float, float)
    def on_mouse_coordinates(self, lon: float, lat: float) -> None:
        self.mouseCoordinates.emit(lon, lat)

    @Slot(float, float, float, float, float, float)
    def on_camera_pose_changed(
        self, lon: float, lat: float, height: float, heading: float, pitch: float, roll: float
    ) -> None:
        if hasattr(self, "controller") and self.controller:
            self.controller._last_camera_state = {
                "lon": float(lon),
                "lat": float(lat),
                "height": float(height),
                "heading": float(heading),
                "pitch": float(pitch),
                "roll": float(roll),
            }

    @Slot(float, float, float)
    def on_camera_changed(self, scale_denominator: float, heading_deg: float, pitch_deg: float) -> None:
        self.cameraChanged.emit(scale_denominator, heading_deg, pitch_deg)

    @Slot(bool)
    def on_render_busy(self, busy: bool) -> None:
        self.renderBusy.emit(busy)

    @Slot(bool)
    def on_measure_cursor(self, enabled: bool) -> None:
        import logging

        enabled = bool(enabled)
        if self._measure_cursor_enabled is enabled:
            return
        self._measure_cursor_enabled = enabled
        logging.getLogger("desktop.bridge").info(
            "[CURSOR_DEBUG] on_measure_cursor slot called enabled=%s", enabled
        )
        self.measureCursorChanged.emit(enabled)

    @Slot(float)
    def on_profile_cursor(self, frac: float) -> None:
        self.profileCursorMoved.emit(float(frac))

    @Slot(str)
    def on_fly_through_playback_state(self, state: str) -> None:
        self.flyThroughPlaybackStateChanged.emit(str(state))

    @Slot(float)
    def on_fly_through_playback_progress(self, progress: float) -> None:
        self.flyThroughPlaybackProgressChanged.emit(float(progress))
