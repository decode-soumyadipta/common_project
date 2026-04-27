from __future__ import annotations

from pathlib import Path


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
        return len(self._visible_imagery_layer_paths()) + self._visible_dem_layer_count()

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
            c._sync_search_visibility_layers()
            c.panel.update_search_results(
                list(c._search_result_assets_by_path.values()),
                c._search_layer_visibility,
            )
            c.panel.log(
                "Comparator: enabled an additional visible raster layer for comparison."
            )

        return self.can_enable_comparator()

    def _auto_enable_second_swipe_imagery_layer(self) -> bool:
        return self._auto_enable_second_comparator_imagery_layer()

    def apply_comparator_selection(self, selected_paths: list[str]) -> bool:
        c = self._controller
        selected = [
            path
            for path in selected_paths
            if path in c._search_result_assets_by_path
        ]
        if len(selected) < 2:
            c._swipe_comparator_enabled = False
            c._run_js_call("setComparator", False)
            c.panel.log("Comparator disabled. Select at least two layers.")
            return False

        left_path = selected[0]
        right_path = selected[1]
        left_asset = c._search_result_assets_by_path.get(left_path) or {}
        right_asset = c._search_result_assets_by_path.get(right_path) or {}
        left_label = str(left_asset.get("file_name") or Path(left_path).name or "Layer A")
        right_label = str(right_asset.get("file_name") or Path(right_path).name or "Layer B")
        c._run_js_call(
            "setComparatorLayers", left_path, right_path, left_label, right_label
        )

        selected_set = set(selected)
        for path in c._search_result_assets_by_path:
            c._search_layer_visibility[path] = path in selected_set

        c._sync_search_visibility_layers()
        c.panel.update_search_results(
            list(c._search_result_assets_by_path.values()),
            c._search_layer_visibility,
        )
        return self._toolbar_toggle_comparator(enabled=True)

    def apply_swipe_comparator_selection(self, selected_paths: list[str]) -> bool:
        return self.apply_comparator_selection(selected_paths)

    def _toolbar_toggle_comparator(self, enabled: bool | None = None) -> bool:
        c = self._controller
        candidate_count = self.comparator_candidate_count()
        next_state = (not c._swipe_comparator_enabled) if enabled is None else bool(enabled)

        if next_state and candidate_count < 2:
            if self._auto_enable_second_comparator_imagery_layer():
                candidate_count = self.comparator_candidate_count()

        if next_state and candidate_count < 2:
            c.panel.log("Comparator needs at least two visible raster layers.")
            c._swipe_comparator_enabled = False
            return False

        c._swipe_comparator_enabled = next_state
        c._run_js_call("setComparator", c._swipe_comparator_enabled)
        if c._swipe_comparator_enabled:
            c._run_js_call("setComparatorPosition", 0.5)
            c._run_js_call("requestComparatorPaneState")
            c.panel.log(
                "Comparator enabled. Drag divider on map to compare georeferenced layers."
            )
            c._logger.info("Comparator enabled candidate_layers=%s", candidate_count)
            c._apply_display_control_mode()
            return True

        c._comparator_selected_pane = None
        c._comparator_selected_layer_type = None
        c.panel.log("Comparator disabled.")
        c._logger.info("Comparator disabled")
        c._apply_display_control_mode()
        return False

    def _toolbar_toggle_swipe_comparator(self, enabled: bool | None = None) -> bool:
        return self._toolbar_toggle_comparator(enabled=enabled)


__all__ = ["ComparatorCoordinator"]
