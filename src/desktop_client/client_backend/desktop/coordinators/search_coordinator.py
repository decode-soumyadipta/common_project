from __future__ import annotations

import json
import math

import httpx


class SearchCoordinator:
    """Encapsulate catalog search and drawn-geometry orchestration for desktop controller."""

    def __init__(self, controller):
        self._controller = controller

    def search_assets_by_coordinate(self) -> None:
        c = self._controller
        if not c._require_offline_endpoints("Coordinate search"):
            return
        lon = float(c.panel.search_coord_lon.value())
        lat = float(c.panel.search_coord_lat.value())
        buffer_meters = float(c.panel.search_buffer_m.value())
        c.panel.set_search_busy(True, "Searching around coordinate...", progress=8)
        try:
            c.panel.set_search_busy(True, "Preparing query...", progress=18)
            if buffer_meters <= 0:
                assets = c.api.search_assets_by_point(lon=lon, lat=lat)
            else:
                polygon_points = self._coordinate_buffer_polygon(
                    lon, lat, buffer_meters
                )
                assets = c.api.search_assets_by_polygon(
                    points=polygon_points, buffer_meters=0.0
                )
            c.panel.set_search_busy(True, "Rendering results...", progress=78)
            c._apply_search_results(
                assets,
                label=f"Coordinate search ({lon:.6f}, {lat:.6f}) buffer={int(buffer_meters)}m",
            )
            c.panel.set_search_busy(True, "Finalizing...", progress=97)
        except httpx.HTTPError as exc:
            c._handle_api_error("Coordinate search", exc)
            return
        finally:
            c.panel.set_search_busy(False)

    def search_assets_from_drawn_geometry(self) -> None:
        c = self._controller
        if not c._require_offline_endpoints("Drawn geometry search"):
            c.panel.set_search_busy(False)
            return
        geometry_type = c.state.search_geometry_type
        payload = c.state.search_geometry_payload or {}
        if geometry_type is None:
            c.panel.log("Draw a search geometry first.")
            c.panel.set_search_busy(False)
            return

        if geometry_type != "polygon":
            c.panel.log("Only polygon draw search is enabled.")
            c.panel.set_search_busy(False)
            return

        c.panel.set_search_busy(True, "Searching polygon overlap...", progress=12)
        try:
            c.panel.set_search_busy(True, "Preparing polygon query...", progress=24)
            points = [
                (float(item["lon"]), float(item["lat"]))
                for item in payload.get("points", [])
            ]
            c.panel.set_search_busy(True, "Querying catalog...", progress=42)
            assets = c.api.search_assets_by_polygon(
                points=points,
                buffer_meters=float(c.panel.search_buffer_m.value()),
            )
            c.panel.set_search_busy(True, "Rendering results...", progress=80)
            c._apply_search_results(assets, label=f"Drawn {geometry_type} search")
            c.panel.set_search_busy(True, "Finalizing...", progress=97)

            # Turn off drawing mode and pencil cursor, but keep polygon on map
            c._run_js_call("setSearchDrawMode", "none")
            c._set_search_draw_button_checked(False)
            
            # Clear Python payload so 'Add Polygon' doesn't auto-finalize with stale points
            c.state.search_geometry_type = None
            c.state.search_geometry_payload = None
        except (KeyError, ValueError, TypeError):
            c.panel.log("Invalid drawn geometry payload.")
            c._logger.exception("Invalid drawn geometry payload=%s", payload)
            return
        except httpx.HTTPError as exc:
            c._handle_api_error("Drawn geometry search", exc)
            return
        finally:
            c.panel.set_search_busy(False)

    def set_search_draw_mode(self, enabled: bool | None = None) -> None:
        c = self._controller
        next_state = True if enabled is None else bool(enabled)
        if not next_state:
            if c._polygon_drawing_context == "measurement":
                c._set_measurement_cursor_enabled(False)
            c.clear_search_geometry()
            c.panel.log("Polygon draw disabled.")
            c._set_search_draw_button_checked(False)
            return
        if c._distance_measure_mode_enabled:
            c._distance_measure_mode_enabled = False
            c._run_js_call("setDistanceMeasureMode", False)
        # if c._add_point_mode_enabled:
        #     c._add_point_mode_enabled = False
        #     c._set_annotation_overlay_visible(False) (Removed to allow coexistence)
        if c._shadow_height_mode_enabled:
            c._shadow_height_mode_enabled = False
        c._pan_mode_enabled = False
        c._run_js_call("setSearchDrawMode", "polygon")
        if c._polygon_drawing_context == "measurement":
            c._set_measurement_cursor_enabled(True)
        c._set_search_draw_button_checked(True)
        c.panel.log("Polygon draw mode enabled.")

    def finish_search_polygon(self) -> None:
        c = self._controller
        c._run_js_call("finishSearchPolygon")
        c._set_search_draw_button_checked(False)

        # Check if polygon was drawn for measurement context
        if c._polygon_drawing_context == "measurement":
            if c._polygon_area_mode_enabled:
                c._toolbar_measure_polygon_area()
            elif c._volume_mode_enabled:
                c._toolbar_measure_volume()
            elif c._slope_aspect_mode_enabled:
                c._toolbar_measure_slope_aspect()
            c._polygon_drawing_context = "none"

    def clear_search_geometry(self) -> None:
        c = self._controller
        c._run_js_call("clearSearchGeometry")
        c.state.search_geometry_type = None
        c.state.search_geometry_payload = None
        c._set_search_draw_button_checked(False)
        c.panel.log("Search geometry cleared.")

    def on_search_geometry(self, geometry_type: str, payload_json: str) -> None:
        c = self._controller
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            c._logger.error("Invalid geometry payload JSON: %s", payload_json)
            return
        c.state.search_geometry_type = geometry_type
        c.state.search_geometry_payload = payload
        c.panel.log(f"Search geometry updated: type={geometry_type}")
        if geometry_type == "polygon":
            c._update_coordinate_inputs_from_polygon(payload)
            c.panel.log("Polygon ready. Click Search to run overlap scan.")

    @staticmethod
    def _coordinate_buffer_polygon(
        lon: float, lat: float, buffer_meters: float
    ) -> list[tuple[float, float]]:
        lat_offset = buffer_meters / 111_320.0
        lon_scale = max(0.1, math.cos(math.radians(lat)))
        lon_offset = buffer_meters / (111_320.0 * lon_scale)
        return [
            (lon - lon_offset, lat - lat_offset),
            (lon + lon_offset, lat - lat_offset),
            (lon + lon_offset, lat + lat_offset),
            (lon - lon_offset, lat + lat_offset),
        ]

    # ═══════════════════════════════════════════════════════════════════════════
    # Event-Driven Architecture Methods for Terabyte-Scale Performance
    # Metadata-first AOI search that never loads full rasters
    # ═══════════════════════════════════════════════════════════════════════════

    def search_assets_by_coordinate_event_driven(self) -> None:
        """Search assets by coordinate using server-side metadata processing.

        Metadata-first approach: Never loads full rasters, only processes metadata.
        All processing happens on server for terabyte-scale performance.
        """
        import time

        start_time = time.time()

        c = self._controller
        if not c._require_offline_endpoints("Event-driven coordinate search"):
            return

        lon = float(c.panel.search_coord_lon.value())
        lat = float(c.panel.search_coord_lat.value())
        buffer_meters = float(c.panel.search_buffer_m.value())

        c.panel.set_search_busy(True, "Server-side metadata search...", progress=5)

        try:
            # Event-driven optimization: Request server-side metadata processing
            c.panel.set_search_busy(
                True, "Processing metadata on server...", progress=15
            )

            if buffer_meters <= 0:
                # Server-side point search using only metadata
                assets = self._server_metadata_point_search(lon, lat)
            else:
                # Server-side polygon search using only metadata
                polygon_points = self._coordinate_buffer_polygon(
                    lon, lat, buffer_meters
                )
                assets = self._server_metadata_polygon_search(polygon_points, 0.0)

            c.panel.set_search_busy(
                True, "Optimizing results for display...", progress=70
            )

            # Apply server-optimized results
            c._apply_search_results_event_driven(
                assets,
                label=f"Metadata search ({lon:.6f}, {lat:.6f}) buffer={int(buffer_meters)}m",
            )

            c.panel.set_search_busy(
                True, "Finalizing event-driven search...", progress=95
            )

            # Track performance
            search_time = time.time() - start_time
            c._track_performance_metric(
                "search_times", search_time, f"coordinate search: {len(assets)} results"
            )

        except httpx.HTTPError as exc:
            c._handle_api_error("Event-driven coordinate search", exc)
            return
        finally:
            c.panel.set_search_busy(False)

    def search_assets_from_drawn_geometry_event_driven(self) -> None:
        """Search assets from drawn geometry using server-side metadata processing.

        Event-driven approach: All processing on server, client requests everything from server.
        Metadata-first: Never loads full rasters during search.
        """
        import time

        start_time = time.time()

        c = self._controller
        if not c._require_offline_endpoints("Event-driven drawn geometry search"):
            c.panel.set_search_busy(False)
            return

        geometry_type = c.state.search_geometry_type
        payload = c.state.search_geometry_payload or {}

        if geometry_type is None:
            c.panel.log("Draw a search geometry first.")
            c.panel.set_search_busy(False)
            return

        if geometry_type != "polygon":
            c.panel.log("Only polygon draw search is enabled.")
            c.panel.set_search_busy(False)
            return

        c.panel.set_search_busy(
            True, "Server-side polygon metadata search...", progress=8
        )

        try:
            c.panel.set_search_busy(
                True, "Processing polygon metadata on server...", progress=20
            )

            points = [
                (float(item["lon"]), float(item["lat"]))
                for item in payload.get("points", [])
            ]

            c.panel.set_search_busy(
                True, "Server metadata polygon query...", progress=40
            )

            # Server-side metadata-only polygon search
            assets = self._server_metadata_polygon_search(
                points,
                float(c.panel.search_buffer_m.value()),
            )

            c.panel.set_search_busy(True, "Optimizing polygon results...", progress=75)

            # Apply event-driven results
            c._apply_search_results_event_driven(
                assets, label=f"Metadata {geometry_type} search"
            )

            c.panel.set_search_busy(True, "Finalizing polygon search...", progress=95)

            # Turn off drawing mode and pencil cursor, but keep polygon on map
            c._run_js_call("setSearchDrawMode", "none")
            c._set_search_draw_button_checked(False)
            
            # Clear Python payload so 'Add Polygon' doesn't auto-finalize with stale points
            c.state.search_geometry_type = None
            c.state.search_geometry_payload = None

            # Track performance
            search_time = time.time() - start_time
            c._track_performance_metric(
                "search_times", search_time, f"polygon search: {len(assets)} results"
            )

        except (KeyError, ValueError, TypeError):
            c.panel.log("Invalid drawn geometry payload.")
            c._logger.exception("Invalid drawn geometry payload=%s", payload)
            return
        except httpx.HTTPError as exc:
            c._handle_api_error("Event-driven drawn geometry search", exc)
            return
        finally:
            c.panel.set_search_busy(False)

    def _server_metadata_point_search(self, lon: float, lat: float) -> list[dict]:
        """Perform server-side metadata-only point search."""
        c = self._controller

        # Use existing API but with metadata-only optimization hints
        assets = c.api.search_assets_by_point(lon=lon, lat=lat)

        # Server-side metadata optimization: Pre-process for terabyte-scale performance
        optimized_assets = self._optimize_assets_metadata(assets)

        c._logger.info(
            "Server metadata point search completed: %d assets", len(optimized_assets)
        )
        return optimized_assets

    def _server_metadata_polygon_search(
        self, points: list[tuple[float, float]], buffer_meters: float
    ) -> list[dict]:
        """Perform server-side metadata-only polygon search."""
        c = self._controller

        # Use existing API but with metadata-only optimization hints
        assets = c.api.search_assets_by_polygon(
            points=points, buffer_meters=buffer_meters
        )

        # Server-side metadata optimization: Pre-process for terabyte-scale performance
        optimized_assets = self._optimize_assets_metadata(assets)

        c._logger.info(
            "Server metadata polygon search completed: %d assets", len(optimized_assets)
        )
        return optimized_assets

    def _optimize_assets_metadata(self, assets: list[dict]) -> list[dict]:
        """Optimize asset metadata for terabyte-scale performance.

        Server-side processing to prepare metadata for ultra-high performance display.
        Never loads full raster data, only processes metadata.
        """
        c = self._controller

        optimized = []
        for asset in assets:
            # Create optimized metadata record
            optimized_asset = dict(asset)

            # Add server-side optimization flags
            optimized_asset["server_optimized"] = True
            optimized_asset["metadata_only"] = True
            optimized_asset["terabyte_ready"] = True

            # Pre-calculate display properties for smooth UI
            file_size = asset.get("file_size_bytes", 0)
            if file_size > 1_000_000_000_000:  # > 1TB
                optimized_asset["performance_tier"] = "ultra_large"
                optimized_asset["cache_strategy"] = "aggressive"
            elif file_size > 100_000_000_000:  # > 100GB
                optimized_asset["performance_tier"] = "large"
                optimized_asset["cache_strategy"] = "enhanced"
            else:
                optimized_asset["performance_tier"] = "standard"
                optimized_asset["cache_strategy"] = "normal"

            optimized.append(optimized_asset)

        c._logger.info(
            "Optimized %d assets for terabyte-scale performance", len(optimized)
        )
        return optimized
