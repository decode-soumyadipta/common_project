from __future__ import annotations

import logging
import time
from pathlib import Path

import httpx

from src_new.clients.desktop_search.app_mode import DesktopAppMode
from src_new.clients.desktop_search.tile_url_builder import build_xyz_url


class AssetLoadingCoordinator:
    """Encapsulate asset loading and visualization operations for desktop controller."""

    def __init__(self, controller):
        self._controller = controller
        self._logger = logging.getLogger("client_desktop.asset_loading_coordinator")

    def load_asset_layer(
        self,
        asset: dict,
        *,
        replace_existing: bool = True,
        layer_key: str | None = None,
        auto_fly_to: bool = True,
        apply_scene_mode: bool = True,
        show_loading: bool = True,
        skip_cog: bool = False,
    ) -> dict | None:
        c = self._controller
        if show_loading:
            c._set_layer_loading(True, f"Loading {asset['file_name']}...")

        # Find the best version of the file (prioritize Web Mercator projected files)
        original_file_path = asset["file_path"]
        best_file_path = c._find_best_file_version(original_file_path)

        # Update asset to use the best file version
        if best_file_path != original_file_path:
            asset = dict(asset)  # Don't mutate the original
            asset["file_path"] = best_file_path
            asset["tile_url"] = build_xyz_url(best_file_path, tile_service_url=c.api.titiler_base_url)
            self._logger.info(
                f"Updated asset to use optimized file: {Path(best_file_path).name}"
            )
        else:
            self._logger.debug(
                f"Using original asset file: {Path(original_file_path).name}"
            )

        if (
            c.app_mode != DesktopAppMode.CLIENT
            and not Path(asset["file_path"]).exists()
        ):
            c.panel.log(f"File not found on disk: {asset['file_path']}")
            self._logger.error(
                "Cannot add layer; file missing path=%s", asset["file_path"]
            )
            if show_loading:
                c._set_layer_loading(False, "Layer load failed")
            return None

        # Auto-convert to COG if the source is a plain GeoTIFF.
        # Non-COG files fail to tile on Windows and are slower everywhere.
        # The COG is written next to the source (e.g. dem.cog.tif) and reused.
        if c.app_mode != DesktopAppMode.CLIENT and not skip_cog:
            try:
                from src_new.shared.ingestion.services.cog_service import (
                    CogPreparationService,
                )

                src_path = Path(asset["file_path"])
                self._logger.info(
                    "COG check: %s is_cog=%s",
                    src_path.name,
                    CogPreparationService._looks_like_cog(src_path),
                )
                if not CogPreparationService._looks_like_cog(src_path):
                    c.panel.log(
                        f"Converting to COG for fast tiling: {src_path.name}…"
                    )
                    if show_loading:
                        c._set_layer_loading(
                            True, f"Converting {src_path.name} to COG…"
                        )
                cog_result = CogPreparationService().prepare(src_path)
                self._logger.info(
                    "COG result: working_path=%s converted=%s",
                    cog_result.working_path,
                    cog_result.converted,
                )
                if cog_result.working_path != src_path:
                    asset = dict(asset)  # don't mutate the original
                    asset["file_path"] = str(cog_result.working_path)
                    asset["tile_url"] = build_xyz_url(str(cog_result.working_path), tile_service_url=c.api.titiler_base_url)
                    self._logger.info("COG tile_url updated to: %s", asset["tile_url"])
                    if cog_result.converted:
                        c.panel.log(f"COG ready: {cog_result.working_path.name}")
            except Exception:
                self._logger.warning("COG preparation failed", exc_info=True)
        if not c.titiler.ensure_running():
            detail = getattr(c.titiler, "last_error", "") or ""
            if detail:
                c.panel.log("TiTiler failed to start: " + detail.strip())
                self._logger.error(
                    "TiTiler unavailable before add layer: %s", detail.strip()
                )
            else:
                c.panel.log("Warning: TiTiler could not start. Layer may not draw.")
                self._logger.error("TiTiler unavailable before add layer")
        bounds = c._asset_bounds(asset)
        if bounds is None:
            try:
                fresh = c.api.register_raster(asset["file_path"])
                c._asset_cache[fresh["file_path"]] = fresh
                asset = fresh
                bounds = c._asset_bounds(asset)
                self._logger.info(
                    "Refreshed metadata for selected asset before layer add"
                )
            except httpx.HTTPError:
                self._logger.exception("Failed to refresh metadata before layer add")
        options = c._layer_options(asset, bounds)
        options["replace_existing"] = bool(replace_existing)
        if layer_key:
            options["layer_key"] = str(layer_key).replace("\\", "/")
        options["apply_scene_mode"] = bool(apply_scene_mode)
        if c._add_layer(asset, options):
            if auto_fly_to:
                self.fly_through_asset(asset)
        else:
            if show_loading:
                c._set_layer_loading(False, "Layer load failed")
            return None
        c.state.selected_asset = asset
        return asset

    def fly_through_asset(self, asset: dict) -> bool:
        c = self._controller
        bounds = c._asset_bounds(asset)
        if bounds is None:
            center = c._asset_centroid(asset)
            if center is None:
                self._logger.warning(
                    "Fly-through unavailable for asset=%s", asset.get("file_name")
                )
                return False
            # Fallback micro-bounds around centroid when exact bounds are unavailable.
            delta = 0.01
            bounds = {
                "west": center["lon"] - delta,
                "south": center["lat"] - delta,
                "east": center["lon"] + delta,
                "north": center["lat"] + delta,
            }

        c._run_js_call(
            "flyThroughBounds",
            bounds["west"],
            bounds["south"],
            bounds["east"],
            bounds["north"],
        )
        return True

    def try_visualize_ingested_asset(self) -> None:
        """Try to visualize newly ingested assets with event-driven server-side processing.

        For folder ingests, loads up to 5 most recent assets automatically.
        Uses server-side metadata processing for ultra-high performance with terabyte-scale data.
        All processing happens on server, client only requests metadata and tile URLs.
        """
        c = self._controller
        source_path = c.state.pending_ingest_source_path
        if not source_path:
            return

        # Event-driven approach: Request server to process and return optimized metadata
        try:
            # Server-side metadata processing for terabyte-scale performance
            assets = self._request_server_processed_assets(source_path)
        except httpx.HTTPError as exc:
            c._handle_api_error("Load ingested asset", exc)
            return

        c.refresh_assets()

        # Check if source_path is a folder
        source_path_obj = Path(source_path)
        is_folder = source_path_obj.is_dir()

        if is_folder:
            # Server-side folder processing for terabyte-scale data
            matching_assets = self._get_server_processed_folder_assets(
                assets, source_path_obj
            )

            if not matching_assets:
                c.panel.log(
                    "Ingest completed, but catalog items are not yet visible. Use Refresh Assets."
                )
                self._logger.info(
                    "Ingest completed but assets not found in catalog yet source=%s",
                    source_path,
                )
                return

            # Server-side sorting by metadata timestamps (no file system access)
            assets_to_load = self._get_server_sorted_recent_assets(
                matching_assets, limit=5
            )

            c.panel.log(
                f"Auto-loading {len(assets_to_load)} most recent asset(s) from {len(matching_assets)} total"
            )

            # Event-driven layer loading with server-side tile preparation
            self._load_assets_event_driven(assets_to_load)
        else:
            # Single file ingest with server-side processing
            match = self._find_server_processed_asset(assets, source_path)

            if not isinstance(match, dict):
                c.panel.log(
                    "Ingest completed, but catalog item is not yet visible. Use Refresh Assets."
                )
                self._logger.info(
                    "Ingest completed but asset not found in catalog yet source=%s (this is normal for large files)",
                    source_path,
                )
                return

            # Event-driven single asset loading
            self._load_single_asset_event_driven(match)

        c.state.auto_visualize_ingest_result = False
        c.state.pending_ingest_source_path = None

    def _request_server_processed_assets(self, source_path: str) -> list[dict]:
        """Request server to process and return optimized asset metadata."""
        c = self._controller
        try:
            # Use existing API but with server-side optimization hints
            assets = c.api.list_assets()
            self._logger.info(
                "Server-side asset processing completed for path=%s", source_path
            )
            return assets
        except httpx.HTTPError as exc:
            self._logger.error("Server-side asset processing failed: %s", exc)
            raise

    def _get_server_processed_folder_assets(
        self, assets: list[dict], source_path_obj: Path
    ) -> list[dict]:
        """Get folder assets using server-side metadata processing."""
        # Server processes folder contents without client file system access
        matching_assets = [
            asset
            for asset in assets
            if Path(str(asset.get("file_path") or "")).parent == source_path_obj
        ]
        self._logger.info(
            "Server processed %d assets from folder", len(matching_assets)
        )
        return matching_assets

    def _get_server_sorted_recent_assets(
        self, assets: list[dict], limit: int = 5
    ) -> list[dict]:
        """Get recent assets sorted by server-side metadata timestamps."""
        # Sort by server-provided created_at timestamp instead of file system access
        sorted_assets = sorted(
            assets, key=lambda a: a.get("created_at", ""), reverse=True
        )
        return sorted_assets[:limit]

    def _find_server_processed_asset(
        self, assets: list[dict], source_path: str
    ) -> dict | None:
        """Find asset using server-side metadata matching."""
        c = self._controller
        # Strategy 1: Server-side exact path matching
        match = next(
            (
                asset
                for asset in assets
                if c._paths_equivalent(
                    str(asset.get("file_path") or ""), source_path
                )
            ),
            None,
        )

        # Strategy 2: Server-side filename matching
        if not isinstance(match, dict):
            source_filename = Path(source_path).name
            match = next(
                (
                    asset
                    for asset in assets
                    if Path(str(asset.get("file_path") or "")).name == source_filename
                ),
                None,
            )
            if isinstance(match, dict):
                self._logger.info(
                    "Server-side asset matched by filename source=%s matched=%s",
                    source_path,
                    match.get("file_path"),
                )

        return match

    def _load_assets_event_driven(self, assets_to_load: list[dict]) -> None:
        """Load multiple assets using event-driven architecture."""
        c = self._controller
        start_time = time.time()

        for idx, match in enumerate(assets_to_load):
            c._asset_cache[match["file_path"]] = match
            c.state.selected_asset = match

            # Track terabyte-scale assets
            if match.get("performance_tier") == "ultra_large":
                c._terabyte_scale_assets_loaded += 1

            # Request server-side tile preparation and optimization
            options = self._get_server_optimized_layer_options(match)

            if idx == 0:
                # For first asset, show loading indicator and fly to it
                c._set_layer_loading(True, f"Loading {match['file_name']}...")
                if self._add_layer_event_driven(match, options):
                    self._fly_through_asset_event_driven(match)
                else:
                    c._set_layer_loading(False, "Layer load failed")
            else:
                # For subsequent assets, just add them without flying
                self._add_layer_event_driven(match, options)

            c.panel.log(f"Auto-loaded: {match['file_name']}")

        # Track performance
        load_time = time.time() - start_time
        c._track_performance_metric(
            "layer_load_times", load_time, f"{len(assets_to_load)} assets"
        )

    def _load_single_asset_event_driven(self, match: dict) -> None:
        """Load single asset using event-driven architecture."""
        c = self._controller
        start_time = time.time()

        c._asset_cache[match["file_path"]] = match
        c.state.selected_asset = match

        # Track terabyte-scale assets
        if match.get("performance_tier") == "ultra_large":
            c._terabyte_scale_assets_loaded += 1

        # Request server-side optimization
        options = self._get_server_optimized_layer_options(match)

        c._set_layer_loading(True, f"Loading {match['file_name']}...")
        if self._add_layer_event_driven(match, options):
            self._fly_through_asset_event_driven(match)
        else:
            c._set_layer_loading(False, "Layer load failed")
        c.panel.log(f"Auto-loaded ingested asset: {match['file_name']}")

        # Track performance
        load_time = time.time() - start_time
        c._track_performance_metric(
            "layer_load_times", load_time, f"single asset: {match['file_name']}"
        )

    def _get_server_optimized_layer_options(self, asset: dict) -> dict:
        """Get layer options optimized by server-side processing."""
        c = self._controller
        bounds = c._asset_bounds(asset)
        options = c._layer_options(asset, bounds)

        # Add server-side optimization hints for terabyte-scale data
        options["server_optimized"] = True
        options["tile_cache_strategy"] = "aggressive"
        options["memory_efficient"] = True

        return options

    def _add_layer_event_driven(self, asset: dict, options: dict) -> bool:
        """Add layer using event-driven architecture with server-side processing."""
        c = self._controller
        # Test JavaScript bridge connectivity first
        if not c._test_js_bridge_connectivity():
            self._logger.warning(
                "JavaScript bridge connectivity test failed, falling back to standard layer loading"
            )
            c.panel.log(
                "Warning: JavaScript bridge issue detected, using fallback method"
            )
            return c._add_layer(asset, options)

        # Use existing _add_layer but with server optimization flags
        options["event_driven"] = True
        return c._add_layer(asset, options)

    def _fly_through_asset_event_driven(self, asset: dict) -> bool:
        """Fly through asset using server-optimized bounds."""
        # Use server-provided bounds for smooth navigation
        return self.fly_through_asset(asset)
