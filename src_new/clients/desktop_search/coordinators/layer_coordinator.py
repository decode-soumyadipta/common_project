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
        """Toggle visibility of a search result layer with debug logging."""
        c = self._controller
        print(f"\n{'=' * 80}")
        print(f"DEBUG: toggle_search_result_visibility called")
        print(f"  file_path: {file_path}")
        print(f"  visible (requested): {visible}")
        print(f"  Current visibility map: {c._search_layer_visibility}")
        print(f"{'=' * 80}\n")

        normalized_path = str(file_path or "").strip().replace("\\", "/")
        if not normalized_path:
            print("DEBUG: Visibility toggle ignored: missing asset path")
            c.panel.log("Visibility toggle ignored: missing asset path.")
            return

        asset = c._search_result_assets_by_path.get(normalized_path)
        if not isinstance(asset, dict):
            print(
                f"DEBUG: Visibility toggle ignored: asset not in search results for path={normalized_path}"
            )
            print(
                f"DEBUG: Available paths in search results: {list(c._search_result_assets_by_path.keys())}"
            )
            c.panel.log(
                "Visibility toggle ignored: asset is no longer in current search results."
            )
            return

        next_visible = bool(visible)
        print(
            f"DEBUG: Asset found: {asset.get('file_name')}, kind={asset.get('kind')}, next_visible={next_visible}"
        )

        if next_visible and c._is_dem_asset(asset):
            print("DEBUG: Showing DEM - hiding other DEM layers")
            for path, candidate in c._search_result_assets_by_path.items():
                if path != normalized_path and c._is_dem_asset(candidate):
                    c._search_layer_visibility[path] = False
                    print(f"DEBUG: Hiding other DEM: {candidate.get('file_name')}")

        c._search_layer_visibility[normalized_path] = next_visible
        print(f"DEBUG: Updated visibility map: {normalized_path} = {next_visible}")
        print(
            f"DEBUG: Full visibility map after update: {c._search_layer_visibility}"
        )

        c._sync_search_visibility_layers()

        if c._search_layer_visibility.get(normalized_path, False):
            c.panel.log(f"Shown on map: {asset.get('file_name', 'asset')}")
            print(f"DEBUG: Layer shown: {asset.get('file_name')}")
        else:
            c.panel.log(f"Hidden from map: {asset.get('file_name', 'asset')}")
            print(f"DEBUG: Layer hidden: {asset.get('file_name')}")

        print(f"DEBUG: Calling panel.update_search_results to refresh UI")
        c.panel.update_search_results(
            list(c._search_result_assets_by_path.values()),
            c._search_layer_visibility,
        )
        print(f"DEBUG: toggle_search_result_visibility completed\n")

    def reorder_search_result_layers(self, reordered_layers: list[dict]) -> None:
        """Handle drag-and-drop reordering of search result layers with real-time globe updates."""
        c = self._controller
        print(f"\n{'=' * 80}")
        print(f"DEBUG: reorder_search_result_layers called in coordinator!")
        print(f"  reordered_layers: {reordered_layers}")
        print(f"{'=' * 80}\n")
        try:
            if not reordered_layers:
                print("DEBUG: No reordered layers, returning")
                return

            print(f"DEBUG: Processing {len(reordered_layers)} layers")

            # Track performance for event-driven architecture
            start_time = time.time()

            # Find corresponding assets using file_path (not file_name, to handle duplicates)
            reordered_assets = []
            for layer_info in reordered_layers:
                file_path = layer_info.get("file_path", "")
                if not file_path:
                    print(f"WARNING: Layer info missing file_path: {layer_info}")
                    continue

                # Normalize path for lookup
                normalized_path = file_path.replace("\\", "/")

                # Find the asset with matching file path
                if normalized_path in c._search_result_assets_by_path:
                    asset = c._search_result_assets_by_path[normalized_path]
                    # Add visibility info from the layer_info
                    asset_with_visibility = asset.copy()
                    asset_with_visibility["is_visible"] = layer_info.get(
                        "is_visible", True
                    )
                    reordered_assets.append(asset_with_visibility)
                    print(
                        f"  Matched asset: {asset.get('file_name', 'Unknown')} at {normalized_path} (visible={layer_info.get('is_visible', True)})"
                    )
                else:
                    print(f"  WARNING: No asset found for path: {normalized_path}")

            if not reordered_assets:
                c.panel.log("Layer reordering failed: No matching assets found")
                print(
                    "ERROR: No matching assets found in _search_result_assets_by_path"
                )
                print(
                    f"DEBUG: Available asset paths: {list(c._search_result_assets_by_path.keys())}"
                )
                print(
                    f"DEBUG: Requested paths: {[layer_info.get('file_path', '') for layer_info in reordered_layers]}"
                )
                return

            print(f"DEBUG: Found {len(reordered_assets)} matching assets")

            # CRITICAL FIX: Ensure all layers are actually loaded before reordering
            # Sometimes the reorder happens before layers are fully loaded
            missing_layers = []
            for asset in reordered_assets:
                file_path = str(asset.get("file_path", "")).replace("\\", "/")
                if file_path not in c._loaded_search_layer_keys:
                    missing_layers.append(asset)

            if missing_layers:
                print(
                    f"WARNING: {len(missing_layers)} layers not yet loaded, attempting to load them first"
                )
                for asset in missing_layers:
                    file_path = str(asset.get("file_path", "")).replace("\\", "/")
                    print(
                        f"  Loading missing layer: {asset.get('file_name', 'Unknown')} - {file_path}"
                    )

                    # Try to load the layer
                    loaded = c._load_asset_layer_event_driven(
                        asset,
                        replace_existing=False,
                        layer_key=file_path,
                        auto_fly_to=False,
                        apply_scene_mode=False,
                        show_loading=False,
                    )

                    if loaded:
                        c._loaded_search_layer_keys.add(file_path)
                        print(f"  Successfully loaded missing layer: {file_path}")
                    else:
                        print(f"  Failed to load missing layer: {file_path}")

                # Small delay to allow layers to initialize
                time.sleep(0.1)

            # Update the Cesium layer stack order using event-driven approach
            if c._event_driven_enabled:
                c._reorder_layers_event_driven(reordered_assets)
            else:
                c._reorder_layers_standard(reordered_assets)

            # Track performance metrics
            elapsed_time = time.time() - start_time
            c._track_performance_metric(
                "layer_reorder_times", elapsed_time, f"layers={len(reordered_layers)}"
            )

            # Log the successful reordering
            layer_names = [
                asset.get("file_name", "Unknown") for asset in reordered_assets
            ]
            if len(layer_names) <= 3:
                c.panel.log(f"Layers reordered: {', '.join(layer_names)}")
            else:
                c.panel.log(
                    f"Layers reordered: {', '.join(layer_names[:3])} and {len(layer_names) - 3} more"
                )

            c._logger.info(
                "Search result layers reordered: %d layers in %.3fs",
                len(reordered_layers),
                elapsed_time,
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
