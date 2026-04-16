from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot


class WebBridge(QObject):
    mapClicked = Signal(float, float)
    measurementUpdated = Signal(float)
    jsLogReceived = Signal(str, str)

    @Slot(float, float)
    def on_map_click(self, lon: float, lat: float) -> None:
        self.mapClicked.emit(lon, lat)

    @Slot(float)
    def on_measurement(self, meters: float) -> None:
        self.measurementUpdated.emit(meters)

    @Slot(str, str)
    def js_log(self, level: str, message: str) -> None:
        self.jsLogReceived.emit(level, message)
