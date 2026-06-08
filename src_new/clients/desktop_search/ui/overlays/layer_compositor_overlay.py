"""Layer compositor overlay widget for adjusting layer opacities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtCore import QSignalBlocker, Qt
from qtpy.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from src_new.clients.desktop_search.controller import DesktopController


class LayerCompositorOverlay(QWidget):
    """Overlay widget for adjusting layer opacities in the compositor mode."""

    def __init__(self, parent: QWidget, controller: DesktopController):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.controller = controller
        self.selected_layer_path = None
        self._saved_visibility = None
        self._layer_alphas: dict[str, int] = {}
        self._selecting_guard = False
        self.active_picker = None

        self.setObjectName("compositorOverlay")
        self.setStyleSheet(
            """
            QWidget#compositorOverlay {
                background: rgba(248, 250, 252, 0.95);
                border: 1px solid #c9d3df;
                border-radius: 8px;
                min-width: 320px;
            }
            QFrame#layerKindCard {
                background: rgba(255, 255, 255, 0.95);
                border: 1px solid #d7dfe9;
                border-radius: 6px;
            }
            QLabel {
                color: #1a2a3a;
                font-size: 12px;
                font-weight: 600;
            }
            QComboBox, QSlider {
                min-height: 24px;
            }
            """
        )
        self.setFixedWidth(340)

        self.layout_main = QVBoxLayout(self)
        self.layout_main.setContentsMargins(10, 10, 10, 10)
        self.layout_main.setSpacing(8)

        # Title Row
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(4)
        
        title = QLabel("Layer Compositor")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(title, 1)
        
        close_btn = QPushButton("×")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #64748b;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #ef4444;
            }
        """)
        close_btn.clicked.connect(self.close_compositor)
        title_row.addWidget(close_btn, 0)
        self.layout_main.addLayout(title_row)

        # Card Frame
        self.card = QFrame(self)
        self.card.setObjectName("layerKindCard")
        self.card_layout = QVBoxLayout(self.card)
        self.card_layout.setContentsMargins(10, 10, 10, 10)
        self.card_layout.setSpacing(8)

        # Instructions
        self.instruction_label = QLabel("Click an imagery layer on the map or select below:")
        self.instruction_label.setStyleSheet("color: #64748b; font-weight: normal; font-size: 11px;")
        self.card_layout.addWidget(self.instruction_label)

        # Layer Selection Row
        combo_row = QHBoxLayout()
        combo_row.setSpacing(8)
        combo_row.addWidget(QLabel("Imagery:"))
        
        self.combo = QComboBox(self.card)
        self.combo.setMinimumWidth(180)
        combo_row.addWidget(self.combo, 1)
        self.card_layout.addLayout(combo_row)

        # Opacity Slider Row
        slider_row = QHBoxLayout()
        slider_row.setSpacing(8)
        slider_row.addWidget(QLabel("Opacity:"))

        self.slider = QSlider(Qt.Orientation.Horizontal, self.card)
        self.slider.setRange(0, 100)
        self.slider.setValue(100)
        slider_row.addWidget(self.slider, 1)

        self.value_label = QLabel("100%")
        self.value_label.setFixedWidth(45)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        slider_row.addWidget(self.value_label)
        self.card_layout.addLayout(slider_row)

        self.layout_main.addWidget(self.card)
        self.layout_main.addStretch()

        # Connect events
        self.combo.currentIndexChanged.connect(self._on_combo_index_changed)
        self.slider.valueChanged.connect(self._on_slider_changed)

        self.hide()

    def update_layers(self) -> None:
        """Refresh the imagery layer combobox list."""
        with QSignalBlocker(self.combo):
            self.combo.clear()
            self.combo.addItem("Select Imagery Layer...", "")
            
            imagery_layers = self.controller.available_layer_opacity_options("imagery")
            for layer in imagery_layers:
                self.combo.addItem(str(layer.get("label") or "Layer"), layer.get("path"))

        # Re-sync slider for currently selected layer
        self.select_imagery_layer(self.selected_layer_path)

    def _on_combo_index_changed(self) -> None:
        path = self.combo.currentData()
        self.select_imagery_layer(path)

    def _on_slider_changed(self, value: int) -> None:
        if not self.selected_layer_path:
            return
        self._layer_alphas[self.selected_layer_path] = value
        self.value_label.setText(f"{value}%")
        # Apply the setting via controller
        self.controller.apply_layer_compositor_settings(False, [], {self.selected_layer_path: value / 100.0})

    def select_imagery_layer(self, path: str | None) -> None:
        if self._selecting_guard:
            return
        self._selecting_guard = True
        try:
            # 1. Reset previous asset opacity to 100%
            if self.selected_layer_path and self.selected_layer_path != path:
                self.controller._run_js_call("setLayerAlpha", self.selected_layer_path, 1.0)
                if self.selected_layer_path in self._layer_alphas:
                    self._layer_alphas[self.selected_layer_path] = 100

            self.selected_layer_path = path

            if not path:
                self.slider.setEnabled(False)
                self.value_label.setText("n/a")
                with QSignalBlocker(self.combo):
                    self.combo.setCurrentIndex(0)
                self.controller._set_status("Please select or click an imagery layer.")
                return

            # Update combo selection index
            idx = self.combo.findData(path)
            if idx >= 0:
                with QSignalBlocker(self.combo):
                    self.combo.setCurrentIndex(idx)

            # Enable slider and set value
            self.slider.setEnabled(True)
            current_val = self._layer_alphas.get(path, 100)
            with QSignalBlocker(self.slider):
                self.slider.setValue(current_val)
            self.value_label.setText(f"{current_val}%")

            # Apply this opacity to the selected layer
            self.controller._run_js_call("setLayerAlpha", path, current_val / 100.0)

            self.controller._set_status(f"Selected: {self.combo.currentText()}. Adjust slider for opacity.")
        finally:
            self._selecting_guard = False

    def handle_map_click(self, lon: float, lat: float) -> bool:
        if not self.active_picker:
            return False
            
        self.controller._logger.info("Layer Compositor: handle_map_click active_picker=%s lon=%f lat=%f", self.active_picker, lon, lat)
            
        target_path = None
        best_dist = float("inf")
        best_path_fallback = None

        for path, asset in self.controller._search_result_assets_by_path.items():
            is_dem = self.controller._is_dem_asset(asset)
            asset_kind = "dem" if is_dem else "imagery"
            if asset_kind != "imagery":
                continue
            bounds = self.controller._asset_bounds(asset)
            if bounds:
                west = bounds.get("west", 0.0)
                south = bounds.get("south", 0.0)
                east = bounds.get("east", 0.0)
                north = bounds.get("north", 0.0)
                
                # Small tolerance check
                width = abs(east - west)
                height = abs(north - south)
                tol_x = max(0.05, width * 0.05)
                tol_y = max(0.05, height * 0.05)
                
                if (west - tol_x) <= lon <= (east + tol_x) and (south - tol_y) <= lat <= (north + tol_y):
                    target_path = path
                    self.controller._logger.info("Layer Compositor: Picked asset path=%s via direct bounds check", path)
                    break

                # Centroid fallback
                center_lon = (west + east) / 2.0
                center_lat = (south + north) / 2.0
                dist = ((lon - center_lon) ** 2 + (lat - center_lat) ** 2) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    best_path_fallback = path

        if not target_path and best_path_fallback:
            target_path = best_path_fallback
            self.controller._logger.info("Layer Compositor: Picked closest asset path=%s via distance=%f", target_path, best_dist)
                    
        if target_path:
            self.select_imagery_layer(target_path)
            return True
            
        self.controller._logger.warning("Layer Compositor: No asset found at clicked coordinate (lon=%f, lat=%f)", lon, lat)
        return False

    def initialize_compositor_view(self) -> None:
        """Called when Layer Compositor toggles ON: switch to chosen view mode, show imagery."""
        # 1. Read current view mode (2D/3D) from the main Display Settings dropdown
        mode = str(self.controller.panel.rgb_view_mode_combo.currentData() or "3d")
        self.controller._run_js_call("setSceneModeInternal", mode)

        # 2. Hide search markers and annotations
        self.controller._run_js_call("setSearchOverlayVisible", False)
        self.controller._run_js_call("setAnnotationVisibility", False)

        # 3. Always enable picking and set measurement crosshair cursor
        self.active_picker = "imagery"
        self.controller._set_measurement_cursor_enabled(True)

        # 4. Make all available imagery layers visible at 100% opacity on the map
        imagery_layers = self.controller.available_layer_opacity_options("imagery")
        for layer in imagery_layers:
            path = layer.get("path")
            if path:
                self.controller._run_js_call("setLayerVisibility", path, True)
                self.controller._run_js_call("setLayerAlpha", path, 1.0)
                self.controller._search_layer_visibility[path] = True
                self._layer_alphas[path] = 100

        # Update the search results UI list checked items
        self.controller.panel.update_search_results(
            list(self.controller._search_result_assets_by_path.values()),
            self.controller._search_layer_visibility,
        )

        # 5. Populate and reset combo box selection
        self.update_layers()

        self.controller._set_status("Layer Compositor active. Click an imagery layer on the map or select from list.")

    def restore_pre_compositor_state(self) -> None:
        """Restore map visibility and reset opacities when Layer Compositor is disabled."""
        self.controller._run_js_call("setSearchOverlayVisible", True)
        self.controller._run_js_call("setAnnotationVisibility", True)

        if self._saved_visibility is not None:
            # Restore visibility of all assets
            for path, visible in self._saved_visibility.items():
                self.controller._search_layer_visibility[path] = visible
                self.controller._run_js_call("setLayerVisibility", path, visible)
            self._saved_visibility = None
            
            # Update search results UI list checked items
            self.controller.panel.update_search_results(
                list(self.controller._search_result_assets_by_path.values()),
                self.controller._search_layer_visibility,
            )
            
        # Reset alphas of all assets to 1.0 in JS
        for path in self.controller._search_result_assets_by_path:
            self.controller._run_js_call("setLayerAlpha", path, 1.0)
            
        # Reset active picker and crosshair cursor
        self.active_picker = None
        self.controller._set_measurement_cursor_enabled(False)

    def close_compositor(self) -> None:
        window = self.controller.panel.window()
        if hasattr(window, "toolbar_actions"):
            action = window.toolbar_actions.get("Layer Compositor")
            if action:
                action.setChecked(False)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() == Qt.MouseButtons(Qt.MouseButton.LeftButton) and hasattr(self, "_drag_pos"):
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def apply_state(self, _state_dict: dict) -> None:
        """Apply saved state to the layer compositor overlay."""
        return


__all__ = ["LayerCompositorOverlay"]
