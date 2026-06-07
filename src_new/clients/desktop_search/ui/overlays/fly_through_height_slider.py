"""Frosted-glass vertical height slider overlay for fly-through navigation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtCore import Qt, QSignalBlocker
from qtpy.QtWidgets import (
    QFrame,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from src_new.clients.desktop_search.controller import DesktopController


class FlyThroughHeightSlider(QWidget):
    """Frosted-glass vertical height slider overlay for fly-through navigation."""

    def __init__(self, parent: QWidget, controller: DesktopController):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.controller = controller
        self._active = False
        self._height_value = 900

        self.setObjectName("flyThroughHeightSliderWidget")
        self.setStyleSheet(
            """
            QWidget#flyThroughHeightSliderWidget {
                background: transparent;
            }
            QFrame#flyThroughHeightCard {
                background: rgba(255, 255, 255, 0.14);
                border: 1px solid rgba(255, 255, 255, 0.26);
                border-radius: 14px;
            }
            QLabel#flyThroughHeightLabel {
                color: #ffffff;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.3px;
            }
            QLabel#flyThroughHeightValueLabel {
                color: #ffffff;
                font-size: 10px;
                font-weight: 600;
            }
            QSlider#flyThroughHeightSlider::groove:vertical {
                background: rgba(255, 255, 255, 0.20);
                border-radius: 3px;
                width: 6px;
            }
            QSlider#flyThroughHeightSlider::sub-page:vertical {
                background: rgba(255, 255, 255, 0.82);
                border-radius: 3px;
            }
            QSlider#flyThroughHeightSlider::add-page:vertical {
                background: rgba(255, 255, 255, 0.12);
                border-radius: 3px;
            }
            QSlider#flyThroughHeightSlider::handle:vertical {
                background: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.55);
                height: 14px;
                margin: 0 -6px;
                border-radius: 7px;
            }
            QSlider#flyThroughHeightSlider::handle:vertical:hover {
                background: #f8fbff;
            }
            """
        )

        card = QFrame(self)
        card.setObjectName("flyThroughHeightCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 12, 10, 12)
        card_layout.setSpacing(8)

        self.height_label = QLabel("Height")
        self.height_label.setObjectName("flyThroughHeightLabel")
        self.height_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        card_layout.addWidget(self.height_label)

        self.height_slider = QSlider(Qt.Orientation.Vertical)
        self.height_slider.setObjectName("flyThroughHeightSlider")
        self.height_slider.setRange(1, 2000)
        self.height_slider.setValue(900)
        self.height_slider.setSingleStep(25)
        self.height_slider.setPageStep(100)
        self.height_slider.setTickPosition(QSlider.TickPosition.TicksRight)
        self.height_slider.setTickInterval(200)
        self.height_slider.setToolTip("Adjust camera height above ground during flight.")
        self.height_slider.valueChanged.connect(self._on_height_changed)
        card_layout.addWidget(self.height_slider, 1)

        self.height_value_label = QLabel("900 m")
        self.height_value_label.setObjectName("flyThroughHeightValueLabel")
        self.height_value_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        card_layout.addWidget(self.height_value_label)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(card)

        self.setFixedWidth(70)
        self.setFixedHeight(240)
        self.hide()

    def set_fly_through_active(self, active: bool) -> None:
        """Show or hide the height slider widget and reset height when re-enabled."""
        self._active = bool(active)
        self.setVisible(self._active)
        if self._active:
            self.set_height(900)
            self.update_position()

    def set_height(self, value: float) -> None:
        """Update height slider and labels programmatically."""
        height = max(1.0, min(2000.0, float(value)))
        self._height_value = int(round(height))
        with QSignalBlocker(self.height_slider):
            self.height_slider.setValue(self._height_value)
        self.height_value_label.setText(f"{self._height_value} m")

    def update_position(self) -> None:
        """Anchor the height slider to the right vertical edge of the map window."""
        parent_widget = self.parentWidget()
        if not parent_widget or not parent_widget.isVisible():
            return

        map_area = None
        if hasattr(parent_widget, "web_view"):
            map_area = parent_widget.web_view
        elif hasattr(parent_widget, "_map_v_splitter"):
            map_area = parent_widget._map_v_splitter

        if map_area is None:
            return

        map_rect = map_area.rect()
        top_left = map_area.mapToGlobal(map_rect.topLeft())
        bottom_right = map_area.mapToGlobal(map_rect.bottomRight())

        right_margin = 16
        x_pos = bottom_right.x() - self.width() - right_margin
        # Center vertically inside the map view area
        y_pos = top_left.y() + (bottom_right.y() - top_left.y() - self.height()) // 2

        self.move(x_pos, y_pos)
        self.raise_()

    def _on_height_changed(self, value: int) -> None:
        self._height_value = int(value)
        self.height_value_label.setText(f"{self._height_value} m")
        self.controller._set_fly_through_height(float(value))


__all__ = ["FlyThroughHeightSlider"]
