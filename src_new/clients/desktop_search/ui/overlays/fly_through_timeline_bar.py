"""Bottom fly-through control bar for playback, seeking, and pitch control."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtCore import Qt, QSize, QSignalBlocker
from qtpy.QtGui import QIcon
from qtpy.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSlider,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from src_new.clients.desktop_search.controller import DesktopController


class FlyThroughTimelineBar(QWidget):
    """Compact bottom bar for fly-through playback controls."""

    def __init__(self, parent: QWidget, controller: DesktopController):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.controller = controller
        self._playing = False
        self._active = False
        self._speed_value = 1.0
        self._pitch_value = -42
        # Extra horizontal offset (pixels) to nudge the bar further left from the map area's left edge. Increase to move the bar left; use `set_horizontal_offset()` to change at runtime. Raised default to strongly bias the control towards the left side of the map viewport. Default offset to bias the control leftwards. Align to the left edge by default.
        self._horizontal_offset = 0
        # Allow the bar to move left of the map area's edge so it can shift farther left than the visible map column when requested.
        self._force_left = True

        self.setObjectName("flyThroughTimelineBar")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(
            """
            QWidget#flyThroughTimelineBar {
                background: transparent;
            }
            QFrame#flyThroughTimelineCard {
                background: rgba(255, 255, 255, 0.14);
                border: 1px solid rgba(255, 255, 255, 0.26);
                border-radius: 14px;
            }
            QLabel#flyThroughTitle {
                color: #ffffff;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.3px;
            }
            QLabel#flyThroughMetaLabel {
                color: #ffffff;
                font-size: 10px;
                font-weight: 600;
            }
            QToolButton#flyThroughPlayButton {
                background: rgba(255, 255, 255, 0.20);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.30);
                border-radius: 18px;
                padding: 6px 16px;
                font-size: 11px;
                font-weight: 700;
                min-width: 78px;
            }
            QToolButton#flyThroughPlayButton:hover {
                background: rgba(255, 255, 255, 0.28);
            }
            QToolButton#flyThroughExportButton {
                background: rgba(255, 255, 255, 0.20);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.30);
                border-radius: 12px;
                padding: 4px 12px;
                font-size: 10px;
                font-weight: 700;
            }
            QToolButton#flyThroughExportButton:hover {
                background: rgba(255, 255, 255, 0.28);
            }
            QToolButton#flyThroughSpeedButton {
                background: rgba(255, 255, 255, 0.12);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.24);
                border-radius: 12px;
                padding: 4px 10px;
                font-size: 10px;
                font-weight: 700;
                min-width: 42px;
            }
            QToolButton#flyThroughSpeedButton:hover {
                background: rgba(255, 255, 255, 0.18);
            }
            QToolButton#flyThroughSpeedButton:checked {
                background: rgba(255, 255, 255, 0.34);
                border-color: rgba(255, 255, 255, 0.48);
                color: white;
            }
            QSlider#flyThroughTimelineSlider::groove:horizontal,
            QSlider#flyThroughPitchSlider::groove:horizontal {
                background: rgba(255, 255, 255, 0.20);
                border-radius: 3px;
                height: 6px;
            }
            QSlider#flyThroughTimelineSlider::sub-page:horizontal,
            QSlider#flyThroughPitchSlider::sub-page:horizontal {
                background: rgba(255, 255, 255, 0.82);
                border-radius: 3px;
            }
            QSlider#flyThroughTimelineSlider::add-page:horizontal,
            QSlider#flyThroughPitchSlider::add-page:horizontal {
                background: rgba(255, 255, 255, 0.12);
                border-radius: 3px;
            }
            QSlider#flyThroughTimelineSlider::handle:horizontal,
            QSlider#flyThroughPitchSlider::handle:horizontal {
                background: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.55);
                width: 14px;
                margin: -6px 0;
                border-radius: 7px;
            }
            QSlider#flyThroughTimelineSlider::handle:horizontal:hover,
            QSlider#flyThroughPitchSlider::handle:horizontal:hover {
                background: #f8fbff;
            }

            """
        )

        card = QFrame(self)
        card.setObjectName("flyThroughTimelineCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 8, 14, 8)
        card_layout.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)

        title = QLabel("Fly Through")
        title.setObjectName("flyThroughTitle")
        header_row.addWidget(title)
        header_row.addStretch(1)

        self.state_label = QLabel("Ready")
        self.state_label.setObjectName("flyThroughMetaLabel")
        header_row.addWidget(self.state_label)

        self.progress_label = QLabel("0%")
        self.progress_label.setObjectName("flyThroughMetaLabel")
        header_row.addWidget(self.progress_label)

        card_layout.addLayout(header_row)

        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setObjectName("flyThroughTimelineSlider")
        self.progress_slider.setRange(0, 1000)
        self.progress_slider.setValue(0)
        self.progress_slider.setSingleStep(1)
        self.progress_slider.setPageStep(50)
        self.progress_slider.setToolTip("Seek through the fly-through path.")
        self.progress_slider.valueChanged.connect(self._on_progress_changed)
        card_layout.addWidget(self.progress_slider)

        controls_row = QHBoxLayout()
        controls_row.setContentsMargins(0, 0, 0, 0)
        controls_row.setSpacing(10)

        pitch_label = QLabel("Tilt")
        pitch_label.setObjectName("flyThroughMetaLabel")
        controls_row.addWidget(pitch_label)

        self.pitch_value_label = QLabel("-42°")
        self.pitch_value_label.setObjectName("flyThroughMetaLabel")
        controls_row.addWidget(self.pitch_value_label)

        self.pitch_slider = QSlider(Qt.Orientation.Horizontal)
        self.pitch_slider.setObjectName("flyThroughPitchSlider")
        self.pitch_slider.setRange(-80, -10)
        self.pitch_slider.setValue(-42)
        self.pitch_slider.setFixedWidth(160)
        self.pitch_slider.setToolTip("Adjust the camera tilt during flight.")
        self.pitch_slider.valueChanged.connect(self._on_pitch_changed)
        controls_row.addWidget(self.pitch_slider)



        controls_row.addStretch(1)

        self.play_pause_btn = QToolButton()
        self.play_pause_btn.setObjectName("flyThroughPlayButton")
        self.play_pause_btn.setText("Play")
        self.play_pause_btn.setIcon(self._media_icon("play"))
        self.play_pause_btn.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonIconOnly
        )
        self.play_pause_btn.setIconSize(QSize(18, 18))
        self.play_pause_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_pause_btn.clicked.connect(self._on_play_pause_clicked)
        controls_row.addWidget(self.play_pause_btn)

        self.export_video_btn = QToolButton()
        self.export_video_btn.setObjectName("flyThroughExportButton")
        self.export_video_btn.setText("Export Video")
        self.export_video_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_video_btn.clicked.connect(self._on_export_video_clicked)
        controls_row.addWidget(self.export_video_btn)

        speed_label = QLabel("Speed")
        speed_label.setObjectName("flyThroughMetaLabel")
        controls_row.addWidget(speed_label)

        self.speed_group = QButtonGroup(self)
        self.speed_group.setExclusive(True)
        self.speed_buttons: dict[float, QToolButton] = {}
        for speed in (0.25, 0.5, 1.0, 2.0, 3.0):
            button = QToolButton()
            button.setObjectName("flyThroughSpeedButton")
            button.setText(f"{speed:g}x")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, speed_value=speed: self._on_speed_clicked(
                    speed_value
                )
            )
            self.speed_group.addButton(button)
            self.speed_buttons[speed] = button
            controls_row.addWidget(button)

        self.speed_buttons[1.0].setChecked(True)

        card_layout.addLayout(controls_row)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(card)

        self.setMinimumHeight(95)
        self.hide()

    @staticmethod
    def _media_icon(kind: str) -> QIcon:
        app = QApplication.instance()
        style = app.style() if app else None
        if style is None:
            return QIcon()
        if kind == "pause":
            return style.standardIcon(QStyle.StandardPixmap.SP_MediaPause)
        return style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay)

    def set_fly_through_active(self, active: bool) -> None:
        """Show or hide the control bar and reset state when re-enabled."""
        self._active = bool(active)
        self.setVisible(self._active)
        if self._active:
            self.set_playback_state("idle")
            self.set_progress(0.0)
            self.set_speed(1.0)
            self.set_pitch(-42)
            self.controller._set_fly_through_pitch(-42.0)
            # Reposition immediately when shown so offset takes effect.
            self.update_position()

    def set_playback_state(self, state: str) -> None:
        normalized = str(state or "idle").lower()
        self._playing = normalized == "playing"
        if normalized == "paused":
            self.play_pause_btn.setIcon(self._media_icon("play"))
            self.state_label.setText("Paused")
        elif normalized == "playing":
            self.play_pause_btn.setIcon(self._media_icon("pause"))
            self.state_label.setText("Playing")
        elif normalized == "ended":
            self.play_pause_btn.setIcon(self._media_icon("play"))
            self.state_label.setText("Ended")
        else:
            self.play_pause_btn.setIcon(self._media_icon("play"))
            self.state_label.setText("Ready")

    def set_progress(self, value: float) -> None:
        progress = max(0.0, min(1.0, float(value)))
        with QSignalBlocker(self.progress_slider):
            self.progress_slider.setValue(int(round(progress * 1000)))
        self.progress_label.setText(f"{int(round(progress * 100))}%")

    def set_speed(self, value: float) -> None:
        speed = max(0.25, min(3.0, float(value)))
        self._speed_value = speed
        if speed not in self.speed_buttons:
            speed = 1.0
        for button_speed, button in self.speed_buttons.items():
            button.setChecked(abs(button_speed - speed) < 1e-6)

    def set_pitch(self, value: float) -> None:
        pitch = max(-80.0, min(-10.0, float(value)))
        self._pitch_value = int(round(pitch))
        with QSignalBlocker(self.pitch_slider):
            self.pitch_slider.setValue(self._pitch_value)
        self.pitch_value_label.setText(f"{self._pitch_value}°")



    def update_position(self) -> None:
        """Anchor the bar to the bottom of the map area with full horizontal width."""
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

        left_margin = 12
        right_margin = 12
        bottom_margin = 12

        map_width = bottom_right.x() - top_left.x()
        available_width = max(0, map_width - left_margin - right_margin)

        # Constrain the control bar width so it doesn't span the entire map when the map is very wide. This lets us center it within the map viewport.
        max_control_width = 720
        min_control_width = 320
        width = min(max_control_width, max(min_control_width, available_width))
        height = self.minimumHeight()
        self.resize(width, height)

        # Shift the default position a bit leftwards from the center, and apply horizontal offset.
        x_pos = int(top_left.x() + (map_width - width) * 0.4) - self._horizontal_offset
        y_pos = bottom_right.y() - height - bottom_margin

        # Ensure the bar stays within the horizontal bounds of the map area
        min_x = top_left.x() + left_margin
        max_x = bottom_right.x() - right_margin - width
        if x_pos < min_x:
            x_pos = min_x
        if x_pos > max_x:
            x_pos = max_x
        top_margin = 12
        max_y = bottom_right.y() - bottom_margin - height
        min_y = top_left.y() + top_margin
        if max_y < min_y:
            y_pos = min_y
        else:
            if y_pos < min_y:
                y_pos = min_y
            if y_pos > max_y:
                y_pos = max_y
        self.move(x_pos, y_pos)
        self.raise_()

    def set_force_left(self, enabled: bool) -> None:
        """Enable or disable forcing the bar left of the map area's left edge.

        When enabled the control may be positioned outside the map's left
        boundary (useful for aggressive left nudges). Call `update_position()`
        will reposition immediately.
        """
        self._force_left = bool(enabled)
        self.update_position()

    def set_horizontal_offset(self, offset: int) -> None:
        """Set an extra horizontal offset in pixels to nudge the bar left.

        Positive values move the bar further left; negative move it right.
        Calling this will immediately reposition the widget.
        """
        try:
            offset_val = int(offset)
        except Exception:
            return
        self._horizontal_offset = offset_val
        self.update_position()

    def increase_horizontal_offset(self, delta: int = 1000) -> None:
        """Increase the horizontal offset by `delta` pixels (positive moves left).

        Useful for repeated 'more' nudges. Calls `update_position()`.
        """
        try:
            delta_val = int(delta)
        except Exception:
            return
        self._horizontal_offset += delta_val
        self.update_position()

    def _on_play_pause_clicked(self) -> None:
        self.controller._toggle_fly_through_playback()

    def _on_progress_changed(self, value: int) -> None:
        progress = max(0.0, min(1.0, value / 1000.0))
        self.progress_label.setText(f"{int(round(progress * 100))}%")
        self.controller._seek_fly_through_progress(progress)

    def _on_speed_clicked(self, speed: float) -> None:
        self.set_speed(speed)
        self.controller._set_fly_through_speed(speed)

    def _on_pitch_changed(self, value: int) -> None:
        self._pitch_value = int(value)
        self.pitch_value_label.setText(f"{self._pitch_value}°")
        self.controller._set_fly_through_pitch(float(value))

    def _on_export_video_clicked(self) -> None:
        parent_window = self.parentWidget()
        if hasattr(parent_window, "export_fly_through_video"):
            parent_window.export_fly_through_video()


__all__ = ["FlyThroughTimelineBar"]