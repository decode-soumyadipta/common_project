from __future__ import annotations

from qtpy.QtCore import Qt, Slot
from qtpy.QtWidgets import QApplication


class ControlPanelDisplayMixin:
    def _update_display_value_labels(self, _value: int | None = None) -> None:
        brightness_scale = self.brightness_slider.value() / 100.0
        contrast_scale = self.contrast_slider.value() / 100.0
        pitch_degrees = int(self.pitch_slider.value())
        hillshade_percent = int(self.dem_hillshade_slider.value())

        self.brightness_value.setText(f"{brightness_scale:.2f}x")
        self.contrast_value.setText(f"{contrast_scale:.2f}x")
        self.pitch_value.setText(f"{pitch_degrees} deg")
        self.dem_hillshade_value.setText(f"{hillshade_percent}%")

    @Slot(float, float, float)
    def update_camera_info(self, scale_denominator: float, heading_deg: float, pitch_deg: float) -> None:
        """Update the pitch slider from live camera telemetry without triggering a bounce-back."""
        if not self.pitch_slider.isEnabled():
            return

        # Pitch from Cesium is roughly -90 (looking straight down) to 0 (looking horizontal)
        # Or it might be positive depending on the coordinate frame, but usually negative in the slider.
        # Clamp it to the slider range and set the value.
        pitch_val = int(pitch_deg)
        if pitch_val > self.pitch_slider.maximum():
            pitch_val = self.pitch_slider.maximum()
        elif pitch_val < self.pitch_slider.minimum():
            pitch_val = self.pitch_slider.minimum()

        # Set value silently so we don't emit valueChanged and cause an infinite loop
        self.pitch_slider.blockSignals(True)
        self.pitch_slider.setValue(pitch_val)
        self.pitch_slider.blockSignals(False)
        self._update_display_value_labels()

    def set_layer_loading(self, active: bool, message: str) -> None:
        self.layer_load_status.setText(message)
        if active:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self.layer_load_progress.setRange(0, 0)
            self.layer_load_progress.setVisible(True)
            # Notify main window to show overlay if it has one
            if hasattr(self.parent(), "set_busy_overlay"):
                self.parent().set_busy_overlay(True, message)
            elif hasattr(self.window(), "set_busy_overlay"):
                self.window().set_busy_overlay(True, message)
            return
        QApplication.restoreOverrideCursor()
        self.layer_load_progress.setRange(0, 100)
        self.layer_load_progress.setValue(100)
        self.layer_load_progress.setVisible(False)
        if hasattr(self.parent(), "set_busy_overlay"):
            self.parent().set_busy_overlay(False)
        elif hasattr(self.window(), "set_busy_overlay"):
            self.window().set_busy_overlay(False)
