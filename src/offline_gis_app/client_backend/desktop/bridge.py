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

    # ── Status-bar signals ───────────────────────────────────────────────
    # Emitted continuously as the user moves the cursor over the globe.
    # lon / lat are in decimal degrees (WGS-84 / EPSG:4326).
    # elevation_m is terrain height in metres; -9999 when not available.
    mouseCoordinates = Signal(float, float, float)

    # Emitted on every camera move: approximate scale denominator + heading.
    cameraChanged = Signal(float, float)

    # Emitted when the renderer starts/stops a frame batch.
    renderBusy = Signal(bool)
    
    # Emitted with loading progress (0-100) and status message
    loadingProgress = Signal(int, str)

    # ------------------------------------------------------------------
    # Slots (called from JavaScript via QWebChannel)
    # ------------------------------------------------------------------

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

    @Slot(float, float, float)
    def on_mouse_coordinates(self, lon: float, lat: float, elevation_m: float) -> None:
        self.mouseCoordinates.emit(lon, lat, elevation_m)

    @Slot(float, float)
    def on_camera_changed(self, scale_denominator: float, heading_deg: float) -> None:
        self.cameraChanged.emit(scale_denominator, heading_deg)

    @Slot(bool)
    def on_render_busy(self, busy: bool) -> None:
        self.renderBusy.emit(busy)
