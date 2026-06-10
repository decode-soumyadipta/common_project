from __future__ import annotations

import json
from pathlib import Path

from qtpy.QtCore import QSignalBlocker


class ComparatorCoordinator:
    """Encapsulate comparator visibility, candidate selection, and toggle flow."""

    def __init__(self, controller):
        self._controller = controller

    def available_comparator_layer_options(self) -> list[dict[str, object]]:
        c = self._controller
        options: list[dict[str, object]] = []
        for path, asset in c._search_result_assets_by_path.items():
            label = str(asset.get("file_name") or Path(path).name or "Layer")
            kind = str(asset.get("kind") or "")
            if kind:
                label = f"{label} [{kind}]"
            options.append(
                {
                    "path": path,
                    "label": label,
                    "visible": bool(c._search_layer_visibility.get(path, False)),
                }
            )
        return options

    def available_swipe_layer_options(self) -> list[dict[str, object]]:
        return self.available_comparator_layer_options()

    def _visible_imagery_layer_paths(self) -> list[str]:
        c = self._controller
        visible_layers: list[str] = []
        for path, asset in c._search_result_assets_by_path.items():
            if not c._search_layer_visibility.get(path, False):
                continue
            if c._is_dem_asset(asset):
                continue
            visible_layers.append(path)
        if c._explicit_imagery_layer_visible:
            selected = c._selected_asset()
            if isinstance(selected, dict) and not c._is_dem_asset(selected):
                selected_path = str(selected.get("file_path") or "")
                if selected_path and selected_path not in visible_layers:
                    visible_layers.append(selected_path)
        return visible_layers

    def _available_imagery_layer_paths(self) -> list[str]:
        c = self._controller
        available_paths: list[str] = []
        for path, asset in c._search_result_assets_by_path.items():
            if c._is_dem_asset(asset):
                continue
            available_paths.append(path)
        if c._explicit_imagery_layer_visible:
            selected = c._selected_asset()
            if isinstance(selected, dict) and not c._is_dem_asset(selected):
                selected_path = str(selected.get("file_path") or "")
                if selected_path and selected_path not in available_paths:
                    available_paths.append(selected_path)
        return available_paths

    def _visible_dem_layer_count(self) -> int:
        c = self._controller
        has_visible_search_dem = any(
            c._search_layer_visibility.get(path, False) and c._is_dem_asset(asset)
            for path, asset in c._search_result_assets_by_path.items()
        )
        if has_visible_search_dem or c._explicit_dem_layer_visible:
            return 1
        return 0

    def comparator_candidate_count(self) -> int:
        return (
            len(self._visible_imagery_layer_paths()) + self._visible_dem_layer_count()
        )

    def swipe_comparator_candidate_count(self) -> int:
        return self.comparator_candidate_count()

    def can_enable_comparator(self) -> bool:
        return self.comparator_candidate_count() >= 2

    def can_enable_swipe_comparator(self) -> bool:
        return self.can_enable_comparator()

    def can_attempt_enable_comparator(self) -> bool:
        if self.can_enable_comparator():
            return True
        return len(self._available_imagery_layer_paths()) >= 2

    def can_attempt_enable_swipe_comparator(self) -> bool:
        return self.can_attempt_enable_comparator()

    def _auto_enable_second_comparator_imagery_layer(self) -> bool:
        c = self._controller
        visible_imagery = self._visible_imagery_layer_paths()
        if len(visible_imagery) >= 2:
            return True

        available_imagery = self._available_imagery_layer_paths()
        if len(available_imagery) < 2:
            return False

        changed = False
        visible_set = set(visible_imagery)
        for path in available_imagery:
            if path in visible_set:
                continue
            if path not in c._search_result_assets_by_path:
                continue
            c._search_layer_visibility[path] = True
            visible_set.add(path)
            changed = True
            if len(visible_set) >= 2:
                break

        if changed:
            if c._event_driven_enabled:
                c._sync_search_visibility_layers_event_driven()
            else:
                c._sync_search_visibility_layers()
            c.panel.update_search_results(
                list(c._search_result_assets_by_path.values()),
                c._search_layer_visibility,
            )
            c._refresh_search_result_markers()
            c.panel.log(
                "Comparator: enabled an additional visible raster layer for comparison."
            )

        return self.can_enable_comparator()

    def _auto_enable_second_swipe_imagery_layer(self) -> bool:
        return self._auto_enable_second_comparator_imagery_layer()

# TODO: Refactor for cognitive complexity
# TODO: Refactor for cognitive complexity
    def apply_comparator_selection(self, selected_paths: list[str]) -> bool:
        import json as _json
        c = self._controller
        if c._comparator_visibility_snapshot is None:
            c._comparator_visibility_snapshot = dict(c._search_layer_visibility)

        selected = [
            path for path in selected_paths if path in c._search_result_assets_by_path
        ]
        if len(selected) < 2:
            c._swipe_comparator_enabled = False
            c._run_js_call("setComparator", False)
            c._run_js_call("clearComparatorExplicitKeys")
            c.panel.log("Comparator disabled. Select at least two layers.")
            return False

        # Send the full ordered list of selected paths so the JS resolveComparatorLayerKeys always returns exactly len(selected) keys — no ghost panes from extra visible layers.
        c._run_js_call("setComparatorAllLayers", _json.dumps(selected))

        # Also keep the legacy left/right pair for backward compat with setComparatorLayers callers.
        left_path  = selected[0]
        right_path = selected[1]
        left_asset  = c._search_result_assets_by_path.get(left_path)  or {}
        right_asset = c._search_result_assets_by_path.get(right_path) or {}
        left_label  = str(left_asset.get("file_name")  or Path(left_path).name  or "Layer A")
        right_label = str(right_asset.get("file_name") or Path(right_path).name or "Layer B")
        c._run_js_call(
            "setComparatorLayers", left_path, right_path, left_label, right_label
        )

        selected_set = set(selected)
        for path in c._search_result_assets_by_path:
            c._search_layer_visibility[path] = path in selected_set

        if c._event_driven_enabled:
            c._sync_search_visibility_layers_event_driven()
        else:
            c._sync_search_visibility_layers()
        c.panel.update_search_results(
            list(c._search_result_assets_by_path.values()),
            c._search_layer_visibility,
        )
        c._refresh_search_result_markers()

        # Auto-zoom to the selected imagery asset center/bounds
        zoom_bounds = None
        for path in selected:
            asset = c._search_result_assets_by_path.get(path)
            if asset and not c._is_dem_asset(asset):
                bounds = c._asset_bounds(asset)
                if bounds:
                    zoom_bounds = bounds
                    break
        if zoom_bounds:
            c._run_js_call(
                "focusBounds",
                zoom_bounds["west"],
                zoom_bounds["south"],
                zoom_bounds["east"],
                zoom_bounds["north"]
            )

        return self._toolbar_toggle_comparator(enabled=True)

    def apply_swipe_comparator_selection(self, selected_paths: list[str]) -> bool:
# TODO: Refactor for cognitive complexity
        return self.apply_comparator_selection(selected_paths)
# TODO: Refactor for cognitive complexity

    def _restore_pre_comparator_visibility(self) -> None:
        c = self._controller
        if c._comparator_visibility_snapshot is not None:
            snapshot = c._comparator_visibility_snapshot
            c._comparator_visibility_snapshot = None
            for path in c._search_result_assets_by_path:
                if path in snapshot:
                    c._search_layer_visibility[path] = bool(snapshot[path])
            if c._event_driven_enabled:
                c._sync_search_visibility_layers_event_driven()
            else:
                c._sync_search_visibility_layers()
            c.panel.update_search_results(
                list(c._search_result_assets_by_path.values()),
                c._search_layer_visibility,
            )
            c._refresh_search_result_markers()

    def _enable_comparator_flow(self, candidate_count: int) -> bool:
        c = self._controller
        if c._comparator_visibility_snapshot is None:
            c._comparator_visibility_snapshot = dict(c._search_layer_visibility)
        c._run_js_call("setComparatorPosition", 0.5)
        c._run_js_call("requestComparatorPaneState")
        c.panel.log(
            "Comparator enabled. Drag divider on map to compare georeferenced layers."
        )
        c._logger.info("Comparator enabled candidate_layers=%s", candidate_count)
        c._apply_display_control_mode()
        return True

    def _toolbar_toggle_comparator(self, enabled: bool | None = None) -> bool:
        c = self._controller
        candidate_count = self.comparator_candidate_count()
        next_state = (
            (not c._swipe_comparator_enabled) if enabled is None else bool(enabled)
        )

        if next_state:
            if c._comparator_visibility_snapshot is None:
                c._comparator_visibility_snapshot = dict(c._search_layer_visibility)
            if candidate_count < 2:
                if self._auto_enable_second_comparator_imagery_layer():
                    candidate_count = self.comparator_candidate_count()

        if next_state and candidate_count < 2:
            c.panel.log("Comparator needs at least two visible raster layers.")
            c._swipe_comparator_enabled = False
            self._restore_pre_comparator_visibility()
            return False

        c._swipe_comparator_enabled = next_state
        c._run_js_call("setComparator", c._swipe_comparator_enabled)

        # Keep AOI/search marker visibility aligned with the checkbox state
        desired_aoi_visible = (
            bool(c.panel.search_aoi_visible_check.isChecked())
            if hasattr(c.panel, "search_aoi_visible_check")
            else True
        )
        c._set_search_aoi_visible(desired_aoi_visible)

        if c._swipe_comparator_enabled:
            return self._enable_comparator_flow(candidate_count)

        self._restore_pre_comparator_visibility()
        c._comparator_selected_pane = None
        c._comparator_selected_layer_type = None
        # Clear explicit key list so next comparator open starts fresh
        c._run_js_call("clearComparatorExplicitKeys")
        c.panel.log("Comparator disabled.")
        c._logger.info("Comparator disabled")
        c._apply_display_control_mode()
        return False

    def _toolbar_toggle_swipe_comparator(self, enabled: bool | None = None) -> bool:
        return self._toolbar_toggle_comparator(enabled=enabled)

    @staticmethod
    def _set_slider_from_float_value(
        slider, raw_value: object, scale: float = 1.0
    ) -> None:
        if not isinstance(raw_value, (int, float)):
            return
        scaled = round(float(raw_value) * scale)
        slider.setValue(max(slider.minimum(), min(slider.maximum(), scaled)))

    def on_comparator_pane_state(self, payload_json: str) -> None:
        c = self._controller
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            c._logger.warning(
                "Invalid comparator pane state payload JSON: %s", payload_json
            )
            return

        if not isinstance(payload, dict):
            c._logger.warning(
                "Invalid comparator pane state payload type: %s", type(payload).__name__
            )
            return

        pane = str(payload.get("pane") or "").strip().lower()
        layer_type = str(payload.get("layer_type") or "").strip().lower()
        if pane not in {"left", "right"}:
            pane = "left"
        c._comparator_selected_pane = pane
        c._comparator_selected_layer_type = (
            layer_type if layer_type in {"dem", "imagery"} else None
        )

        imagery = (
            payload.get("imagery") if isinstance(payload.get("imagery"), dict) else {}
        )
        dem = payload.get("dem") if isinstance(payload.get("dem"), dict) else {}

        blockers = [
            QSignalBlocker(c.panel.brightness_slider),
            QSignalBlocker(c.panel.contrast_slider),
            QSignalBlocker(c.panel.dem_hillshade_slider),
            QSignalBlocker(c.panel.dem_color_mode_combo),
        ]
        try:
            self._set_slider_from_float_value(
                c.panel.brightness_slider, imagery.get("brightness"), scale=100.0
            )
            self._set_slider_from_float_value(
                c.panel.contrast_slider, imagery.get("contrast"), scale=100.0
            )
            self._set_slider_from_float_value(
                c.panel.dem_hillshade_slider, dem.get("hillshade_alpha"), scale=100.0
            )

            color_mode = str(dem.get("color_mode") or "").strip().lower()
            if color_mode:
                color_mode_index = c.panel.dem_color_mode_combo.findData(color_mode)
                if color_mode_index >= 0:
                    c.panel.dem_color_mode_combo.setCurrentIndex(color_mode_index)
        finally:
            del blockers

        c.panel._update_display_value_labels()
        c._apply_display_control_mode()
        c._logger.debug(
            "Comparator pane selected pane=%s type=%s",
            c._comparator_selected_pane,
            c._comparator_selected_layer_type,
        )


__all__ = ["ComparatorCoordinator"]
