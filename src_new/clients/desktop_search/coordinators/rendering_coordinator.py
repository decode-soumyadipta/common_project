"""Rendering coordinator for layer rendering and tile URL management."""

from __future__ import annotations

import base64
import logging
import platform
import re
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote, unquote

import httpx

if TYPE_CHECKING:
    from src_new.clients.desktop_search.controller import DesktopController


class RenderingCoordinator:
    """Handles layer rendering, tile URL optimization, and server-side rendering."""

    def __init__(self, controller: DesktopController):
        self._controller = controller
        self._logger = logging.getLogger("client_desktop.rendering_coordinator")

    def raster_render_query(self, asset: dict) -> dict[str, object]:
        """Build raster render query with stretch modes and color maps."""
        c = self._controller
        query: dict[str, object] = {}
        file_name = asset.get("file_name", "")
        is_dem = (
            str(asset.get("kind", "")).lower() in ("dem", "elevation")
            or any(
                marker in str(file_name).lower()
                for marker in ("dem", "dtm", "elevation")
            )
        )

        self._logger.debug(f"Raster render query for {file_name}: is_dem={is_dem}")

        info = {}
        try:
            info = c.api.get_cog_info(asset["file_path"])
            self._logger.debug(f"COG info for {file_name}: {info}")
        except httpx.HTTPError as exc:
            self._logger.warning(
                "COG info unavailable for %s: %s", asset.get("file_name"), exc
            )

        band_count = int(info.get("count", 1) or 1)
        nodata_value = info.get("nodata_value", info.get("nodata"))

        self._logger.debug(
            f"Band count for {file_name}: {band_count}, nodata: {nodata_value}"
        )

        try:
            if nodata_value is not None:
                query["nodata"] = float(nodata_value)
        except (TypeError, ValueError):
            pass

        if band_count >= 3 and not is_dem:
            self._logger.info(
                f"Multi-band imagery detected for {file_name}: {band_count} bands, adding bidx=[1,2,3]"
            )
            query["bidx"] = [1, 2, 3]
            # Use bilinear resampling for high fidelity rendering instead of nearest neighbor
            query["resampling"] = "bilinear"
            # Set nodata=0 to prevent GDAL "INIT_DEST NO_DATA without defined nodata" error on Windows when the file has no nodata value defined.
            if "nodata" not in query:
                query["nodata"] = 0
        else:
            self._logger.debug(
                f"Single-band or DEM for {file_name}: band_count={band_count}, is_dem={is_dem}"
            )

        stats = {}
        try:
            stats = c.api.get_cog_statistics(asset["file_path"])
        except httpx.HTTPError as exc:
            self._logger.warning(
                "Statistics unavailable for %s: %s", asset.get("file_name"), exc
            )

        stretch_mode = "linear"
        if is_dem and hasattr(c.panel, "dem_stretch_mode_combo"):
            stretch_mode = str(
                c.panel.dem_stretch_mode_combo.currentData() or "linear"
            )
        elif hasattr(c.panel, "stretch_mode_combo"):
            stretch_mode = str(c.panel.stretch_mode_combo.currentData() or "linear")
        use_percentiles = stretch_mode not in {"minmax", "stddev"}

        def _stat_range(stat: dict) -> tuple[float | None, float | None]:
            if not isinstance(stat, dict):
                return None, None
            if use_percentiles:
                low = stat.get("percentile_2", stat.get("min"))
                high = stat.get("percentile_98", stat.get("max"))
            else:
                low = stat.get("min", stat.get("percentile_2"))
                high = stat.get("max", stat.get("percentile_98"))
            return low, high

        if is_dem:
            color_mode = str(c.panel.dem_color_mode_combo.currentData() or "gray")
            if color_mode == "slope":
                query["algorithm"] = "slope"
                query["colormap_name"] = "viridis"
                query["rescale"] = "0,90"
                self._logger.debug(f"DEM slope mode for {file_name}: {query}")
                return query

            query["colormap_name"] = color_mode

            # Provide default elevation rescale if TiTiler stats fail, preventing blank maps.
            low, high = -100.0, 4000.0
            if isinstance(stats, dict) and stats:
                first_band = (
                    stats.get("b1")
                    if isinstance(stats.get("b1"), dict)
                    else next(iter(stats.values()))
                )
                if isinstance(first_band, dict):
                    if stretch_mode == "stddev":
                        mean = first_band.get("mean")
                        std = first_band.get("std")
                        if std is None:
                            std = first_band.get("stdev")
                        if std is None:
                            std = first_band.get("stddev")
                        if mean is not None and std is not None:
                            low = float(mean) - (2.0 * float(std))
                            high = float(mean) + (2.0 * float(std))
                    else:
                        b_low, b_high = _stat_range(first_band)
                        if (
                            b_low is not None
                            and b_high is not None
                            and float(b_high) > float(b_low)
                        ):
                            low, high = float(b_low), float(b_high)

            query["rescale"] = f"{low},{high}"
            self._logger.debug(f"Final DEM raster query for {file_name}: {query}")
            return query

        if not isinstance(stats, dict) or not stats:
            self._logger.debug(
                f"No stats available for {file_name}, final query: {query}"
            )
            return query

        if band_count >= 3 and not is_dem:
            # FIX: Apply QGIS-style per-band Cumulative Count Cut (2% - 98%) This fixes both the pitch-black 16-bit rendering and the bluish tint. Passing a list of rescales allows TiTiler to stretch each band independently.
            if stretch_mode == "linear_shared":
                lows = []
                highs = []
                for i in range(1, min(3, band_count) + 1):
                    stat = stats.get(f"b{i}")
                    if not isinstance(stat, dict):
                        lows = []
                        highs = []
                        break
                    low, high = _stat_range(stat)
                    if low is None or high is None or float(low) >= float(high):
                        lows = []
                        highs = []
                        break
                    lows.append(float(low))
                    highs.append(float(high))
                if lows and highs:
                    query["rescale"] = f"{min(lows)},{max(highs)}"
                    self._logger.debug(f"Applied shared RGB stretch: {query}")
                    return query
            rescales = []
            valid = True
            for i in range(1, min(3, band_count) + 1):
                stat = stats.get(f"b{i}")
                if not isinstance(stat, dict):
                    valid = False
                    break
                low, high = _stat_range(stat)
                if low is None or high is None or float(low) >= float(high):
                    valid = False
                    break
                rescales.append(f"{float(low)},{float(high)}")

            if valid and len(rescales) == 3:
                query["rescale"] = rescales
                self._logger.debug(f"Applied per-band true color correction: {query}")
            else:
                self._logger.debug(
                    "Skipped true color correction (missing stats), rendering raw."
                )
            return query

        first_band = (
            stats.get("b1")
            if isinstance(stats.get("b1"), dict)
            else next(iter(stats.values()))
        )
        if not isinstance(first_band, dict):
            self._logger.debug(
                f"No valid first band stats for {asset.get('file_name', '')}, final query: {query}"
            )
            return query

        low, high = _stat_range(first_band)
        if low is None or high is None or float(high) <= float(low):
            self._logger.debug(
                f"Invalid rescale values for {asset.get('file_name', '')}, final query: {query}"
            )
            return query

        query["rescale"] = f"{float(low)},{float(high)}"

        self._logger.debug(
            f"Final raster query for {asset.get('file_name', '')}: {query}"
        )
        return query

    def _is_point_cloud_asset(self, asset: dict) -> bool:
        """Return True when the asset is a LAS/LAZ point cloud."""
        kind = str(asset.get("kind", "")).lower()
        ext = Path(str(asset.get("file_path", "") or asset.get("file_name", ""))).suffix.lower()
        return kind == "point_cloud" or ext in (".las", ".laz")

    def build_pointcloud_tileset_url(self, asset: dict) -> str:
        """Build the 3D Tiles tileset.json URL for a point-cloud asset.

        Uses the /pointcloud/tileset/{b64}/tileset.json endpoint that the
        tile service exposes.  The file path is base64-encoded so it is safe
        to embed in a URL segment.
        """
        c = self._controller
        file_path = str(asset.get("file_path", ""))
        b64 = base64.urlsafe_b64encode(file_path.encode("utf-8")).rstrip(b"=").decode("ascii")
        base = str(c.api.tile_service_base_url).rstrip("/")
        url = f"{base}/pointcloud/tileset/{b64}/tileset.json"
        self._logger.info("Built 3D Tiles URL for %s: %s", asset.get("file_name"), url)
        return url

    def layer_options(self, asset: dict, bounds: dict[str, float] | None) -> dict:
        """Build layer options including bounds, zoom levels, and render query."""
        # Point clouds bypass TiTiler entirely — return options with no tilejson query
        if self._is_point_cloud_asset(asset):
            options: dict = {"bounds": bounds, "is_dem": False, "is_point_cloud": True}
            self._logger.info(
                "Point cloud layer options for %s (skipping TiTiler tilejson)",
                asset.get("file_name"),
            )
            return options

        return self._layer_options_raster(asset, bounds)

    def _layer_options_raster(self, asset: dict, bounds: dict[str, float] | None) -> dict:
        """Build raster layer options (TiTiler path)."""
        c = self._controller
        options: dict = {"bounds": bounds, "is_dem": c._is_dem_asset(asset)}
        try:
            tilejson = c.api.get_tilejson(asset["file_path"])
        except httpx.HTTPError as exc:
            self._logger.warning(
                "TileJSON unavailable for %s: %s", asset["file_name"], exc
            )
            return options

        minzoom = tilejson.get("minzoom")
        maxzoom = tilejson.get("maxzoom")
        if isinstance(minzoom, int):
            options["minzoom"] = minzoom
        if isinstance(maxzoom, int):
            options["maxzoom"] = maxzoom

        # TileJSON bounds: [west, south, east, north] in EPSG:4326
        b = tilejson.get("bounds")
        if isinstance(b, list) and len(b) == 4:
            w, s, e, n = b
            if c._is_valid_lon_lat(w, s) and c._is_valid_lon_lat(e, n):
                tilejson_bounds = {
                    "west": float(w),
                    "south": float(s),
                    "east": float(e),
                    "north": float(n),
                }
                if (
                    c._is_near_global_bounds(tilejson_bounds)
                    and bounds
                    and not c._is_near_global_bounds(bounds)
                ):
                    self._logger.warning(
                        "Ignoring near-global TileJSON bounds for %s and keeping catalog bounds.",
                        asset.get("file_name"),
                    )
                else:
                    options["bounds"] = tilejson_bounds

        raster_query = c._raster_render_query(asset)
        if raster_query:
            options["query"] = raster_query
        self._logger.info("Layer options for %s: %s", asset["file_name"], options)
        return options

    def add_layer(self, asset: dict, options: dict) -> bool:
        """Add layer with event-driven architecture and server-side optimization."""
        c = self._controller

        # ---- Point-cloud fast path: skip TiTiler entirely ----
        if self._is_point_cloud_asset(asset) or options.get("is_point_cloud"):
            return self.add_point_cloud_layer(asset, options)

        tile_url = str(asset.get("tile_url") or "")

        # Event-driven optimization: Let server handle URL normalization
        if options.get("event_driven", False):
            tile_url = self.get_server_optimized_tile_url(asset, tile_url)
        else:
            # Legacy path normalization for non-event-driven calls
            tile_url = self.normalize_tile_url_legacy(tile_url)

        asset["tile_url"] = tile_url

        if not c._is_offline_safe_url(tile_url):
            c.panel.log(
                f"Blocked non-offline tile URL for {asset.get('file_name', 'asset')}"
            )
            self._logger.error("Blocked non-offline tile URL: %s", tile_url)
            return False

        is_dem = bool(options.get("is_dem"))
        from_search_results = bool(str(options.get("layer_key") or "").strip())

        # Event-driven performance optimizations
        if options.get("server_optimized", False):
            self.apply_server_performance_hints(options)

        if is_dem:
            return self.add_dem_layer_event_driven(asset, options, from_search_results)
        return self.add_imagery_layer_event_driven(
            asset, options, from_search_results
        )

    def add_point_cloud_layer(self, asset: dict, options: dict) -> bool:
        """Render a LAS/LAZ point cloud on the Cesium globe as a 3D tileset layer."""
        c = self._controller
        file_path = asset.get("file_path")
        if not file_path:
            c.panel.log("Point cloud file path is missing.")
            return False

        file_name = asset.get("file_name", Path(file_path).name)
        self._logger.info("Adding Cesium point cloud layer name=%s file_path=%s", file_name, file_path)

        # Ensure we are on the Cesium map
        window = c.panel.window()
        if hasattr(window, "set_canvas_index"):
            window.set_canvas_index(0)

        # Build tileset URL using the b64 tile service endpoint
        tileset_url = self.build_pointcloud_tileset_url(asset)

        # Call Javascript to load the point cloud as a 3D Tileset in Cesium
        js_options = {
            "bounds": options.get("bounds"),
            "layer_key": options.get("layer_key") or file_path.replace("\\", "/"),
            "replace_existing": options.get("replace_existing") is not False
        }
        c._run_js_call("addPointCloudLayer", file_name, tileset_url, js_options)

        c.panel.log(f"Added point cloud layer: {file_name}")
        return True

    def update_canvas_view_stack(self) -> None:
        """Switch canvas stack index based on whether any point cloud layers are active/visible."""
        # Point clouds are now rendered inside Cesium (Index 0) by default to preserve geographic context,
        # scale bar, measurements, and annotations.
        # This function is now a no-op to prevent auto-switching stack index.
        pass

    def get_server_optimized_tile_url(self, asset: dict, tile_url: str) -> str:
        """Adjust the tile URL for server-side delivery if needed."""
        # Find the best version of the file (prioritize Web Mercator projected files)
        original_file_path = asset.get("file_path")
        if original_file_path:
            best_file_path = self.find_best_file_version(original_file_path)
            if best_file_path != original_file_path:
                self._logger.info(
                    f"Optimizing tile URL for {asset.get('file_name')}: using {Path(best_file_path).name}"
                )
                # Re-build the XYZ URL for the optimized file
                if "/cog/tiles/" in tile_url:
                    base_url = tile_url.split("?url=")[0]
                    tile_url = f"{base_url}?url={quote(best_file_path)}"

        # Server handles all URL optimization and caching strategies
        optimized_url = self.normalize_tile_url_legacy(tile_url)

        # Add server-side optimization parameters for large datasets
        if "?" in optimized_url:
            optimized_url += "&cache_strategy=aggressive&memory_efficient=true"
        else:
            optimized_url += "?cache_strategy=aggressive&memory_efficient=true"

        self._logger.info("Server-optimized tile URL for %s", asset.get("file_name"))
        return optimized_url

    def find_best_file_version(self, file_path: str) -> str:
        """Find the best version of a file, prioritizing Web Mercator projected and COG versions."""
        original_path = Path(file_path)
        # Even if the original file is missing (e.g. it was replaced by a COG version during ingestion), we should still look for candidates based on its name.
        if not original_path.exists():
            self._logger.debug(
                f"Original file not found, searching for versions: {file_path}"
            )

        # Priority order: _3857.cog.tif > _3857.tif > .cog.tif > original
        candidates = []

        # Check for Web Mercator + COG version
        web_mercator_cog = original_path.parent / f"{original_path.stem}_3857.cog.tif"
        if web_mercator_cog.exists():
            candidates.append((web_mercator_cog, 4))  # Highest priority
            self._logger.debug(f"Found Web Mercator COG: {web_mercator_cog}")

        # Check for Web Mercator version
        web_mercator = original_path.parent / f"{original_path.stem}_3857.tif"
        if web_mercator.exists():
            candidates.append((web_mercator, 3))
            self._logger.debug(f"Found Web Mercator: {web_mercator}")

        # Check for COG version of original
        cog_version = original_path.parent / f"{original_path.stem}.cog.tif"
        if cog_version.exists():
            candidates.append((cog_version, 2))
            self._logger.debug(f"Found COG: {cog_version}")

        # Original file
        candidates.append((original_path, 1))
        self._logger.debug(f"Original file: {original_path}")

        # Sort by priority (highest first) and return the best option
        candidates.sort(key=lambda x: x[1], reverse=True)
        best_file = str(candidates[0][0])

        if best_file != file_path:
            self._logger.info(
                f"Using optimized file version: {Path(best_file).name} instead of {original_path.name}"
            )
        else:
            self._logger.debug(f"Using original file: {original_path.name}")

        return best_file

    def normalize_tile_url_legacy(self, tile_url: str) -> str:
        """Legacy tile URL normalization for backward compatibility."""
        if platform.system() == "Windows":
            # Handle URL-encoded Windows paths with spaces and special characters
            if "url=" in tile_url:
                # Split the URL to get the file path part
                base_part, url_part = tile_url.split("url=", 1)

                # First decode any URL-encoded characters (like %20 for spaces, %3A for :, %2F for /)
                decoded_url = unquote(url_part)
                self._logger.debug(f"Windows URL decode: {url_part} -> {decoded_url}")

                # Strip any file:/// or file:// or file: prefix so GDAL sees raw C:/...
                if decoded_url.startswith("file:///"):
                    decoded_url = decoded_url[8:]
                elif decoded_url.startswith("file://"):
                    decoded_url = decoded_url[7:]
                elif decoded_url.startswith("file:"):
                    decoded_url = decoded_url[5:]

                # Ensure Windows drive letter format (C:/...)
                if re.match(r"^[a-zA-Z]:", decoded_url):
                    # Already in correct format
                    pass
                elif (
                    decoded_url.startswith("/")
                    and len(decoded_url) > 3
                    and decoded_url[2] == ":"
                ):
                    # Remove leading slash from /C:/... format
                    decoded_url = decoded_url[1:]

                # Reconstruct the tile URL with the properly decoded path
                tile_url = base_part + "url=" + decoded_url
                self._logger.debug(f"Windows final URL: {tile_url}")

            # Also handle already partially processed URLs with encoded characters
            tile_url = re.sub(r"url=file:/{0,3}([a-zA-Z]:)", r"url=\1", tile_url)
            tile_url = re.sub(
                r"url=file%3A(?:%2F){1,3}([a-zA-Z](?:%3A|:))",
                lambda m: "url=" + m.group(1).replace("%3A", ":"),
                tile_url,
            )
        else:
            # macOS / Linux: strip file:/// so GDAL sees a bare /abs/path.
            if "url=file:///" in tile_url:
                tile_url = tile_url.replace("url=file:///", "url=/")
            elif "url=file://" in tile_url:
                tile_url = tile_url.replace("url=file://", "url=")
            if "url=file%3A%2F%2F%2F" in tile_url:
                tile_url = tile_url.replace("url=file%3A%2F%2F%2F", "url=%2F")
            elif "url=file%3A%2F%2F" in tile_url:
                tile_url = tile_url.replace("url=file%3A%2F%2F", "url=")

        return tile_url

    def apply_server_performance_hints(self, options: dict) -> None:
        """Apply server-side performance hints for terabyte-scale data."""
        # Configure aggressive caching for large datasets
        options["tile_cache_size"] = "large"
        options["prefetch_strategy"] = "aggressive"
        options["memory_management"] = "optimized"

        self._logger.info("Applied server performance hints for terabyte-scale data")

    def add_dem_layer_event_driven(
        self, asset: dict, options: dict, from_search_results: bool
    ) -> bool:
        """Add DEM layer using event-driven architecture."""
        c = self._controller
        if bool(options.get("replace_existing", True)) and not from_search_results:
            c._explicit_imagery_layer_visible = False
        if not from_search_results:
            c._explicit_dem_layer_visible = True

        c.state.active_layer_is_dem = True
        layer_key = str(options.get("layer_key") or "")
        c._active_dem_search_layer_key = layer_key or None

        # Event-driven DEM loading with server optimization
        c._run_js_call(
            "addDemLayerEventDriven", asset["file_name"], asset["tile_url"], options
        )

        c.panel.rgb_view_mode_combo.setCurrentIndex(0)
        c.panel.rgb_view_mode_combo.setEnabled(True)
        c.panel.apply_rgb_view_mode_btn.setEnabled(True)
        c._apply_display_control_mode()
        self._logger.info(
            "Event-driven DEM terrain layer requested name=%s", asset["file_name"]
        )
        return True

    def add_imagery_layer_event_driven(
        self, asset: dict, options: dict, from_search_results: bool
    ) -> bool:
        """Add imagery layer using event-driven architecture."""
        c = self._controller
        replace_existing = bool(options.get("replace_existing", True))
        apply_scene_mode = bool(options.get("apply_scene_mode", True))

        if replace_existing:
            if not from_search_results:
                c._explicit_dem_layer_visible = False
            c.state.active_layer_is_dem = False
            c._active_dem_search_layer_key = None
            c.panel.rgb_view_mode_combo.setEnabled(True)
            c.panel.apply_rgb_view_mode_btn.setEnabled(True)
            c._run_js_call("setSceneModeControlEnabled", True)
            c._apply_display_control_mode()

        # CRITICAL FIX: Do NOT force scene mode from Python backend JavaScript will automatically switch to 2D for imagery, 3D for DEM Forcing mode here creates conflicts and unnecessary morphing

        self._logger.info(
            "Event-driven layer render request name=%s kind=%s is_dem=%s replace_existing=%s apply_scene_mode=%s",
            asset.get("file_name"),
            asset.get("kind"),
            False,
            replace_existing,
            apply_scene_mode,
        )

        # Removed: Python-side setSceneMode call that conflicts with JavaScript auto-switching JavaScript addTileLayer() will automatically call setSceneModeInternal("2d") JavaScript addDemLayer() will automatically call setSceneModeInternal("3d")

        # Event-driven imagery loading with server optimization
        c._run_js_call(
            "addTileLayerEventDriven",
            asset["file_name"],
            asset["tile_url"],
            asset["kind"],
            options,
        )

        if not from_search_results:
            c._explicit_imagery_layer_visible = True
        c._apply_display_control_mode()
        return True
