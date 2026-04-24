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

    @Slot(str, str)
    def on_search_geometry(self, geometry_type: str, payload_json: str) -> None:
        self.searchGeometryChanged.emit(geometry_type, payload_json)

    @Slot(str)
    def on_comparator_pane_state(self, payload_json: str) -> None:
        self.comparatorPaneStateChanged.emit(payload_json)
