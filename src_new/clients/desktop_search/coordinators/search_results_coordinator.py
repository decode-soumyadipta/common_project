from __future__ import annotations

import logging
import re
from pathlib import Path

from qtpy.QtCore import QTimer


class SearchResultsCoordinator:
    """Encapsulate search results processing and management for desktop controller."""

    def __init__(self, controller):
        self._controller = controller
        self._logger = logging.getLogger("client_desktop.search_results_coordinator")

    def apply_search_results(self, assets: list[dict], label: str) -> None:
        """Apply search results with standard processing."""
        self._apply_search_results_internal(assets, label, event_driven=False)

    def apply_search_results_event_driven(
        self, assets: list[dict], label: str
    ) -> None:
        """Apply search results with event-driven optimization."""
        self._apply_search_results_internal(assets, label, event_driven=True)

    def _apply_search_results_internal(
        self, assets: list[dict], label: str, event_driven: bool = False
    ) -> None:
        """Internal method to apply search results with optional event-driven optimization."""
        c = self._controller
        assets = self._dedupe_assets(assets)
        
        # Preserve the catalog view when search returns 0 results.
        previous_assets = c._search_result_assets_by_path
        if not assets:
            c._logger.info("Search returned 0 results; preserving asset catalog")
            c._run_js_call("clearSearchResultMarkers")
            c.panel.log("No results in search area; showing all available assets.")
            return
        
        c.panel.assets_combo.clear()
        c._asset_cache = {}
        previously_visible_paths = {
            path
            for path, is_visible in c._search_layer_visibility.items()
            if is_visible
        }
        had_visible_assets = bool(previously_visible_paths)
        c._search_result_assets_by_path = {}
        local_missing_count = 0

        # Event-driven optimization: Pre-process assets for terabyte-scale performance
        if event_driven:
            assets = self._preprocess_assets_for_terabyte_scale(assets)

        for asset in assets:
            if not c._asset_path_accessible_locally(asset):
                local_missing_count += 1
            file_path = str(asset.get("file_path") or "").replace("\\", "/")
            if not file_path:
                continue

            # Ensure tile_url is populated for all search results
            if "tile_url" not in asset or not asset["tile_url"]:
                from src_new.clients.desktop_search.tile_url_builder import build_xyz_url
                try:
                    cand = c._find_best_file_version(file_path)
                    asset["tile_url"] = build_xyz_url(cand, tile_service_url=c.api.titiler_base_url)
                except Exception as e:
                    c._logger.error("Failed to build tile_url for asset: %s", e)

            c._asset_cache[file_path] = asset
            c._search_result_assets_by_path[file_path] = asset

            # Event-driven display optimization
            display_suffix = ""
            if event_driven and asset.get("performance_tier") == "ultra_large":
                display_suffix = " [TB-Scale]"
            elif event_driven and asset.get("performance_tier") == "large":
                display_suffix = " [Large]"

            display = f"{asset['file_name']} [{asset['kind']}]{display_suffix}"
            c.panel.assets_combo.addItem(display, asset)

        self._merge_user_added_assets()

        current_paths = set(c._search_result_assets_by_path.keys())
        stale_visible_paths = previously_visible_paths - current_paths
        for stale_path in stale_visible_paths:
            c._run_js_call("setLayerVisibility", stale_path, False)
            c._loaded_search_layer_keys.discard(stale_path)
            stale_asset = previous_assets.get(stale_path)
            if isinstance(stale_asset, dict) and c._is_dem_asset(stale_asset):
                c.state.active_layer_is_dem = False
                c._active_dem_search_layer_key = None
                c.panel.rgb_view_mode_combo.setEnabled(True)
                c.panel.apply_rgb_view_mode_btn.setEnabled(True)

        c._search_layer_visibility = {
            path: bool(c._search_layer_visibility.get(path, False))
            for path in c._search_result_assets_by_path
        }

        c._logger.info(
            "Search results applied: assets=%d visible=%d event_driven=%s label=%s",
            len(c._search_result_assets_by_path),
            sum(1 for visible in c._search_layer_visibility.values() if visible),
            event_driven,
            label,
        )

        c._set_search_aoi_visible(True)

        # Event-driven layer synchronization
        if event_driven:
            c._sync_search_visibility_layers_event_driven()
        else:
            c._sync_search_visibility_layers()

        c._refresh_search_result_markers()
        c._logger.info(
            "Search markers refreshed after layer sync: assets=%d",
            len(c._search_result_assets_by_path),
        )
        c._logger.info(
            "Search marker refresh queued again after settle: event_driven=%s label=%s",
            event_driven,
            label,
        )

        # FIX 1 — Layer order: enforce display order matching the UI list.
        # UI display sort: imagery (non-DEM) at row 0 = visually ON TOP in Cesium.
        # IMPORTANT: sort imagery before DEM so JS raises imagery to the top correctly.
        # (Previously we used dict insertion order which was API order = DEM first → wrong.)
        ordered_keys = sorted(
            [
                p.replace("\\", "/")
                for p in c._search_result_assets_by_path.keys()
                if c._search_layer_visibility.get(p, True)
            ],
            key=lambda p: (
                1 if c._is_dem_asset(c._search_result_assets_by_path.get(p, {})) else 0,
                p,  # stable tie-break by path
            ),
        )
        if ordered_keys:
            c._run_js_call("enforceLayerDisplayOrder", ordered_keys)

        # FIX 2 — Fly-to: single controlled fly-to AFTER layers+order are set,
        # so the globe is never blank during flight.
        c._focus_visible_search_assets_with_enhanced_behavior(
            force=not had_visible_assets,
            is_first_search=not had_visible_assets,
            asset_count=len(assets),
        )

        c.panel.update_search_results(
            list(c._search_result_assets_by_path.values()),
            c._search_layer_visibility,
        )
        QTimer.singleShot(0, c._refresh_search_result_markers)
        QTimer.singleShot(250, c._refresh_search_result_markers)
        c.panel.log(
            f"Marker refresh scheduled for {len(c._search_result_assets_by_path)} search result(s)."
        )

        # Enhanced logging for event-driven mode
        if event_driven:
            terabyte_count = sum(
                1 for a in assets if a.get("performance_tier") == "ultra_large"
            )
            large_count = sum(1 for a in assets if a.get("performance_tier") == "large")
            c.panel.log(
                f"{label}: {c.panel.assets_combo.count()} assets (TB-scale: {terabyte_count}, Large: {large_count})"
            )
        else:
            c.panel.log(f"{label}: {c.panel.assets_combo.count()} assets")

        if local_missing_count:
            c.panel.log(
                f"Note: {local_missing_count} result(s) are remote-only paths; loading uses server-side tiles."
            )

    def _preprocess_assets_for_terabyte_scale(self, assets: list[dict]) -> list[dict]:
        """Preprocess assets for terabyte-scale performance optimization."""
        c = self._controller
        processed = []

        for asset in assets:
            # Add event-driven optimization metadata
            processed_asset = dict(asset)

            # Determine performance tier based on file size
            file_size = asset.get("file_size_bytes", 0)
            if file_size > 1_000_000_000_000:  # > 1TB
                processed_asset["performance_tier"] = "ultra_large"
                processed_asset["ui_priority"] = "high"
            elif file_size > 100_000_000_000:  # > 100GB
                processed_asset["performance_tier"] = "large"
                processed_asset["ui_priority"] = "medium"
            else:
                processed_asset["performance_tier"] = "standard"
                processed_asset["ui_priority"] = "normal"

            # Add server optimization flags
            processed_asset["event_driven"] = True
            processed_asset["server_optimized"] = True

            processed.append(processed_asset)

        # Sort by performance tier and size for optimal display order
        processed.sort(
            key=lambda a: (
                a.get("performance_tier") == "ultra_large",
                a.get("performance_tier") == "large",
                a.get("file_size_bytes", 0),
            ),
            reverse=True,
        )

        c._logger.info(
            "Preprocessed %d assets for terabyte-scale performance", len(processed)
        )
        return processed

    @staticmethod
    def _asset_identity_key(asset: dict) -> str:
        """Generate a unique identity key for an asset."""
        file_name = str(asset.get("file_name") or asset.get("file_path") or "")
        base = file_name.replace("\\", "/").split("/")[-1].lower()
        base = re.sub(r"_3857\.cog\.(tif|tiff)$", ".tif", base)
        base = re.sub(r"\.cog\.(tif|tiff)$", ".tif", base)
        base = re.sub(r"_3857\.(tif|tiff)$", ".tif", base)
        base = re.sub(r"\.(tif|tiff|jp2|j2k|mbtiles)$", "", base)
        base = base.replace(" ", "_").replace("-", "_")
        kind = str(asset.get("kind") or "").lower()
        return f"{kind}:{base}"

    @staticmethod
    def _is_cog_asset(asset: dict) -> bool:
        """Check if an asset is a Cloud Optimized GeoTIFF."""
        name = str(asset.get("file_name") or asset.get("file_path") or "").lower()
        return ".cog." in name or name.endswith(".cog.tif") or name.endswith(".cog.tiff")

    def _dedupe_assets(self, assets: list[dict]) -> list[dict]:
        """Deduplicate assets based on identity key, preferring non-COG versions."""
        c = self._controller
        if not assets:
            return assets
        deduped: list[dict] = []
        index_by_key: dict[str, int] = {}
        for asset in assets:
            key = self._asset_identity_key(asset)
            if key in index_by_key:
                existing_idx = index_by_key[key]
                existing = deduped[existing_idx]
                if not self._is_cog_asset(asset) and self._is_cog_asset(existing):
                    deduped[existing_idx] = asset
                continue
            index_by_key[key] = len(deduped)
            deduped.append(asset)
            
        for asset in deduped:
            if self._is_cog_asset(asset):
                file_path = str(asset.get("file_path", ""))
                if file_path:
                    candidates = []
                    cand1 = re.sub(r"_3857\.cog\.(tif|tiff)$", r".\1", file_path, flags=re.IGNORECASE)
                    if cand1 != file_path:
                        candidates.append(cand1)
                    cand2 = re.sub(r"\.cog\.(tif|tiff)$", r".\1", file_path, flags=re.IGNORECASE)
                    if cand2 != file_path:
                        candidates.append(cand2)
                    cand3 = re.sub(r"\.cog\.(tif|tiff)$", r".\1", cand1, flags=re.IGNORECASE)
                    if cand3 != cand1 and cand3 != file_path:
                        candidates.append(cand3)
                        
                    for cand in candidates:
                        try:
                            if Path(cand).exists():
                                asset["file_path"] = cand
                                asset["file_name"] = Path(cand).name
                                if "tile_url" in asset:
                                    try:
                                        from src_new.clients.desktop_search.tile_url_builder import build_xyz_url
                                        asset["tile_url"] = build_xyz_url(cand)
                                    except Exception as e:
                                        c._logger.error("Failed to build tile_url for reverted asset: %s", e)
                                c._logger.info("Reverted isolated COG asset to original path: %s", cand)
                                break
                        except Exception:
                            pass
                            
        if len(deduped) != len(assets):
            c._logger.info("Deduped assets: %d -> %d (Original non-COG preferred)", len(assets), len(deduped))
        return deduped

    def _merge_user_added_assets(self) -> None:
        """Merge user-added assets into search results."""
        c = self._controller
        for path, asset in c._user_added_assets.items():
            normalized_path = str(path).replace("\\", "/")
            if not normalized_path:
                continue
            if normalized_path in c._search_result_assets_by_path:
                continue
            c._search_result_assets_by_path[normalized_path] = asset
            c._asset_cache[normalized_path] = asset
            if normalized_path not in c._search_layer_visibility:
                c._search_layer_visibility[normalized_path] = True
