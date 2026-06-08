from __future__ import annotations

import logging

_logger = logging.getLogger(__name__)


class SyncFocusCoordinator:
    """Encapsulate layer synchronization and focus operations for desktop controller."""

    def __init__(self, controller):
        self._controller = controller
        self._logger = logging.getLogger("client_desktop.sync_focus_coordinator")

    def sync_search_visibility_layers_event_driven(self) -> None:
        """Synchronize search visibility layers with event-driven optimization."""
        c = self._controller
        
        # CRITICAL FIX: Prevent concurrent visibility syncs
        if c._event_driven_sync_in_progress:
            _logger.debug("DEBUG: Event-driven visibility sync already in progress, skipping")
            return
        
        c._event_driven_sync_in_progress = True
        
        try:
            for file_path, asset in c._search_result_assets_by_path.items():
                should_show = bool(c._search_layer_visibility.get(file_path, False))
                is_dem_asset = c._is_dem_asset(asset)

                if not should_show:
                    if file_path in c._loaded_search_layer_keys:
                        c._run_js_call("setLayerVisibility", file_path, False)
                    if is_dem_asset and c._active_dem_search_layer_key == file_path:
                        c.state.active_layer_is_dem = False
                        c._active_dem_search_layer_key = None
                        c._apply_display_control_mode()
                    continue

                if is_dem_asset and file_path in c._loaded_search_layer_keys:
                    c._run_js_call("setLayerVisibility", file_path, True)
                    c.state.active_layer_is_dem = True
                    c._active_dem_search_layer_key = file_path
                    c._apply_display_control_mode()
                    continue

                if is_dem_asset and should_show:
                    if c._active_dem_search_layer_key and c._active_dem_search_layer_key != file_path:
                        old_dem = c._active_dem_search_layer_key
                        if old_dem in c._loaded_search_layer_keys:
                            c._run_js_call("setLayerVisibility", old_dem, False)
                        c._search_layer_visibility[old_dem] = False
                        c._active_dem_search_layer_key = None

                if (not is_dem_asset) and file_path in c._loaded_search_layer_keys:
                    c._run_js_call("setLayerVisibility", file_path, True)
                    continue

                # Event-driven layer loading with server optimization
                loaded = c._load_asset_layer_event_driven(
                    asset,
                    replace_existing=False,
                    layer_key=file_path,
                    auto_fly_to=False,
                    apply_scene_mode=False,
                    show_loading=False,
                )
                if not loaded:
                    c._search_layer_visibility[file_path] = False
                    continue

                c._loaded_search_layer_keys.add(file_path)

            # Enforce layer stack order matching the UI list for event-driven mode
            order_registry = getattr(c.panel, "_layer_order_registry", {}) or {}
            ordered_keys = sorted(
                [
                    p.replace("\\", "/")
                    for p in c._search_result_assets_by_path
                    if c._search_layer_visibility.get(p, False)
                ],
                key=lambda p: order_registry.get(p, {}).get("order", 9999),
            )
            if ordered_keys:
                c._run_js_call("enforceLayerDisplayOrder", ordered_keys)

            c._apply_display_control_mode()
        finally:
            # Always clear the in-progress flag
            c._event_driven_sync_in_progress = False

    def load_asset_layer_event_driven(
        self,
        asset: dict,
        *,
        replace_existing: bool = True,
        layer_key: str | None = None,
        auto_fly_to: bool = True,
        apply_scene_mode: bool = True,
        show_loading: bool = True,
    ) -> dict | None:
        """Load asset layer with event-driven optimization for terabyte-scale performance."""
        c = self._controller
        if show_loading:
            performance_tier = asset.get("performance_tier", "standard")
            loading_msg = f"Loading {asset['file_name']} [{performance_tier}]..."
            c._set_layer_loading(True, loading_msg)

        # Use existing _load_asset_layer but with event-driven flags
        options = c._get_server_optimized_layer_options(asset)
        options["replace_existing"] = replace_existing
        if layer_key:
            options["layer_key"] = str(layer_key).replace("\\", "/")
        options["apply_scene_mode"] = apply_scene_mode
        options["event_driven"] = True

        # Store bounds from TiTiler back into the asset dict so that _fly_to_asset / asset_bounds can find them later without an extra HTTP call. utility_coordinator.asset_bounds checks asset["bounds"] first.
        if "bounds" in options and isinstance(options["bounds"], dict):
            asset["bounds"] = options["bounds"]

        if c._add_layer_event_driven(asset, options):
            if auto_fly_to:
                c._fly_through_asset_event_driven(asset)
        else:
            if show_loading:
                c._set_layer_loading(False, "Layer load failed")
            return None

        c.state.selected_asset = asset
        return asset


    def sync_search_visibility_layers(self) -> None:
        """Sync layer visibility between UI and globe with debug logging - optimized to only update changed layers."""
        c = self._controller
        
        # CRITICAL FIX: Prevent concurrent visibility syncs
        if c._standard_sync_in_progress:
            _logger.debug("DEBUG: Standard visibility sync already in progress, skipping")
            return
        
        c._standard_sync_in_progress = True
        
        try:
            _logger.debug(f"\n{'=' * 80}")
            _logger.debug("DEBUG: _sync_search_visibility_layers called")
            _logger.debug(f"  Loaded layer keys: {len(c._loaded_search_layer_keys)}")
            _logger.debug(f"  Active DEM layer key: {c._active_dem_search_layer_key}")
            _logger.debug(f"{'=' * 80}\n")

            for file_path, asset in c._search_result_assets_by_path.items():
                should_show = bool(c._search_layer_visibility.get(file_path, False))
                last_synced = c._last_synced_visibility.get(file_path, None)
                is_dem_asset = c._is_dem_asset(asset)
                file_name = asset.get("file_name", "unknown")
                is_loaded = file_path in c._loaded_search_layer_keys

                _logger.debug(f"DEBUG: Processing layer: {file_name} (DEM: {is_dem_asset}, Loaded: {is_loaded})")
                _logger.debug(f"  should_show={should_show}, last_synced={last_synced}")

                # OPTIMIZATION: Skip if visibility hasn't changed since last sync
                if last_synced is not None and last_synced == should_show and is_loaded:
                    _logger.debug("  SKIP: Visibility unchanged")
                    continue

                if not should_show:
                    if is_loaded:  # Only hide if it's actually loaded
                        _logger.debug("  ACTION: Hiding layer")
                        c._run_js_call("setLayerVisibility", file_path, False)
                        c._last_synced_visibility[file_path] = False
                        if is_dem_asset and c._active_dem_search_layer_key == file_path:
                            c.state.active_layer_is_dem = False
                            c._active_dem_search_layer_key = None
                            c._apply_display_control_mode()
                            _logger.debug("  DEM deactivated")
                    else:
                        _logger.debug("  SKIP: Layer not loaded, no need to hide")
                    continue

                if is_dem_asset and is_loaded:
                    _logger.debug("  ACTION: Showing DEM layer")
                    c._run_js_call("setLayerVisibility", file_path, True)
                    c._last_synced_visibility[file_path] = True
                    c.state.active_layer_is_dem = True
                    c._active_dem_search_layer_key = file_path
                    c._apply_display_control_mode()
                    _logger.debug("  DEM activated")
                    continue

                if is_dem_asset and should_show:
                    if c._active_dem_search_layer_key and c._active_dem_search_layer_key != file_path:
                        _logger.debug(f"  ACTION: Deactivating old DEM {c._active_dem_search_layer_key} in favor of new DEM {file_path}")
                        old_dem = c._active_dem_search_layer_key
                        if old_dem in c._loaded_search_layer_keys:
                            c._run_js_call("setLayerVisibility", old_dem, False)
                        c._search_layer_visibility[old_dem] = False
                        c._last_synced_visibility[old_dem] = False
                        c._active_dem_search_layer_key = None

                if (not is_dem_asset) and is_loaded:
                    _logger.debug("  ACTION: Showing imagery layer")
                    c._run_js_call("setLayerVisibility", file_path, True)
                    c._last_synced_visibility[file_path] = True
                    continue

                if not is_loaded:
                    _logger.debug("  ACTION: Loading new layer")
                    try:
                        loaded = c._load_asset_layer(
                            asset,
                            replace_existing=False,
                            layer_key=file_path,
                            auto_fly_to=False,
                            apply_scene_mode=False,
                            show_loading=False,
                        )
                        if not loaded:
                            _logger.debug("  ERROR: Failed to load layer")
                            c._search_layer_visibility[file_path] = False
                            continue

                        c._loaded_search_layer_keys.add(file_path)
                        c._last_synced_visibility[file_path] = True
                        _logger.debug("  SUCCESS: Layer loaded and added to loaded keys")
                    except Exception as e:
                        _logger.debug(f"  ERROR: Exception while loading layer: {e}")
                        c._search_layer_visibility[file_path] = False
                        continue

            # Enforce layer stack order matching the UI list
            order_registry = getattr(c.panel, "_layer_order_registry", {}) or {}
            ordered_keys = sorted(
                [
                    p.replace("\\", "/")
                    for p in c._search_result_assets_by_path
                    if c._search_layer_visibility.get(p, False)
                ],
                key=lambda p: order_registry.get(p, {}).get("order", 9999),
            )
            if ordered_keys:
                c._run_js_call("enforceLayerDisplayOrder", ordered_keys)

            c._apply_display_control_mode()
            _logger.debug("DEBUG: _sync_search_visibility_layers completed\n")
        finally:
            # Always clear the in-progress flag
            c._standard_sync_in_progress = False

    def focus_visible_search_assets(self, *, force: bool) -> None:
        """Legacy focus function - delegates to enhanced version."""
        c = self._controller
        self.focus_visible_search_assets_with_enhanced_behavior(
            force=force,
            is_first_search=force,
            asset_count=len(c._search_result_assets_by_path),
        )

    def focus_visible_search_assets_with_enhanced_behavior(
        self, *, force: bool, is_first_search: bool, asset_count: int
    ) -> None:
        """Enhanced focus function with improved multi-asset handling and first-search auto-flyto."""
        c = self._controller
        visible_assets = [
            asset
            for path, asset in c._search_result_assets_by_path.items()
            if c._search_layer_visibility.get(path, False)
        ]
        
        # Fallback: Zoom/focus to all search results if none are visible, satisfying the requirement: "after searching..it must auto zoom focus automatically to the aoi......setview../flyto"
        assets_to_focus = visible_assets if visible_assets else list(c._search_result_assets_by_path.values())
        
        if not assets_to_focus:
            c._last_visible_focus_signature = None
            return

        union_bounds: dict[str, float] | None = None
        for asset in assets_to_focus:
            bounds = c._asset_bounds(asset)
            if bounds is None:
                continue
            if union_bounds is None:
                union_bounds = dict(bounds)
                continue
            union_bounds["west"] = min(union_bounds["west"], bounds["west"])
            union_bounds["south"] = min(union_bounds["south"], bounds["south"])
            union_bounds["east"] = max(union_bounds["east"], bounds["east"])
            union_bounds["north"] = max(union_bounds["north"], bounds["north"])

        if union_bounds is not None:
            signature = (
                round(float(union_bounds["west"]), 6),
                round(float(union_bounds["south"]), 6),
                round(float(union_bounds["east"]), 6),
                round(float(union_bounds["north"]), 6),
            )
            if not force and c._last_visible_focus_signature == signature:
                return
            c._last_visible_focus_signature = signature

            # Enhanced behavior for multiple assets and first search
            if is_first_search:
                if len(assets_to_focus) == 1:
                    # Single asset: fly to it with appropriate zoom
                    self._logger.info("First search: Flying to single asset")
                    c._fly_to_asset(assets_to_focus[0])
                    c.panel.log(
                        f"Focused on search result: {assets_to_focus[0].get('file_name', 'asset')}"
                    )
                else:
                    # Multiple assets: fit all in view with padding
                    self._logger.info(
                        f"First search: Fitting {len(assets_to_focus)} assets in view"
                    )
                    c._run_js_call(
                        "focusBoundsWithPadding",
                        union_bounds["west"],
                        union_bounds["south"],
                        union_bounds["east"],
                        union_bounds["north"],
                        1.5,  # 50% padding to ensure all assets are visible
                    )
                    c.panel.log(f"Focused on {len(assets_to_focus)} search results")
            else:
                # Subsequent searches: use standard focus without animation
                c._run_js_call(
                    "focusBounds",
                    union_bounds["west"],
                    union_bounds["south"],
                    union_bounds["east"],
                    union_bounds["north"],
                )
            return

        # Fallback: focus on first asset
        c._fly_to_asset(assets_to_focus[0])

    def reorder_layers_event_driven(self, reordered_assets: list[dict]) -> None:
        """Reorder loaded layers in Cesium using the order stored in _layer_order_registry.

        The registry is updated by _on_search_results_reordered_with_data immediately
        after a drag-drop, so by the time this method is called (after the 150ms debounce)
        it always reflects the exact new UI row order.

        Strategy: call enforceLayerDisplayOrder with all loaded layer paths sorted by
        their registry display_order. This is the same mechanism used by
        sync_search_visibility_layers_event_driven and produces the correct Cesium
        imagery stack order regardless of how many invisible layers were moved.
        """
        c = self._controller
        try:
            order_registry = getattr(c.panel, "_layer_order_registry", {}) or {}

            # Sort all loaded layer paths by their new display_order from the registry. Invisible layers that aren't in _loaded_search_layer_keys are excluded — they are not present in the Cesium stack so can't be repositioned.
            loaded_paths_sorted = sorted(
                [
                    p
                    for p in c._loaded_search_layer_keys
                    if p in c._search_result_assets_by_path
                ],
                key=lambda p: order_registry.get(p, {}).get("order", 9999),
            )

            if not loaded_paths_sorted:
                self._logger.info(
                    "reorder: no loaded layers in Cesium stack yet — deferred"
                )
                return

            c._run_js_call("enforceLayerDisplayOrder", loaded_paths_sorted)
            c._run_js_call("requestSceneRender")

            self._logger.info(
                "EVENT_DRIVEN: Sent %d layer reorder commands", len(loaded_paths_sorted)
            )

        except Exception as e:
            self._logger.warning(
                "Event-driven layer reordering failed, falling back to standard: %s", e
            )
            self.reorder_layers_standard(reordered_assets)

    def reorder_layers_standard(self, reordered_assets: list[dict]) -> None:
        """Reorder layers using standard approach.

        CRITICAL: Reorder ALL loaded layers, not just visible ones.
        """
        c = self._controller
        try:
            # For standard approach, we need to manipulate the Cesium layer stack by raising/lowering layers to achieve the desired order
            loaded_layers = []
            for asset in reordered_assets:
                file_path = str(asset.get("file_path", "")).replace("\\", "/")
                if not file_path:
                    continue

                # Check if layer is loaded (not just visible)
                if file_path in c._loaded_search_layer_keys:
                    loaded_layers.append(file_path)
                    self._logger.debug(
                        "STANDARD: Including layer for reorder: %s",
                        asset.get("file_name", ""),
                    )

            if not loaded_layers:
                self._logger.warning("STANDARD: No loaded layers found to reorder")
                return

            # Reorder loaded layers using enforceLayerDisplayOrder
            self._logger.info("STANDARD: Reordering %d layers", len(loaded_layers))
            c._run_js_call("enforceLayerDisplayOrder", loaded_layers)

        except Exception as e:
            self._logger.error("Standard layer reordering failed: %s", e)

    def update_coordinate_inputs_from_polygon(self, payload: dict) -> None:
        """Update coordinate inputs from polygon payload."""
        c = self._controller
        points = payload.get("points", [])
        if not isinstance(points, list) or not points:
            return

        lons: list[float] = []
        lats: list[float] = []
        for item in points:
            if not isinstance(item, dict):
                continue
            lon = item.get("lon")
            lat = item.get("lat")
            if lon is None or lat is None:
                continue
            try:
                lons.append(float(lon))
                lats.append(float(lat))
            except (TypeError, ValueError):
                continue

        if not lons or not lats:
            return

        center_lon = (min(lons) + max(lons)) / 2.0
        center_lat = (min(lats) + max(lats)) / 2.0
        c.panel.search_coord_lon.setValue(center_lon)
        c.panel.search_coord_lat.setValue(center_lat)
