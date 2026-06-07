"""Map overlay controls widget for scene mode and basemap visibility."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QComboBox,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from src_new.clients.desktop_search.controller import DesktopController


class MapOverlayControls(QWidget):
    """Overlay widget for map display controls.

    Provides controls for:
    - Scene mode (3D Globe vs 2D Map)
    - Basemap visibility
    """

    def __init__(self, parent: QWidget, controller: DesktopController):
        """Initialize the map overlay controls."""
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.controller = controller
        self._special_mode_active = False
        self.setObjectName("mapOverlayControls")
        # Restore the original dark-panel style — no QComboBox override so the native macOS dropdown popup keeps its own readable colours.
        self.setStyleSheet(
            """
            QWidget#mapOverlayControls {
                background: rgba(18, 24, 38, 0.85);
                border: 1px solid rgba(120, 160, 220, 0.28);
                border-radius: 8px;
            }
            QLabel {
                color: #e0e8f4;
                font-size: 11px;
                font-weight: 600;
            }
            """
        )
        self.layout_main = QVBoxLayout(self)
        self.layout_main.setContentsMargins(10, 10, 10, 10)
        self.layout_main.setSpacing(8)

        # Scene Mode
        self.scene_mode_combo = QComboBox()
        self.scene_mode_combo.addItems(["3D Globe", "2D Map"])
        self.scene_mode_combo.currentTextChanged.connect(self._on_scene_mode_changed)
        self.layout_main.addWidget(self.scene_mode_combo)

        # Basemap Visibility Toggle
        self.basemap_visibility_combo = QComboBox()
        self.basemap_visibility_combo.addItems(
            ["Hide Map", "Show Map"]
        )
        self.basemap_visibility_combo.currentTextChanged.connect(
            self._on_basemap_visibility_changed
        )
        self.layout_main.addWidget(self.basemap_visibility_combo)

        self.setFixedWidth(200)
        self.hide()

    def set_special_mode(self, active: bool) -> None:
        """Call when comparator or compositor mode is activated/deactivated."""
        self._special_mode_active = bool(active)
        if active:
            self.basemap_visibility_combo.setCurrentText("Hide Map")

    def update_position(self) -> None:
        """Update the overlay position to the top-right inside the map viewport."""
        target_widget = getattr(self.controller, "web_view", None) or self.parentWidget()
        if target_widget and target_widget.isVisible():
            top_right_global = target_widget.mapToGlobal(target_widget.rect().topRight())
            x_pos = top_right_global.x() - self.width() - 14
            y_pos = top_right_global.y() + 18
            self.move(x_pos, y_pos)
            self.raise_()

    def _on_scene_mode_changed(self, text: str) -> None:
        mode = "2d" if "2D" in text else "3d"
        self.controller.web_view.page().runJavaScript(
            f"window.offlineGIS.setSceneMode('{mode}');"
        )

    def _on_basemap_visibility_changed(self, text: str) -> None:
        """Toggle OSM basemap visibility without resetting camera."""
        visible = "Show" in text
        self.controller.web_view.page().runJavaScript(
            f"window.offlineGIS.setBasemapVisibility({str(visible).lower()});"
        )

    # ------------------------------------------------------------------ # Compatibility stubs                                                  # ------------------------------------------------------------------ #

    def update_aoi_stats(self, vertices: int, area_text: str) -> None:
        """No-op: AOI area label is now always shown on the Cesium globe."""
        pass


__all__ = ["MapOverlayControls"]
