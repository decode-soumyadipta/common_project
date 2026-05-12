from __future__ import annotations

import logging


class SyncFocusCoordinator:
    """Encapsulate layer synchronization and focus operations for desktop controller."""

    def __init__(self, controller):
        self._controller = controller
        self._logger = logging.getLogger("client_desktop.sync_focus_coordinator")

    def sync_search_visibility_layers_event_driven(self) -> None:
        """Synchronize search visibility layers with event-driven optimization."""
        c = self._controller
        for file_path, asset in c._search_result_assets_by_path.items():
            should_show = bool(c._search_layer_visibility.get(file_path, False))
            is_dem_asset = c._is_dem_asset(asset)

            if not should_show:
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

            if (
                is_dem_asset
                and c._active_dem_search_layer_key
                and c._active_dem_search_layer_key != file_path
            ):
                c._search_layer_visibility[file_path] = False
                c._run_js_call("setLayerVisibility", file_path, False)
                continue

            if is_dem_asset and c._active_dem_search_layer_key == file_path:
                continue

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

        c._apply_display_control_mode()

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
        print(f"\n{'=' * 80}")
        print(f"DEBUG: _sync_search_visibility_layers called")
        print(f"  Current visibility map: {c._search_layer_visibility}")
        print(f"  Last synced visibility: {c._last_synced_visibility}")
        print(f"  Loaded layer keys: {c._loaded_search_layer_keys}")
        print(f"  Active DEM layer key: {c._active_dem_search_layer_key}")
        print(f"{'=' * 80}\n")

        for file_path, asset in c._search_result_assets_by_path.items():
            should_show = bool(c._search_layer_visibility.get(file_path, False))
            last_synced = c._last_synced_visibility.get(file_path, None)
            is_dem_asset = c._is_dem_asset(asset)
            file_name = asset.get("file_name", "unknown")
            is_loaded = file_path in c._loaded_search_layer_keys

            print(f"DEBUG: Processing layer: {file_name}")
            print(f"  file_path: {file_path}")
            print(f"  should_show: {should_show}")
            print(f"  last_synced: {last_synced}")
            print(f"  is_dem: {is_dem_asset}")
            print(f"  is_loaded: {is_loaded}")

            # OPTIMIZATION: Skip if visibility hasn't changed since last sync
            if last_synced is not None and last_synced == should_show and is_loaded:
                print(
                    f"  SKIP: Visibility unchanged (already {'visible' if should_show else 'hidden'})"
                )
                continue

            if not should_show:
                if is_loaded:  # Only hide if it's actually loaded
                    print(f"  ACTION: Hiding layer via setLayerVisibility")
                    c._run_js_call("setLayerVisibility", file_path, False)
                    c._last_synced_visibility[file_path] = False
                    if is_dem_asset and c._active_dem_search_layer_key == file_path:
                        c.state.active_layer_is_dem = False
                        c._active_dem_search_layer_key = None
                        c._apply_display_control_mode()
                        print(f"  DEM deactivated")
                else:
                    print(f"  SKIP: Layer not loaded, no need to hide")
                continue

            if is_dem_asset and is_loaded:
                print(f"  ACTION: Showing DEM layer via setLayerVisibility")
                c._run_js_call("setLayerVisibility", file_path, True)
                c._last_synced_visibility[file_path] = True
                c.state.active_layer_is_dem = True
                c._active_dem_search_layer_key = file_path
                c._apply_display_control_mode()
                print(f"  DEM activated")
                continue

            if (
                is_dem_asset
                and c._active_dem_search_layer_key
                and c._active_dem_search_layer_key != file_path
            ):
                print(f"  ACTION: Hiding DEM (another DEM is active)")
                c._search_layer_visibility[file_path] = False
                if is_loaded:
                    c._run_js_call("setLayerVisibility", file_path, False)
                    c._last_synced_visibility[file_path] = False
                continue

            if is_dem_asset and c._active_dem_search_layer_key == file_path:
                print(f"  SKIP: DEM already active")
                continue

            if (not is_dem_asset) and is_loaded:
                print(f"  ACTION: Showing imagery layer via setLayerVisibility")
                c._run_js_call("setLayerVisibility", file_path, True)
                c._last_synced_visibility[file_path] = True
                continue

            if not is_loaded:
                print(f"  ACTION: Loading new layer")
                loaded = c._load_asset_layer(
                    asset,
                    replace_existing=False,
                    layer_key=file_path,
                    auto_fly_to=False,
                    apply_scene_mode=False,
                    show_loading=False,
                )
                if not loaded:
                    print(f"  ERROR: Failed to load layer")
                    c._search_layer_visibility[file_path] = False
                    continue

                c._loaded_search_layer_keys.add(file_path)
                c._last_synced_visibility[file_path] = True
                print(f"  SUCCESS: Layer loaded and added to loaded keys")

        c._apply_display_control_mode()
        print(f"DEBUG: _sync_search_visibility_layers completed\n")

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
        if not visible_assets:
            c._last_visible_focus_signature = None
            return

        union_bounds: dict[str, float] | None = None
        for asset in visible_assets:
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
                if len(visible_assets) == 1:
                    # Single asset: fly to it with appropriate zoom
                    self._logger.info("First search: Flying to single asset")
                    c._fly_to_asset(visible_assets[0])
                    c.panel.log(
                        f"Focused on search result: {visible_assets[0].get('file_name', 'asset')}"
                    )
                else:
                    # Multiple assets: fit all in view with padding
                    self._logger.info(
                        f"First search: Fitting {len(visible_assets)} assets in view"
                    )
                    c._run_js_call(
                        "focusBoundsWithPadding",
                        union_bounds["west"],
                        union_bounds["south"],
                        union_bounds["east"],
                        union_bounds["north"],
                        1.5,  # 50% padding to ensure all assets are visible
                    )
                    c.panel.log(f"Focused on {len(visible_assets)} search results")
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

        # Fallback: focus on first visible asset
        c._fly_to_asset(visible_assets[0])

    def reorder_layers_event_driven(self, reordered_assets: list[dict]) -> None:
        """Reorder layers using event-driven approach for optimal performance.

        CRITICAL: We reorder ALL layers that are loaded, regardless of current visibility.
        The visibility state is managed separately by the toggle buttons.
        """
        c = self._controller
        try:
            print(f"\n{'=' * 80}")
            print(
                f"DEBUG: _reorder_layers_event_driven called with {len(reordered_assets)} assets"
            )
            print(
                f"DEBUG: Current _loaded_search_layer_keys: {c._loaded_search_layer_keys}"
            )
            print(
                f"DEBUG: Current _search_result_assets_by_path keys: {list(c._search_result_assets_by_path.keys())}"
            )
            print(f"{'=' * 80}\n")

            # Build layer reorder commands for the JavaScript bridge
            layer_commands = []
            for i, asset in enumerate(reordered_assets):
                file_path = str(asset.get("file_path", "")).replace("\\", "/")
                if not file_path:
                    print(f"  WARNING: Asset {i} has no file_path")
                    continue

                print(
                    f"  Processing asset {i}: {asset.get('file_name', 'Unknown')} - {file_path}"
                )

                # Check if this layer is actually loaded on the map
                if file_path not in c._loaded_search_layer_keys:
                    print(
                        f"  SKIP: Layer not in _loaded_search_layer_keys: {file_path}"
                    )
                    self._logger.debug(
                        "Skipping layer reorder for %s: not loaded on map",
                        asset.get("file_name", ""),
                    )
                    continue

                print(
                    f"  INCLUDE: Layer found in _loaded_search_layer_keys: {file_path}"
                )

                # Include the layer in reordering regardless of visibility state
                # The visibility is controlled by the toggle button, not by reordering
                layer_commands.append(
                    {
                        "layer_key": file_path,
                        "file_name": asset.get("file_name", ""),
                        "kind": asset.get("kind", ""),
                        "new_order": i,
                        "is_dem": c._is_dem_asset(asset),
                    }
                )

            print(f"DEBUG: Built {len(layer_commands)} layer commands")

            if layer_commands:
                # Log the reordering plan for debugging
                print(f"DEBUG: EVENT_DRIVEN Layer reordering plan:")
                for cmd in layer_commands:
                    print(
                        f"  Order {cmd['new_order']}: {cmd['file_name']} ({cmd['kind']}) - key={cmd['layer_key']}"
                    )

                # Send batch reorder command to Cesium
                print(f"DEBUG: Sending reorderLayersEventDriven command to JavaScript")
                c._run_js_call("reorderLayersEventDriven", layer_commands)
                self._logger.info(
                    "EVENT_DRIVEN: Sent %d layer reorder commands", len(layer_commands)
                )

                # Force additional render after reordering
                c._run_js_call("requestSceneRender")
                print(f"DEBUG: Reorder commands sent successfully")
            else:
                print(f"WARNING: No loaded layers found to reorder")
                self._logger.warning("EVENT_DRIVEN: No loaded layers found to reorder")
                c.panel.log("Layer reordering: No loaded layers found on map")

                # Debug: Show what layers we have vs what we're looking for
                print(
                    f"DEBUG: Available loaded layer keys: {c._loaded_search_layer_keys}"
                )
                print(
                    f"DEBUG: Requested asset paths: {[asset.get('file_path', '') for asset in reordered_assets]}"
                )

        except Exception as e:
            print(f"ERROR: Event-driven layer reordering failed: {e}")
            import traceback

            traceback.print_exc()
            self._logger.warning(
                "Event-driven layer reordering failed, falling back to standard: %s", e
            )
            c.panel.log(
                f"Layer reordering: Event-driven approach failed, using fallback"
            )
            self.reorder_layers_standard(reordered_assets)

    def reorder_layers_standard(self, reordered_assets: list[dict]) -> None:
        """Reorder layers using standard approach.

        CRITICAL: Reorder ALL loaded layers, not just visible ones.
        """
        c = self._controller
        try:
            # For standard approach, we need to manipulate the Cesium layer stack
            # by raising/lowering layers to achieve the desired order
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

            # Reorder loaded layers from bottom to top (reverse order)
            self._logger.info("STANDARD: Reordering %d layers", len(loaded_layers))
            for layer_key in reversed(loaded_layers):
                c._run_js_call("raiseLayerToTop", layer_key)

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
