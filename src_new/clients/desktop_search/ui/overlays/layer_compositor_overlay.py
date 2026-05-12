"""Layer compositor overlay widget for adjusting layer opacities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from src_new.clients.desktop_search.controller import DesktopController


class LayerCompositorOverlay(QWidget):
    """Overlay widget for adjusting layer opacities in the compositor mode.

    This widget displays sliders for each active layer, allowing users to
    adjust the opacity of individual layers in real-time.
    """

    def __init__(self, parent: QWidget, controller: DesktopController):
        """Initialize the layer compositor overlay.

        Args:
            parent: Parent widget (typically the web view).
            controller: Desktop controller instance for layer management.
        """
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.controller = controller
        self.setObjectName("compositorOverlay")
        self.setStyleSheet(
            """
            QWidget#compositorOverlay {
                background: rgba(248, 250, 252, 0.9);
                border: 1px solid #c9d3df;
                border-radius: 8px;
            }
            QLabel {
                color: #1a2a3a;
                font-size: 12px;
                font-weight: 600;
            }
            """
        )
        self.layout_main = QVBoxLayout(self)
        self.layout_main.setContentsMargins(10, 10, 10, 10)
        self.layout_main.setSpacing(8)

        title = QLabel("Layer Opacities")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout_main.addWidget(title)

        self.sliders_layout = QVBoxLayout()
        self.layout_main.addLayout(self.sliders_layout)

        self.sliders: dict[str, QSlider] = {}
        self.hide()

    def update_layers(self) -> None:
        """Update the overlay with current active layers and their sliders.

        Clears existing sliders and creates new ones for all searched layers.
        Each slider controls the opacity of its corresponding layer.
        """
        layers = self.controller.available_swipe_layer_options()

        # Clear old sliders
        while self.sliders_layout.count():
            item = self.sliders_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
                item.layout().deleteLater()

        self.sliders.clear()

        if not layers:
            no_layers_label = QLabel("No layers found.")
            self.sliders_layout.addWidget(no_layers_label)
            return

        for layer in layers:
            row = QHBoxLayout()
            base_label = str(layer.get("label") or "Layer")
            if not layer.get("visible"):
                base_label += " (hidden)"
            label = QLabel(base_label)
            label.setFixedWidth(120)
            row.addWidget(label)

            slider = QSlider(Qt.Orientation.Horizontal, self)
            slider.setRange(0, 100)
            slider.setValue(100)
            row.addWidget(slider)

            val_label = QLabel("100%")
            val_label.setFixedWidth(40)
            row.addWidget(val_label)

            slider.valueChanged.connect(
                lambda value, value_label=val_label, layer_path=layer["path"]: (
                    self._on_slider_changed(
                        value,
                        value_label,
                        layer_path,
                    )
                )
            )

            self.sliders[layer["path"]] = slider
            self.sliders_layout.addLayout(row)

    def _on_slider_changed(self, value: int, label: QLabel, path: str) -> None:
        """Handle slider value changes.

        Args:
            value: New slider value (0-100).
            label: Label widget to update with percentage.
            path: File path of the layer being adjusted.
        """
        label.setText(f"{value}%")
        self._apply_settings()

    def _apply_settings(self, *args: object) -> None:
        """Apply current slider values to the layer compositor.

        Args:
            *args: Unused arguments from signal connections.
        """
        if not self.isVisible():
            return
        layer_alphas = {
            path: slider.value() / 100.0 for path, slider in self.sliders.items()
        }
        # Only set opacity. Pass enable_swipe=False and empty swipe_paths.
        self.controller.apply_layer_compositor_settings(False, [], layer_alphas)

    def apply_state(self, state_dict: dict) -> None:
        """Apply saved state to the layer compositor overlay.

        Args:
            state_dict: Dictionary containing saved state (currently unused).
        """
        pass


__all__ = ["LayerCompositorOverlay"]
