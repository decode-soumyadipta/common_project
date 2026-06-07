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
        self.active_picker = None
        self._saved_visibility = None
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
            QFrame#layerSummaryRow {
                background: #ffffff;
                border: 1px solid #e6ebf2;
                border-radius: 4px;
            }
            QLabel {
                color: #1a2a3a;
                font-size: 12px;
                font-weight: 600;
            }
            QLabel#layerSummaryTag {
                color: #5a6a7e;
                font-size: 11px;
                font-weight: 700;
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

        title = QLabel("Layer Opacities")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout_main.addWidget(title)

        self._kind_controls: dict[str, dict[str, object]] = {}
        self._layer_alphas: dict[str, int] = {}
        self._dynamic_widgets: list[QWidget] = []
        self.hide()

    def update_layers(self) -> None:
        """Refresh the overlay with current imagery and DEM layer options."""
        self._clear_dynamic_content()

        imagery_layers = self.controller.available_layer_opacity_options("imagery")
        dem_layers = self.controller.available_layer_opacity_options("dem")

        controls_frame = QFrame(self)
        controls_frame.setObjectName("layerKindCard")
        controls_layout = QVBoxLayout(controls_frame)
        controls_layout.setContentsMargins(10, 10, 10, 10)
        controls_layout.setSpacing(8)

        controls_title = QLabel("Select a layer type")
        controls_layout.addWidget(controls_title)
        controls_layout.addWidget(self._build_kind_picker("imagery", imagery_layers))
        controls_layout.addWidget(self._build_kind_picker("dem", dem_layers))

        self.layout_main.addWidget(controls_frame)
        self._dynamic_widgets.append(controls_frame)

        self.layout_main.addStretch()
        self.adjustSize()

    def _clear_dynamic_content(self) -> None:
        while self.layout_main.count() > 1:
            item = self.layout_main.takeAt(1)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            layout = item.layout()
            if layout is not None:
                self._delete_layout(layout)
        self._dynamic_widgets.clear()
        self._kind_controls.clear()

    def _delete_layout(self, layout: QVBoxLayout | QHBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            nested = item.layout()
            if nested is not None:
                self._delete_layout(nested)
        layout.deleteLater()

    def _build_kind_picker(self, kind: str, layers: list[dict[str, object]]) -> QWidget:
        card = QFrame(self)
        card.setObjectName("layerKindCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 10, 10, 10)
        card_layout.setSpacing(8)

        title = QLabel("Imagery Layers" if kind == "imagery" else "DEM Layers")
        card_layout.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch(1)
        row.addWidget(QLabel("Layer:"))

        combo = QComboBox(card)
        combo.setMinimumWidth(110)
        combo.setMaximumWidth(130)
        for layer in layers:
            combo.addItem(str(layer.get("label") or "Layer"), layer.get("path"))
        row.addWidget(combo, 0)

        pick_btn = QPushButton("Pick", card)
        pick_btn.setCheckable(True)
        pick_btn.setFixedWidth(50)
        pick_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                border: 1px solid #c9d3df;
                border-radius: 4px;
                padding: 2px;
                font-size: 11px;
                font-weight: bold;
                color: #475569;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
            }
            QPushButton:checked {
                background-color: #ffb300;
                color: #1a2a3a;
                border: 1px solid #ff9100;
            }
        """)
        row.addWidget(pick_btn, 0)

        card_layout.addLayout(row)

        slider_row = QHBoxLayout()
        slider_row.setSpacing(8)
        slider_row.addStretch(1)
        slider_row.addWidget(QLabel("Opacity:"))

        slider = QSlider(Qt.Orientation.Horizontal, card)
        slider.setRange(0, 100)
        slider.setValue(100)
        slider.setMaximumWidth(170)
        slider_row.addWidget(slider, 0)

        value_label = QLabel("100%")
        value_label.setFixedWidth(52)
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        slider_row.addWidget(value_label)
        card_layout.addLayout(slider_row)

        self._kind_controls[kind] = {
            "combo": combo,
            "slider": slider,
            "value_label": value_label,
            "pick_btn": pick_btn,
        }

        combo.currentIndexChanged.connect(
            lambda _index, kind_name=kind: self._on_combo_index_changed(kind_name)
        )
        slider.valueChanged.connect(
            lambda value, kind_name=kind: self._on_kind_slider_changed(kind_name, value)
        )
        pick_btn.clicked.connect(
            lambda checked, kind_name=kind: self._on_pick_btn_clicked(kind_name, checked)
        )

        if layers:
            self._sync_kind_slider(kind)
        else:
            combo.setEnabled(False)
            slider.setEnabled(False)
            value_label.setText("n/a")
            pick_btn.setEnabled(False)

        return card

    def _sync_kind_slider(self, kind: str) -> None:
        controls = self._kind_controls.get(kind)
        if not controls:
            return
        combo = controls["combo"]
        slider = controls["slider"]
        value_label = controls["value_label"]
        if not isinstance(combo, QComboBox) or not isinstance(slider, QSlider):
            return
        if combo.count() <= 0:
            slider.setEnabled(False)
            return

        path = str(combo.currentData() or "")
        if not path:
            slider.setEnabled(False)
            return

        slider.setEnabled(True)
        target_value = int(self._layer_alphas.get(path, slider.value()))
        with QSignalBlocker(slider):
            slider.setValue(max(slider.minimum(), min(slider.maximum(), target_value)))
        if isinstance(value_label, QLabel):
            value_label.setText(f"{slider.value()}%")

    def _on_kind_slider_changed(self, kind: str, value: int) -> None:
        controls = self._kind_controls.get(kind)
        if not controls:
            return
        combo = controls["combo"]
        value_label = controls["value_label"]
        if not isinstance(combo, QComboBox):
            return
        path = str(combo.currentData() or "")
        if not path:
            return
        self._layer_alphas[path] = int(value)
        if isinstance(value_label, QLabel):
            value_label.setText(f"{value}%")
        self._apply_settings(path, value)

    def _apply_settings(self, path: str, value: int) -> None:
        if not self.isVisible() or not path:
            return
        self.controller.apply_layer_compositor_settings(False, [], {path: value / 100.0})

    def _build_summary_row(self, index: int, layer: dict[str, object]) -> QWidget:
        row = QFrame(self)
        row.setObjectName("layerSummaryRow")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(8, 6, 8, 6)
        row_layout.setSpacing(8)

        label_text = str(layer.get("label") or layer.get("path") or "Layer")
        if not layer.get("visible"):
            label_text += " (hidden)"
        name_label = QLabel(f"{index}. {label_text}")
        name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row_layout.addWidget(name_label, 1)

        kind_text = str(layer.get("kind") or "").strip().upper() or "LAYER"
        kind_label = QLabel(kind_text)
        kind_label.setObjectName("layerSummaryTag")
        kind_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row_layout.addWidget(kind_label, 0)

        return row

    def _on_combo_index_changed(self, kind: str) -> None:
        self._sync_kind_slider(kind)
        self.focus_and_show_only_selected()

    def _on_pick_btn_clicked(self, kind: str, checked: bool) -> None:
        if checked:
            # Uncheck the other picker
            other_kind = "dem" if kind == "imagery" else "imagery"
            other_ctrl = self._kind_controls.get(other_kind)
            if other_ctrl and "pick_btn" in other_ctrl:
                other_ctrl["pick_btn"].setChecked(False)
            
            self.active_picker = kind
            
            # Save visibility if not already saved
            if self._saved_visibility is None:
                self._saved_visibility = {}
                for path in self.controller._search_result_assets_by_path:
                    self._saved_visibility[path] = bool(self.controller._search_layer_visibility.get(path, False))
            
            # Show ONLY layers of the active picker kind on the map
            for path, asset in self.controller._search_result_assets_by_path.items():
                is_dem = self.controller._is_dem_asset(asset)
                asset_kind = "dem" if is_dem else "imagery"
                visible = (asset_kind == kind)
                self.controller._run_js_call("setLayerVisibility", path, visible)
                
            # Set cursor to native cross cursor on the map viewport
            self.controller._set_measurement_cursor_enabled(True)
            self.controller.panel.log(f"Compositor: Click on an {kind} asset on the map to pick it.")
        else:
            if self.active_picker == kind:
                self.active_picker = None
                self.controller._set_measurement_cursor_enabled(False)
                # Restore original visibility
                if self._saved_visibility is not None:
                    for path, visible in self._saved_visibility.items():
                        self.controller._run_js_call("setLayerVisibility", path, visible)
                    self._saved_visibility = None

    def focus_and_show_only_selected(self) -> None:
        imagery_ctrl = self._kind_controls.get("imagery")
        dem_ctrl = self._kind_controls.get("dem")
        if not imagery_ctrl or not dem_ctrl:
            return
        
        img_combo = imagery_ctrl.get("combo")
        dem_combo = dem_ctrl.get("combo")
        if not img_combo or not dem_combo:
            return
            
        img_path = img_combo.currentData()
        dem_path = dem_combo.currentData()
        if not img_path or not dem_path:
            return
            
        # Set only these two visible on the map, hide everything else
        for path in list(self.controller._search_layer_visibility.keys()):
            visible = (path == img_path or path == dem_path)
            self.controller._search_layer_visibility[path] = visible
            self.controller._run_js_call("setLayerVisibility", path, visible)
            
        # Update the search results UI list checked items
        self.controller.panel.update_search_results(
            list(self.controller._search_result_assets_by_path.values()),
            self.controller._search_layer_visibility,
        )
        
        # Calculate union of bounds and zoom to fit
        img_asset = self.controller._search_result_assets_by_path.get(img_path)
        dem_asset = self.controller._search_result_assets_by_path.get(dem_path)
        
        img_bounds = self.controller._asset_bounds(img_asset) if img_asset else None
        dem_bounds = self.controller._asset_bounds(dem_asset) if dem_asset else None
        
        union_bounds = None
        if img_bounds and dem_bounds:
            union_bounds = {
                "west": min(img_bounds["west"], dem_bounds["west"]),
                "south": min(img_bounds["south"], dem_bounds["south"]),
                "east": max(img_bounds["east"], dem_bounds["east"]),
                "north": max(img_bounds["north"], dem_bounds["north"]),
            }
        elif img_bounds:
            union_bounds = img_bounds
        elif dem_bounds:
            union_bounds = dem_bounds
            
        if union_bounds:
            self.controller._run_js_call(
                "instantFocusBounds",
                union_bounds["west"],
                union_bounds["south"],
                union_bounds["east"],
                union_bounds["north"],
            )
            self.controller.panel.log("Focused and draped selected imagery and DEM assets.")

    def handle_map_click(self, lon: float, lat: float) -> bool:
        if not self.active_picker:
            return False
            
        # Search through assets to find one of active_picker kind that covers (lon, lat)
        target_path = None
        for path, asset in self.controller._search_result_assets_by_path.items():
            is_dem = self.controller._is_dem_asset(asset)
            asset_kind = "dem" if is_dem else "imagery"
            if asset_kind != self.active_picker:
                continue
            bounds = self.controller._asset_bounds(asset)
            if bounds:
                west = bounds.get("west", 0.0)
                south = bounds.get("south", 0.0)
                east = bounds.get("east", 0.0)
                north = bounds.get("north", 0.0)
                if west <= lon <= east and south <= lat <= north:
                    target_path = path
                    break
                    
        if target_path:
            # Dropdown sync: Select in combo box
            controls = self._kind_controls.get(self.active_picker)
            if controls and "combo" in controls:
                combo = controls["combo"]
                idx = combo.findData(target_path)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                    
            # Turn off picker
            btn = controls.get("pick_btn")
            if btn:
                btn.setChecked(False)
                
            self.active_picker = None
            self.controller._set_measurement_cursor_enabled(False)
            
            # Apply visible layers for selected ones
            self.focus_and_show_only_selected()
            return True
            
        return False

    def apply_state(self, _state_dict: dict) -> None:
        """Apply saved state to the layer compositor overlay."""
        return


__all__ = ["LayerCompositorOverlay"]

