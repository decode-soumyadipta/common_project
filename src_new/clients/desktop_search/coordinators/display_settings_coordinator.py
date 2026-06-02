"""Display settings coordinator for visual settings, stretch modes, and raster rendering."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from qtpy.QtCore import QSignalBlocker, QTimer

if TYPE_CHECKING:
    from src_new.clients.desktop_search.controller import DesktopController


class DisplaySettingsCoordinator:
    """Handles display settings including stretch modes, visual adjustments, and layer refresh."""

    def __init__(self, controller: DesktopController):
        self._controller = controller
        self._logger = logging.getLogger("client_desktop.display_settings_coordinator")

    def on_stretch_mode_changed(self, _index: int) -> None:
        """Handle imagery stretch mode change."""
        self.apply_imagery_stretch_mode(log_to_panel=True)

    def on_dem_stretch_mode_changed(self, _index: int) -> None:
        """Handle DEM stretch mode change."""
        self.apply_dem_stretch_mode(log_to_panel=True)

    def apply_imagery_stretch_mode(self, log_to_panel: bool = True) -> None:
        """Apply imagery stretch mode and refresh affected layers."""
        c = self._controller
        c.panel.set_search_busy(True, "Applying Imagery Stretch...", progress=15)
        refreshed = self.refresh_raster_layers_for_stretch(layer_kind="imagery")
        QTimer.singleShot(800, lambda: c.panel.set_search_busy(False))
        mode_label = c.panel.stretch_mode_combo.currentText()
        if not log_to_panel:
            return
        if refreshed > 0:
            c.panel.log(
                f"Imagery stretch applied: {mode_label} ({refreshed} layer(s) refreshed)"
            )
            self._logger.info(
                "Imagery stretch applied mode=%s refreshed=%s", mode_label, refreshed
            )
            return
        c.panel.log(f"Imagery stretch set: {mode_label}")
        self._logger.info(
            "Imagery stretch set mode=%s (no active raster layers)", mode_label
        )

    def apply_dem_stretch_mode(self, log_to_panel: bool = True) -> None:
        """Apply DEM stretch mode and refresh affected layers."""
        c = self._controller
        if not hasattr(c.panel, "dem_stretch_mode_combo"):
            return
        c.panel.set_search_busy(True, "Applying DEM Stretch...", progress=15)
        refreshed = self.refresh_raster_layers_for_stretch(layer_kind="dem")
        QTimer.singleShot(800, lambda: c.panel.set_search_busy(False))
        mode_label = c.panel.dem_stretch_mode_combo.currentText()
        if not log_to_panel:
            return
        if refreshed > 0:
            c.panel.log(
                f"DEM stretch applied: {mode_label} ({refreshed} layer(s) refreshed)"
            )
            self._logger.info(
                "DEM stretch applied mode=%s refreshed=%s", mode_label, refreshed
            )
            return
        c.panel.log(f"DEM stretch set: {mode_label}")
        self._logger.info(
            "DEM stretch set mode=%s (no active raster layers)", mode_label
        )

    def _set_dem_slope_option_enabled(self, enabled: bool) -> None:
        c = self._controller
        combo = c.panel.dem_color_mode_combo
        slope_index = combo.findData("slope")
        if slope_index < 0:
            return

        model = combo.model()
        item = getattr(model, "item", None)
        if callable(item):
            try:
                model_item = item(slope_index)
            except Exception:  # pragma: no cover - defensive Qt model access
                model_item = None
            if model_item is not None:
                model_item.setEnabled(enabled)

        if enabled or str(combo.currentData() or "gray") != "slope":
            return

        fallback_index = combo.findData("terrain")
        if fallback_index < 0:
            fallback_index = combo.findData("gray")
        if fallback_index < 0:
            return

        with QSignalBlocker(combo):
            combo.setCurrentIndex(fallback_index)
        c._viz.apply_dem_color_mode(log_to_panel=False)

    def refresh_raster_layers_for_stretch(self, layer_kind: str | None = None) -> int:
        """Refresh raster layers to apply new stretch settings."""
        c = self._controller
        refreshed = 0
        seen_paths: set[str] = set()

        for path, asset in c._search_result_assets_by_path.items():
            if not c._search_layer_visibility.get(path, False):
                continue
            if not isinstance(asset, dict):
                continue
            if layer_kind == "dem" and not c._is_dem_asset(asset):
                continue
            if layer_kind == "imagery" and c._is_dem_asset(asset):
                continue
            asset_path = str(asset.get("file_path") or "")
            if asset_path and asset_path in seen_paths:
                continue
            loaded = c._load_asset_layer_event_driven(
                asset,
                replace_existing=False,
                layer_key=path,
                auto_fly_to=False,
                apply_scene_mode=False,
                show_loading=False,
            )
            if loaded:
                refreshed += 1
            if asset_path:
                seen_paths.add(asset_path)

        if c._explicit_imagery_layer_visible or c._explicit_dem_layer_visible:
            asset = c.state.selected_asset
            if isinstance(asset, dict):
                asset_path = str(asset.get("file_path") or "")
                if asset_path and asset_path in seen_paths:
                    return refreshed
                is_dem = c._is_dem_asset(asset)
                if layer_kind == "dem" and not is_dem:
                    return refreshed
                if layer_kind == "imagery" and is_dem:
                    return refreshed
                if (c._explicit_dem_layer_visible and is_dem) or (
                    c._explicit_imagery_layer_visible and not is_dem
                ):
                    loaded = c._load_asset_layer_event_driven(
                        asset,
                        replace_existing=False,
                        layer_key=None,
                        auto_fly_to=False,
                        apply_scene_mode=False,
                        show_loading=False,
                    )
                    if loaded:
                        refreshed += 1
        return refreshed

    def apply_raster_stretch(
        self, layer_key: str, stretch_type: str, method: str, **params
    ) -> None:
        """Apply raster stretch settings to a specific layer."""
        c = self._controller
        c._raster_stretch_settings[layer_key] = {
            "type": stretch_type,
            "method": method,
            "params": params,
        }
        self._logger.info(
            "Raster stretch applied layer_key=%s type=%s method=%s params=%s",
            layer_key,
            stretch_type,
            method,
            params,
        )
        # Refresh the layer to apply the new stretch
        asset = c._search_result_assets_by_path.get(layer_key)
        if asset:
            c._load_asset_layer_event_driven(
                asset,
                replace_existing=False,
                layer_key=layer_key,
                auto_fly_to=False,
                apply_scene_mode=False,
                show_loading=False,
            )

    def update_raster_stretch_params(self, layer_key: str, **params) -> None:
        """Update raster stretch parameters for a specific layer."""
        c = self._controller
        if layer_key in c._raster_stretch_settings:
            c._raster_stretch_settings[layer_key]["params"].update(params)
            self._logger.info(
                "Raster stretch params updated layer_key=%s params=%s", layer_key, params
            )
            # Refresh the layer to apply the updated params
            asset = c._search_result_assets_by_path.get(layer_key)
            if asset:
                c._load_asset_layer_event_driven(
                    asset,
                    replace_existing=False,
                    layer_key=layer_key,
                    auto_fly_to=False,
                    apply_scene_mode=False,
                    show_loading=False,
                )

    def remove_raster_stretch(self, layer_key: str) -> None:
        """Remove raster stretch settings from a specific layer."""
        c = self._controller
        if layer_key in c._raster_stretch_settings:
            del c._raster_stretch_settings[layer_key]
            self._logger.info("Raster stretch removed layer_key=%s", layer_key)
            # Refresh the layer to remove the stretch
            asset = c._search_result_assets_by_path.get(layer_key)
            if asset:
                c._load_asset_layer_event_driven(
                    asset,
                    replace_existing=False,
                    layer_key=layer_key,
                    auto_fly_to=False,
                    apply_scene_mode=False,
                    show_loading=False,
                )

    def apply_display_control_mode(self) -> None:
        """Apply display control mode based on visible layers."""
        c = self._controller
        dem_visible = any(
            c._search_layer_visibility.get(path, False) and c._is_dem_asset(asset)
            for path, asset in c._search_result_assets_by_path.items()
        )
        imagery_visible = any(
            c._search_layer_visibility.get(path, False)
            and (not c._is_dem_asset(asset))
            for path, asset in c._search_result_assets_by_path.items()
        )
        if c._explicit_dem_layer_visible:
            dem_visible = True
        if c._explicit_imagery_layer_visible:
            imagery_visible = True

        if c._swipe_comparator_enabled and c._comparator_selected_layer_type in {
            "dem",
            "imagery",
        }:
            dem_visible = c._comparator_selected_layer_type == "dem"
            imagery_visible = c._comparator_selected_layer_type == "imagery"

        comparator_active = c._swipe_comparator_enabled

        for widget in (
            c.panel.brightness_slider,
            c.panel.contrast_slider,
            c.panel.stretch_mode_combo,
        ):
            widget.setEnabled(imagery_visible and not comparator_active if widget is c.panel.stretch_mode_combo else imagery_visible)

        # CRITICAL FIX: Determine current scene mode from RGB view mode combo
        current_scene_mode = str(
            c.panel.rgb_view_mode_combo.currentData() or "3d"
        ).lower()
        is_2d_mode = current_scene_mode == "2d"

        # DEM controls: enabled when DEM is visible
        for widget in (
            c.panel.dem_hillshade_slider,
            c.panel.dem_color_mode_combo,
            getattr(c.panel, "dem_stretch_mode_combo", None),
        ):
            if widget is not None:
                if widget is c.panel.dem_hillshade_slider or widget is c.panel.dem_color_mode_combo:
                    widget.setEnabled(dem_visible)
                else:
                    widget.setEnabled(dem_visible and not comparator_active)

        self._set_dem_slope_option_enabled(not comparator_active)

        # Camera controls: pitch slider enabled in ALL 3D modes with any layer
        # Rotation works in both 2D and 3D (heading rotation valid in 2D Cesium)
        any_layer_visible = dem_visible or imagery_visible
        c.panel.pitch_slider.setEnabled(any_layer_visible and not is_2d_mode)
        for widget in (
            c.panel.rotate_left_btn,
            c.panel.rotate_right_btn,
        ):
            widget.setEnabled(any_layer_visible)  # Rotation works in both 2D/3D

        # Visual feedback for disabled pitch slider in 2D mode
        if is_2d_mode and any_layer_visible:
            c.panel.pitch_slider.setStyleSheet("""
                QSlider {
                    color: #888888;
                    background-color: #f0f0f0;
                }
                QSlider::handle:horizontal {
                    background: #cccccc;
                    border: 1px solid #999999;
                }
                QSlider::groove:horizontal {
                    background: #e0e0e0;
                }
            """)
            c.panel.pitch_slider.setToolTip("Pitch control is disabled in 2D mode")
        else:
            # Reset to default style when enabled
            c.panel.pitch_slider.setStyleSheet("")
            c.panel.pitch_slider.setToolTip("Adjust camera pitch angle")

        if c._toolbar_context_callback is not None:
            # The toolbar callback is a bound MainWindow method; during
            # controller initialization the MainWindow.controller attribute
            # may not be set yet. Call defensively to avoid AttributeError in
            # that race. If the callback fails, log and continue — the
            # MainWindow will refresh toolbar state later.
            try:
                if dem_visible and imagery_visible:
                    c._toolbar_context_callback("mixed")
                elif dem_visible:
                    c._toolbar_context_callback("dem")
                elif imagery_visible:
                    c._toolbar_context_callback("imagery")
                else:
                    c._toolbar_context_callback("none")
            except Exception as exc:  # pragma: no cover - defensive
                try:
                    self._logger.debug(
                        "Toolbar context callback deferred: %s", exc
                    )
                except Exception:
                    pass

        if c._swipe_comparator_enabled and not c.can_enable_comparator():
            c._swipe_comparator_enabled = False
            c._comparator_selected_pane = None
            c._comparator_selected_layer_type = None
            c._run_js_call("setComparator", False)
            c.panel.log(
                "Comparator disabled: at least two visible raster layers are required."
            )
