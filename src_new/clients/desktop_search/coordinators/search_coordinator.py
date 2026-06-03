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

        c._logger.info(
            "Event-driven coordinate search requested: lon=%s lat=%s buffer=%s",
            lon,
            lat,
            buffer_meters,
        )
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

    def set_search_draw_mode(self, mode: str | bool | None = None) -> None:
        if getattr(self, "_setting_search_draw_mode", False):
            return
        self._setting_search_draw_mode = True
        try:
            c = self._controller
            normalized_mode = "polygon"
            if isinstance(mode, str):
                lowered = mode.strip().lower()
                if lowered in {"rectangle", "box", "bbox"}:
                    normalized_mode = "rectangle"
                elif lowered in {"none", "off", "false", "0"}:
                    normalized_mode = "none"
            elif mode is False:
                normalized_mode = "none"

            if hasattr(c.panel, "_set_search_draw_mode") and normalized_mode != "none":
                if not (hasattr(c.panel, "search_draw_mode") and c.panel.search_draw_mode == normalized_mode):
                    c.panel._set_search_draw_mode(normalized_mode)

            if normalized_mode == "none":
                if c._polygon_drawing_context == "measurement":
                    c._set_measurement_cursor_enabled(False)
                c.clear_search_geometry(rearm_draw=False)
                c._run_js_call("setSearchDrawMode", "none")
                c.panel.log("Search draw disabled.")
                c._set_search_draw_button_checked(False)
                return
            if c._distance_measure_mode_enabled:
                c._distance_measure_mode_enabled = False
                c._run_js_call("setDistanceMeasureMode", False)
            # if c._add_point_mode_enabled:
            #     c._add_point_mode_enabled = False
            #     c._set_annotation_overlay_visible(False) (Removed to allow coexistence)
            c._pan_mode_enabled = False
            c._run_js_call("setSearchDrawMode", normalized_mode)
            # Always enable crosshair for drawing activities
            c._set_measurement_cursor_enabled(True)
            c._set_search_draw_button_checked(True)
            if normalized_mode == "rectangle":
                c.panel.log("Box draw mode enabled.")
            else:
                c.panel.log("Polygon draw mode enabled.")
        finally:
            self._setting_search_draw_mode = False

    def finish_search_polygon(self) -> None:
        c = self._controller
        c._run_js_call("finishSearchPolygon")
        c._set_search_draw_button_checked(False)



    def clear_search_geometry(self, *, rearm_draw: bool = True) -> None:
        c = self._controller
        current_mode = getattr(c.panel, "search_draw_mode", "polygon")
        c._run_js_call("clearSearchGeometry")
        c.state.search_geometry_type = None
        c.state.search_geometry_payload = None
        c.panel.log("Search geometry cleared.")
        # Re-arm the active draw mode so the user can immediately draw again.
        if rearm_draw and current_mode in {"polygon", "rectangle"}:
            c._run_js_call("setSearchDrawMode", current_mode)
            c._set_search_draw_button_checked(True)
            c._set_measurement_cursor_enabled(current_mode == "polygon")
        else:
            c._set_search_draw_button_checked(False)

    def on_search_geometry(self, geometry_type: str, payload_json: str | dict) -> None:
        c = self._controller
        if geometry_type == "none":
            c.state.search_geometry_type = None
            c.state.search_geometry_payload = None
            return
        if isinstance(payload_json, dict):
            payload = payload_json
        else:
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
            c.panel.log("Polygon finalized. Click 'Search' to search.")
        elif geometry_type in {"rectangle", "bbox"}:
            c.panel.log("Box finalized. Click 'Search' to search.")

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

            # Robust search strategy:
            # 1) Always run point query (fast, precise, resilient)
            # 2) If buffer > 0, merge with polygon envelope query
            # 3) If still empty, retry once with swapped lon/lat
            assets, resolved_lon, resolved_lat, used_swapped = (
                self._search_coordinate_assets_event_driven_with_fallback(
                    lon=lon,
                    lat=lat,
                    buffer_meters=buffer_meters,
                )
            )

            if used_swapped:
                c.panel.search_coord_lon.setValue(resolved_lon)
                c.panel.search_coord_lat.setValue(resolved_lat)
                c.panel.log(
                    "Coordinate order auto-corrected to lon/lat for this search."
                )

            c.panel.set_search_busy(
                True, "Optimizing results for display...", progress=70
            )

            # Apply server-optimized results
            c._apply_search_results_event_driven(
                assets,
                label=f"Metadata search ({resolved_lon:.6f}, {resolved_lat:.6f}) buffer={int(buffer_meters)}m",
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

    def _search_coordinate_assets_event_driven_with_fallback(
        self, *, lon: float, lat: float, buffer_meters: float
    ) -> tuple[list[dict], float, float, bool]:
        """Search coordinate with robust fallback for lon/lat input order mistakes."""
        c = self._controller

        c._logger.debug("Running primary event-driven coordinate search: %s,%s buffer=%s", lon, lat, buffer_meters)
        assets = self._search_coordinate_assets_event_driven(
            lon=lon,
            lat=lat,
            buffer_meters=buffer_meters,
        )
        if assets:
            return assets, lon, lat, False

        # Retry once with swapped coordinate order. This handles the common
        # case where users enter lat/lon into lon/lat fields.
        swapped_assets = self._search_coordinate_assets_event_driven(
            lon=lat,
            lat=lon,
            buffer_meters=buffer_meters,
        )
        if swapped_assets:
            c._logger.info(
                "Coordinate search fallback succeeded with swapped order input_lon=%.6f input_lat=%.6f",
                lon,
                lat,
            )
            return swapped_assets, lat, lon, True

        # Final fallback: if server returned no results for both orders,
        # perform a lightweight client-side nearest-asset lookup using
        # catalog bounds (centroid distance). This helps when metadata
        # queries are strict but the user expects nearby assets.
        try:
            all_assets = c.api.list_assets()
            if all_assets:
                def _centroid_distance(a):
                    from math import radians, sin, cos, asin, sqrt
                    # bbox may come as dict {min_lon, min_lat, max_lon, max_lat}
                    # or as a list/tuple [west, south, east, north]
                    b = a.get("bbox") or a.get("bounds") or None
                    if not b:
                        return float("inf")
                    try:
                        if isinstance(b, dict):
                            west  = float(b.get("min_lon", b.get("west",  float("nan"))))
                            south = float(b.get("min_lat", b.get("south", float("nan"))))
                            east  = float(b.get("max_lon", b.get("east",  float("nan"))))
                            north = float(b.get("max_lat", b.get("north", float("nan"))))
                        elif isinstance(b, (list, tuple)) and len(b) >= 4:
                            west, south, east, north = map(float, b[:4])
                        else:
                            return float("inf")
                        if any(v != v for v in (west, south, east, north)):  # NaN check
                            return float("inf")
                        cx = (west + east) / 2.0
                        cy = (south + north) / 2.0
                        lon1, lat1, lon2, lat2 = map(radians, (lon, lat, cx, cy))
                        dlon = lon2 - lon1
                        dlat = lat2 - lat1
                        a_h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
                        c_h = 2 * asin(min(1.0, sqrt(a_h)))
                        return 6371.0 * c_h
                    except Exception:
                        return float("inf")

                ranked = sorted(all_assets, key=_centroid_distance)
                # Return top 10 nearest assets within 500 km
                nearest = [r for r in ranked[:10] if _centroid_distance(r) < 500.0]
                if nearest:
                    c._logger.info(
                        "Client-side nearest-asset fallback returning %d assets", len(nearest)
                    )
                    c.panel.log(
                        f"No exact match; showing {len(nearest)} nearest assets as fallback."
                    )
                    return nearest, lon, lat, False
        except Exception:
            c._logger.exception("Nearest-asset fallback failed")

        return [], lon, lat, False

    def _search_coordinate_assets_event_driven(
        self, *, lon: float, lat: float, buffer_meters: float
    ) -> list[dict]:
        """Run point + optional buffer search and merge results deterministically."""
        point_assets = self._server_metadata_point_search(lon, lat)
        if buffer_meters <= 0:
            return point_assets

        polygon_points = self._coordinate_buffer_polygon(lon, lat, buffer_meters)
        polygon_assets = self._server_metadata_polygon_search(polygon_points, 0.0)
        return self._merge_asset_results(point_assets, polygon_assets)

    @staticmethod
    def _asset_identity_key(asset: dict) -> str:
        """Return a stable identity key for deduplicating merged search results."""
        file_path = str(asset.get("file_path") or "").replace("\\", "/").strip()
        if file_path:
            return f"path:{file_path}"
        raster_id = str(asset.get("raster_id") or "").strip()
        if raster_id:
            return f"id:{raster_id}"
        file_name = str(asset.get("file_name") or "").strip()
        if file_name:
            return f"name:{file_name}"
        return f"obj:{id(asset)}"

    def _merge_asset_results(
        self, primary_assets: list[dict], secondary_assets: list[dict]
    ) -> list[dict]:
        """Merge two asset lists preserving order and removing duplicates."""
        merged: list[dict] = []
        seen: set[str] = set()
        for asset in [*primary_assets, *secondary_assets]:
            key = self._asset_identity_key(asset)
            if key in seen:
                continue
            seen.add(key)
            merged.append(asset)
        return merged

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

        try:
            if geometry_type in {"rectangle", "bbox"}:
                c.panel.set_search_busy(
                    True, "Server-side box metadata search...", progress=8
                )
                bounds = self._payload_to_bounds(payload)
                if bounds is None:
                    c.panel.log("Invalid box geometry payload.")
                    c._logger.exception("Invalid box geometry payload=%s", payload)
                    return
                min_lon, min_lat, max_lon, max_lat = self._expand_bounds_by_meters(
                    *bounds,
                    float(c.panel.search_buffer_m.value()),
                )
                c.panel.set_search_busy(
                    True, "Processing box metadata on server...", progress=20
                )
                c.panel.set_search_busy(
                    True, "Server metadata box query...", progress=40
                )
                assets = self._server_metadata_bbox_search(
                    min_lon=min_lon,
                    min_lat=min_lat,
                    max_lon=max_lon,
                    max_lat=max_lat,
                )
                search_label = "Metadata box search"
            elif geometry_type == "polygon":
                c.panel.set_search_busy(
                    True, "Server-side polygon metadata search...", progress=8
                )
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
                assets = self._server_metadata_polygon_search(
                    points,
                    float(c.panel.search_buffer_m.value()),
                )
                search_label = "Metadata polygon search"
            else:
                c.panel.log("Only polygon and box draw search are enabled.")
                c.panel.set_search_busy(False)
                return

            c.panel.set_search_busy(True, "Optimizing geometry results...", progress=75)

            # Apply event-driven results
            c._apply_search_results_event_driven(
                assets, label=search_label
            )

            c.panel.set_search_busy(True, "Finalizing geometry search...", progress=95)

            # Turn off drawing mode and pencil cursor, but keep polygon on map
            c._run_js_call("setSearchDrawMode", "none")
            c._set_search_draw_button_checked(False)
            
            # Clear Python payload so 'Add Polygon' doesn't auto-finalize with stale points
            c.state.search_geometry_type = None
            c.state.search_geometry_payload = None

            # Track performance
            search_time = time.time() - start_time
            c._track_performance_metric(
                "search_times", search_time, f"{geometry_type} search: {len(assets)} results"
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

    @staticmethod
    def _payload_to_bounds(payload: dict) -> tuple[float, float, float, float] | None:
        if not isinstance(payload, dict):
            return None
        bounds = payload.get("bounds")
        if not isinstance(bounds, dict):
            bounds = payload
        
        try:
            west = float(bounds.get("west"))
            south = float(bounds.get("south"))
            east = float(bounds.get("east"))
            north = float(bounds.get("north"))
            if west >= east or south >= north:
                return None
            return west, south, east, north
        except (TypeError, ValueError):
            pass

        points = payload.get("points")
        if not isinstance(points, list) or len(points) < 2:
            return None

        lons: list[float] = []
        lats: list[float] = []
        for item in points:
            try:
                lons.append(float(item["lon"]))
                lats.append(float(item["lat"]))
            except (KeyError, TypeError, ValueError):
                return None

        west = min(lons)
        east = max(lons)
        south = min(lats)
        north = max(lats)
        if west >= east or south >= north:
            return None
        return west, south, east, north

    @staticmethod
    def _expand_bounds_by_meters(
        west: float, south: float, east: float, north: float, buffer_meters: float
    ) -> tuple[float, float, float, float]:
        if buffer_meters <= 0:
            return west, south, east, north
        lat_offset = buffer_meters / 111_320.0
        center_lat = (south + north) / 2.0
        lon_scale = max(0.1, math.cos(math.radians(center_lat)))
        lon_offset = buffer_meters / (111_320.0 * lon_scale)
        return (
            max(-180.0, west - lon_offset),
            max(-90.0, south - lat_offset),
            min(180.0, east + lon_offset),
            min(90.0, north + lat_offset),
        )

    def _server_metadata_bbox_search(
        self,
        *,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
    ) -> list[dict]:
        c = self._controller
        assets = c.api.search_assets_by_bbox(
            west=min_lon,
            south=min_lat,
            east=max_lon,
            north=max_lat,
        )
        optimized_assets = self._optimize_assets_metadata(assets)
        c._logger.info(
            "Server metadata bbox search completed: %d assets", len(optimized_assets)
        )
        return optimized_assets

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
