from __future__ import annotations


class VisualizationCoordinator:
    """Encapsulate viewer mode and style operations for desktop controller."""

    def __init__(self, controller):
        self._controller = controller

    def apply_rgb_view_mode(self) -> None:
        c = self._controller
        mode = str(c.panel.rgb_view_mode_combo.currentData() or "3d")
        c._run_js_call("setSceneMode", mode)
        c._apply_display_control_mode()
        mode_label = "2D map" if mode == "2d" else "3D terrain"
        c.panel.log(f"RGB view mode applied: {mode_label}")

    def on_visual_slider_changed(self, _value: int) -> None:
        self.apply_visual_settings(log_to_panel=False)

    def on_dem_slider_changed(self, _value: int) -> None:
        self.apply_dem_settings(log_to_panel=False)

    def on_dem_color_mode_changed(self, _index: int) -> None:
        self.apply_dem_color_mode(log_to_panel=False)

    def apply_visual_settings(self, log_to_panel: bool = True) -> None:
        c = self._controller
        brightness = c.panel.brightness_slider.value() / 100.0
        contrast = c.panel.contrast_slider.value() / 100.0
        c._run_js_call("setImageryProperties", brightness, contrast)
        if log_to_panel:
            c.panel.log(
                f"Applied imagery settings brightness={brightness:.2f}, contrast={contrast:.2f}"
            )
            c._logger.info(
                "Applied imagery settings brightness=%.2f contrast=%.2f",
                brightness,
                contrast,
            )
            return
        c._logger.debug(
            "Live imagery settings brightness=%.2f contrast=%.2f", brightness, contrast
        )

    def apply_dem_settings(
        self, _checked: bool | None = None, log_to_panel: bool = True
    ) -> None:
        c = self._controller
        exaggeration = c.panel.dem_exaggeration_slider.value() / 100.0
        hillshade_strength = c.panel.dem_hillshade_slider.value() / 100.0
        c._run_js_call("setDemProperties", exaggeration, hillshade_strength)
        if log_to_panel:
            c.panel.log(
                "Applied DEM settings "
                f"exaggeration={exaggeration:.2f}, hillshade={hillshade_strength:.2f}"
            )
            c._logger.info(
                "Applied DEM settings exaggeration=%.2f hillshade=%.2f",
                exaggeration,
                hillshade_strength,
            )
            return
        c._logger.debug(
            "Live DEM settings exaggeration=%.2f hillshade=%.2f",
            exaggeration,
            hillshade_strength,
        )

    def apply_dem_color_mode(self, log_to_panel: bool = True) -> None:
        c = self._controller
        color_mode = str(c.panel.dem_color_mode_combo.currentData() or "gray")
        c._run_js_call("setDemColorMode", color_mode)
        if log_to_panel:
            label = "White relief" if color_mode == "gray" else "Color relief"
            c.panel.log(f"Applied DEM style: {label}")
            c._logger.info("Applied DEM style=%s", color_mode)
            return
        c._logger.debug("Live DEM style=%s", color_mode)

    def rotate_camera(self, degrees: float) -> None:
        self._controller._run_js_call("rotateCamera", degrees)

    def set_pitch(self, degrees: int) -> None:
        self._controller._run_js_call("setPitch", float(degrees))
