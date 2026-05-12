"""Map overlay controls widget for scene mode and polygon visibility."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from src_new.clients.desktop_search.app_mode import DesktopAppMode

if TYPE_CHECKING:
    from src_new.clients.desktop_search.controller import DesktopController


class MapOverlayControls(QWidget):
    """Overlay widget for map display controls.

    Provides controls for:
    - Scene mode (3D Globe vs 2D Map)
    - Search polygon visibility
    - Area of Interest (AOI) statistics display
    """

    def __init__(self, parent: QWidget, controller: DesktopController):
        """Initialize the map overlay controls."""
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.controller = controller
        self._special_mode_active = (
            False  # True when comparator or compositor is active
        )
        self.setObjectName("mapOverlayControls")
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
            QCheckBox {
                color: #e0e8f4;
                font-size: 10px;
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
        )  # Default to "Hide Map" for faster startup
        self.basemap_visibility_combo.currentTextChanged.connect(
            self._on_basemap_visibility_changed
        )
        self.layout_main.addWidget(self.basemap_visibility_combo)

        # Polygon Visibility (always visible; enabled when polygon exists)
        self.polygon_visibility_checkbox = QCheckBox("Show Search AOI Polygon")
        self.polygon_visibility_checkbox.setChecked(True)
        self.polygon_visibility_checkbox.setEnabled(False)
        self.polygon_visibility_checkbox.toggled.connect(
            self._on_polygon_visibility_toggled
        )
        self.layout_main.addWidget(self.polygon_visibility_checkbox)

        # Hide AOI checkbox in server mode as searching is client-only
        if self.controller.app_mode == DesktopAppMode.SERVER:
            self.polygon_visibility_checkbox.setVisible(False)
        else:
            self.polygon_visibility_checkbox.setVisible(True)

        # AOI Stats
        self.aoi_stats_label = QLabel("Area: 0 m\u00b2 | Vertices: 0")
        self.aoi_stats_label.setWordWrap(True)
        self.aoi_stats_label.setVisible(False)
        self.layout_main.addWidget(self.aoi_stats_label)

        self._last_aoi_vertices = 0
        self._last_aoi_area_text = "0 m\u00b2"

        self.setFixedWidth(200)

        # Connect bridge signals
        self.controller.bridge.aoiStatsUpdated.connect(self.update_aoi_stats)

        self.hide()

    def set_special_mode(self, active: bool) -> None:
        """Call when comparator or compositor mode is activated/deactivated.

        Keeps the AOI checkbox visible and hides stats when needed.
        """
        self._special_mode_active = bool(active)
        self._apply_aoi_visibility()

    def update_position(self) -> None:
        """Update the overlay position to top-right corner of parent widget."""
        parent_widget = self.parentWidget()
        if parent_widget and parent_widget.isVisible():
            # For Tool windows, move() expects global screen coordinates.
            # Map the parent's top-right corner to global space.
            top_right_global = parent_widget.mapToGlobal(parent_widget.rect().topRight())
            
            # Position near the top-right edge with a 10px internal margin
            x_pos = top_right_global.x() - self.width() - 10
            y_pos = top_right_global.y() + 10
            
            self.move(x_pos, y_pos)
            self.raise_()

    def _on_scene_mode_changed(self, text: str) -> None:
        mode = "2d" if "2D" in text else "3d"
        self.controller.web_view.page().runJavaScript(
            f"window.offlineGIS.setSceneMode('{mode}');"
        )

    def _on_basemap_visibility_changed(self, text: str) -> None:
        """Toggle OSM basemap visibility without resetting camera."""
        visible = "Show" in text  # "Show Map" = True, "Hide Map" = False
        self.controller.web_view.page().runJavaScript(
            f"window.offlineGIS.setBasemapVisibility({str(visible).lower()});"
        )

    def _on_polygon_visibility_toggled(self, checked: bool) -> None:
        self.controller.web_view.page().runJavaScript(
            f"window.offlineGIS.setSearchPolygonVisibility({str(checked).lower()});"
        )

    def update_aoi_stats(self, vertices: int, area_text: str) -> None:
        """Update the AOI statistics display."""
        self._last_aoi_vertices = int(vertices)
        self._last_aoi_area_text = str(area_text)
        self._apply_aoi_visibility()

    def _apply_aoi_visibility(self) -> None:
        vertices = self._last_aoi_vertices
        area_text = self._last_aoi_area_text
        self.polygon_visibility_checkbox.setVisible(True)
        self.polygon_visibility_checkbox.setEnabled(vertices >= 3)
        if vertices >= 3 and not self._special_mode_active:
            self.aoi_stats_label.setText(f"Area: {area_text}\nVertices: {vertices}")
            self.aoi_stats_label.setVisible(True)
        else:
            self.aoi_stats_label.setVisible(False)

        self.adjustSize()
        main_win = self.window()
        if hasattr(main_win, "_position_compositor_overlay"):
            main_win._position_compositor_overlay()


__all__ = ["MapOverlayControls"]
