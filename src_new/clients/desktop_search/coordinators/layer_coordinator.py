from __future__ import annotations

import datetime as dt
import logging
import time
from pathlib import Path

from qtpy.QtWidgets import QFileDialog


class LayerCoordinator:
    """Encapsulate layer management operations for desktop controller."""

    def __init__(self, controller):
        self._controller = controller
        self._logger = logging.getLogger("client_desktop.layer_coordinator")

    def add_raster_layers(self) -> None:
        """Add raster layers from file selection dialog."""
        c = self._controller
        file_filter = (
            "Raster Files (*.tif *.tiff *.jp2 *.j2k *.mbtiles);;All Files (*)"
        )
        files, _ = QFileDialog.getOpenFileNames(
            c.panel,
            "Add Raster Layers",
            "",
            file_filter,
        )
        if not files:
            return

        added = 0
        for file_path in files:
            asset = c._create_raster_asset_from_path(file_path)
            if not asset:
                continue
            normalized_path = str(asset.get("file_path") or "").replace("\\", "/")
            if not normalized_path:
                continue

            c._user_added_assets[normalized_path] = asset
            c._search_result_assets_by_path[normalized_path] = asset
            c._search_layer_visibility[normalized_path] = True
            loaded = c._load_asset_layer(
                asset,
                replace_existing=False,
                layer_key=normalized_path,
                auto_fly_to=added == 0,
                apply_scene_mode=False,
                show_loading=True,
                skip_cog=True,
            )
            if loaded:
                c._loaded_search_layer_keys.add(normalized_path)
                added += 1
        if added:
            c.panel.log(f"Added {added} raster layer(s).")
            c.panel.update_search_results(
                list(c._search_result_assets_by_path.values()),
                c._search_layer_visibility,
            )
            c._refresh_search_result_markers()
            c._set_project_modified(True)

        else:
            c.panel.log("No raster layers were added.")
        
        c._set_layer_loading(False, "Ready")

    def add_vector_layers(self) -> None:
        """Add vector layers from file selection dialog."""
        c = self._controller
        file_filter = (
            "Vector Files (*.geojson *.json *.shp *.kml);;All Files (*)"
        )
        files, _ = QFileDialog.getOpenFileNames(
            c.panel,
            "Add Vector Layers",
            "",
            file_filter,
        )
        if not files:
            return

        added = 0
        for file_path in files:
            geojson = c._read_vector_geojson(Path(file_path))
            if not geojson:
                continue
            label = Path(file_path).stem
            normalized_path = str(file_path).replace("\\", "/")
            layer_key = c._make_unique_vector_key(f"vector:{normalized_path}")
            c._run_js_call("addVectorLayer", layer_key, label, geojson, {})
            c._vector_layers[layer_key] = {
                "layer_key": layer_key,
                "label": label,
                "file_path": normalized_path,
                "source": Path(file_path).suffix.lstrip(".").lower() or "file",
                "geojson": geojson,
                "is_visible": True,
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
            c._set_project_modified(True)
            added += 1


        c._refresh_vector_layers_ui()
        if added:
            c.panel.log(f"Added {added} vector layer(s).")
        else:
            c.panel.log("No vector layers were added.")

    def remove_search_layer(self, file_path: str) -> None:
        """Remove a search result layer from the map and internal state."""
        c = self._controller
        normalized_path = str(file_path or "").replace("\\", "/")
        if not normalized_path:
            return
        asset = c._search_result_assets_by_path.get(normalized_path)
        if not asset:
            c.panel.log("Layer not found.")
            return

        c._run_js_call("removeLayerByKey", normalized_path)
        c._loaded_search_layer_keys.discard(normalized_path)
        c._search_layer_visibility.pop(normalized_path, None)
        c._last_synced_visibility.pop(normalized_path, None)
        c._search_result_assets_by_path.pop(normalized_path, None)
        c._asset_cache.pop(normalized_path, None)
        c._user_added_assets.pop(normalized_path, None)
        if c._active_dem_search_layer_key == normalized_path:
            c._active_dem_search_layer_key = None
            c.state.active_layer_is_dem = False
        if hasattr(c.panel, "_layer_order_registry"):
            c.panel._layer_order_registry.pop(normalized_path, None)
        if c.state.selected_asset and str(c.state.selected_asset.get("file_path") or "").replace("\\", "/") == normalized_path:
            c.state.selected_asset = None

        c._apply_display_control_mode()
        c.panel.update_search_results(
            list(c._search_result_assets_by_path.values()),
            c._search_layer_visibility,
        )
        c._set_project_modified(True)

    def set_vector_layer_visibility(self, layer_key: str, visible: bool) -> None:
        """Toggle visibility of a vector layer."""
        c = self._controller
        key = str(layer_key or "")
        if not key or key not in c._vector_layers:
            return
        c._vector_layers[key]["is_visible"] = bool(visible)
        c._run_js_call("setVectorLayerVisibility", key, bool(visible))
        c._refresh_vector_layers_ui()

    def remove_vector_layer(self, layer_key: str) -> None:
        """Remove a vector layer from the map."""
        c = self._controller
        key = str(layer_key or "")
        if not key or key not in c._vector_layers:
            return
        layer = c._vector_layers.pop(key)
        c._run_js_call("removeVectorLayer", key)
        if layer.get("source") == "annotations":
            c._annotation_line_records = []
            c._annotation_polygon_records = []
        c._refresh_vector_layers_ui()

    def toggle_search_result_visibility(self, file_path: str, visible: bool) -> None:
        """Toggle visibility of a search result layer on the map with proper debouncing."""
        c = self._controller

        normalized_path = str(file_path or "").strip().replace("\\", "/")
        if not normalized_path:
            c.panel.log("Visibility toggle ignored: missing asset path.")
            return

        # CRITICAL FIX: Prevent rapid successive clicks from queuing multiple operations
        # and causing hangs. Use a debounce mechanism with a flag.
        import time
        current_time = time.time()
        
        # Check if this path was recently toggled (within 100ms)
        last_toggle_time = c._visibility_toggle_debounce.get(normalized_path, 0)
        if current_time - last_toggle_time < 0.1:  # 100ms debounce window
            print(f"DEBUG: Ignoring rapid click on {normalized_path} (debounced)")
            return
        
        c._visibility_toggle_debounce[normalized_path] = current_time

        asset = c._search_result_assets_by_path.get(normalized_path)
        if not isinstance(asset, dict):
            c.panel.log(
                "Visibility toggle ignored: asset is no longer in current search results."
            )
            return

        next_visible = bool(visible)

        # CRITICAL FIX: Prevent multiple concurrent visibility operations
        if c._visibility_sync_in_progress:
            print(f"DEBUG: Visibility sync already in progress, queuing toggle for {normalized_path}")
            return
        
        # Mark sync as in progress
        c._visibility_sync_in_progress = True
        
        try:
            # DEM exclusivity: only one DEM layer visible at a time
            if next_visible and c._is_dem_asset(asset):
                for path, candidate in c._search_result_assets_by_path.items():
                    if path != normalized_path and c._is_dem_asset(candidate):
                        c._search_layer_visibility[path] = False

            c._search_layer_visibility[normalized_path] = next_visible

            print(f"DEBUG: Syncing visibility for {normalized_path}: {next_visible}")
            
            # Determine if this is a new layer that needs loading
            needs_loading = next_visible and normalized_path not in c._loaded_search_layer_keys
            
            if needs_loading:
                # Set loading state for new layer
                c._set_layer_loading(True, f"Loading {asset.get('file_name', 'layer')}...")
            
            if c._event_driven_enabled:
                c._sync_search_visibility_layers_event_driven()
            else:
                c._sync_search_visibility_layers()

            if c._search_layer_visibility.get(normalized_path, False):
                c.panel.log(f"Shown on map: {asset.get('file_name', 'asset')}")
                # Use instantFocusBounds (snap camera immediately) so Cesium requests
                # tiles at the correct zoom level from the very first render frame.
                # flyToBounds (animated, 2s) causes the camera to be at a high altitude
                # during the animation where minzoom=11 tiles aren't requested → blank globe.
                from qtpy.QtCore import QTimer
                # Increased delay to ensure layer sync completes before camera movement
                QTimer.singleShot(250, lambda: self._safe_zoom_to_asset(c, normalized_path, needs_loading))
            else:
                c.panel.log(f"Hidden from map: {asset.get('file_name', 'asset')}")
                # Clear loading state when hiding a layer
                c._set_layer_loading(False, "Ready")

            # Update UI with current visibility state
            c.panel.update_search_results(
                list(c._search_result_assets_by_path.values()),
                c._search_layer_visibility,
            )
            c._refresh_search_result_markers()
        finally:
            # Always clear the in-progress flag
            c._visibility_sync_in_progress = False
    
    def _safe_zoom_to_asset(self, c, file_path: str, was_loading: bool = False) -> None:
        """Safely zoom to asset with error handling and validation."""
        try:
            # Verify asset still exists
            if file_path not in c._search_result_assets_by_path:
                print(f"DEBUG: Asset {file_path} no longer in search results, skip zoom")
                if was_loading:
                    c._set_layer_loading(False, "Ready")
                return
            
            # Verify layer was actually loaded
            if file_path not in c._loaded_search_layer_keys:
                print(f"DEBUG: Asset {file_path} not loaded yet, skip zoom")
                if was_loading:
                    c._set_layer_loading(False, "Ready")
                return
            
            c._toolbar_zoom_to_asset(file_path)
        except Exception as e:
            print(f"DEBUG: Error during zoom to asset {file_path}: {e}")
            # Log but don't fail - the layer is still visible even if zoom fails
        finally:
            # Always clear loading state after zoom attempt
            if was_loading:
                c._set_layer_loading(False, "Ready")

    def reorder_search_result_layers(self, reordered_layers: list[dict]) -> None:
        """Handle drag-and-drop reordering of search result layers with real-time globe updates."""
        c = self._controller
        try:
            if not reordered_layers:
                return

            start_time = time.time()

            # Resolve file_path → asset objects from the current search result registry
            reordered_assets = []
            for layer_info in reordered_layers:
                file_path = layer_info.get("file_path", "")
                if not file_path:
                    continue
                normalized_path = file_path.replace("\\", "/")
                asset = c._search_result_assets_by_path.get(normalized_path)
                if asset:
                    asset_with_vis = asset.copy()
                    asset_with_vis["is_visible"] = layer_info.get("is_visible", True)
                    reordered_assets.append(asset_with_vis)
                else:
                    c._logger.debug(
                        "reorder: no asset found for path=%s", normalized_path
                    )

            if not reordered_assets:
                c.panel.log("Layer reordering failed: no matching assets found")
                c._logger.warning(
                    "reorder_search_result_layers: none of the %d requested paths "
                    "matched _search_result_assets_by_path",
                    len(reordered_layers),
                )
                return

            # REORDER-ONLY — never load layers here.
            #
            # _loaded_search_layer_keys tracks which assets have been sent to Cesium.
            # Assets loaded via the search-results sync flow are added to this set by
            # sync_focus_coordinator (lines ~65 and ~211).  Assets not yet in the set
            # are simply not present in the Cesium imagery stack yet; telling Cesium to
            # reorder them would be a no-op at best and a full re-render at worst.
            #
            # Previously this block attempted to load every "missing" layer, which caused
            # ALL assets to be re-rendered on every drag-and-drop reorder (because the set
            # was empty for layers loaded through the search path), freezing the application.
            loaded_for_reorder = [
                asset
                for asset in reordered_assets
                if str(asset.get("file_path", "")).replace("\\", "/")
                in c._loaded_search_layer_keys
            ]

            skipped_count = len(reordered_assets) - len(loaded_for_reorder)
            if skipped_count:
                c._logger.debug(
                    "reorder: skipping %d asset(s) not yet in Cesium stack "
                    "(will be ordered correctly on next visibility sync)",
                    skipped_count,
                )

            if not loaded_for_reorder:
                c._logger.info(
                    "reorder: no loaded assets yet — reorder deferred until layers are ready"
                )
                return

            # Issue the reorder to the Cesium bridge (pure stack rearrangement, no reload)
            if c._event_driven_enabled:
                c._reorder_layers_event_driven(loaded_for_reorder)
            else:
                c._reorder_layers_standard(loaded_for_reorder)

            elapsed = time.time() - start_time
            c._track_performance_metric(
                "layer_reorder_times", elapsed, f"layers={len(loaded_for_reorder)}"
            )

            names = [a.get("file_name", "?") for a in loaded_for_reorder]
            summary = (
                ", ".join(names)
                if len(names) <= 3
                else f"{', '.join(names[:3])} and {len(names) - 3} more"
            )
            c.panel.log(f"Layers reordered: {summary}")
            c._logger.info(
                "Layers reordered: %d in %.3fs", len(loaded_for_reorder), elapsed
            )

        except Exception as e:
            c.panel.log(f"Layer reordering failed: {str(e)}")
            c._logger.error(
                "Failed to reorder search result layers: %s", e, exc_info=True
            )

    def add_selected_layer(self) -> None:
        """Add the currently selected asset as a layer."""
        c = self._controller
        asset = c._selected_asset()
        if not asset:
            c.panel.log("No selected asset.")
            c._logger.warning("Add layer requested with no selected asset")
            return
        loaded_asset = c._load_asset_layer(asset)
        if not loaded_asset:
            return
        c.panel.log(f"Layer added: {loaded_asset['file_name']}")
        c._logger.info(
            "Layer add requested name=%s kind=%s url=%s",
            loaded_asset["file_name"],
            loaded_asset["kind"],
            loaded_asset["tile_url"],
        )
