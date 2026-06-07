"""Layer compositor overlay widget for adjusting layer opacities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtCore import QSignalBlocker, Qt
from qtpy.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
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
        combo.setMinimumWidth(170)
        combo.setMaximumWidth(190)
        for layer in layers:
            combo.addItem(str(layer.get("label") or "Layer"), layer.get("path"))
        row.addWidget(combo, 0)

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
        }

        combo.currentIndexChanged.connect(
            lambda _index, kind_name=kind: self._sync_kind_slider(kind_name)
        )
        slider.valueChanged.connect(
            lambda value, kind_name=kind: self._on_kind_slider_changed(kind_name, value)
        )

        if layers:
            self._sync_kind_slider(kind)
        else:
            combo.setEnabled(False)
            slider.setEnabled(False)
            value_label.setText("n/a")

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

    def apply_state(self, _state_dict: dict) -> None:
        """Apply saved state to the layer compositor overlay."""
        return


__all__ = ["LayerCompositorOverlay"]

