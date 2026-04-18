from __future__ import annotations

import ipaddress
import json
import logging
from pathlib import Path
from urllib.parse import urlparse

import httpx
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QFileDialog
from PySide6.QtWebEngineWidgets import QWebEngineView

from offline_gis_app.desktop.api_client import DesktopApiClient
from offline_gis_app.desktop.api_server_manager import ApiServerManager
from offline_gis_app.desktop.app_mode import DesktopAppMode
from offline_gis_app.desktop.bridge import WebBridge
from offline_gis_app.desktop.control_panel import ControlPanel
from offline_gis_app.desktop.state import DesktopState
from offline_gis_app.desktop.titiler_manager import TiTilerManager
from offline_gis_app.services.metadata_extractor import MetadataExtractorError, extract_metadata
from offline_gis_app.services.tile_url_builder import build_xyz_url


class DesktopController:
    """Coordinates desktop UI actions, API calls, and Cesium bridge commands."""

    def __init__(
        self,
        panel: ControlPanel,
        web_view: QWebEngineView,
        bridge: WebBridge,
        api_client: DesktopApiClient | None = None,
        titiler_manager: TiTilerManager | None = None,
        app_mode: DesktopAppMode = DesktopAppMode.UNIFIED,
        api_server_manager: ApiServerManager | None = None,
    ):
        self.panel = panel
        self.web_view = web_view
        self.bridge = bridge
        self.app_mode = app_mode
        self.api = api_client or DesktopApiClient()
        self.panel.api_client = self.api  # Set API client on panel for asset listing
        self.api_server = api_server_manager or ApiServerManager(base_url=self.api.base_url)
        self.titiler = titiler_manager or TiTilerManager()
        self.state = DesktopState()
        self._logger = logging.getLogger("desktop.controller")
        self._asset_cache: dict[str, dict] = {}
        self._offline_endpoints_valid = True
        self._layer_loading_active = False
        self._ingest_poll_timer = QTimer(panel)
        self._ingest_poll_timer.setInterval(1000)
        self._ingest_poll_timer.timeout.connect(self._poll_active_ingest_job)
        self._last_ingest_step: str | None = None
        self._last_ingest_status: str | None = None
        self._logger.info("Controller initialized mode=%s", self.app_mode.value)
        self._connect_signals()
        self._prepare_api_runtime()
        self.refresh_assets()
        
        # Refresh uploaded assets list on server mode
        if self.app_mode == DesktopAppMode.SERVER:
            self.panel.refresh_uploaded_assets()

    def _prepare_api_runtime(self) -> None:
        self._offline_endpoints_valid = self._validate_offline_endpoints()
        if not self._offline_endpoints_valid:
            return

        if self.app_mode in {DesktopAppMode.SERVER, DesktopAppMode.UNIFIED}:
            if self.api_server.ensure_running():
                self.panel.log(f"API ready: {self.api.base_url}")
            else:
                self.panel.log(
                    f"API not reachable at {self.api.base_url}. Start API manually: python -m offline_gis_app.cli api"
                )
            return
        if not self.api.api_ready():
            self.panel.log(
                f"API not reachable at {self.api.base_url}. Start server desktop or API, then click Refresh Assets."
            )

    def _handle_api_error(self, action: str, exc: httpx.HTTPError) -> None:
        if isinstance(exc, httpx.ConnectError):
            self.panel.log(
                f"API unavailable at {self.api.base_url}. Start API/server desktop, then retry '{action}'."
            )
            self._logger.warning("%s failed: %s", action, exc)
            return
        if isinstance(exc, httpx.HTTPStatusError):
            status_code = exc.response.status_code if exc.response is not None else "unknown"
            self.panel.log(
                f"{action} failed with API status {status_code}. Check API logs and refresh again."
            )
            self._logger.error("%s failed with status=%s", action, status_code)
            return
        self.panel.log(f"{action} failed: {exc}")
        self._logger.error("%s failed: %s", action, exc)

    def _connect_signals(self) -> None:
        self.panel.browse_btn.clicked.connect(self.browse_path)
        self.panel.preview_btn.clicked.connect(self.preview_selected_path)
        self.panel.save_btn.clicked.connect(self.save_selected_path)
        self.panel.refresh_assets_btn.clicked.connect(self.refresh_assets)
        self.panel.add_layer_btn.clicked.connect(self.add_selected_layer)
        self.panel.apply_visual_btn.clicked.connect(self.apply_visual_settings)
        self.panel.apply_dem_btn.clicked.connect(self.apply_dem_settings)
        self.panel.apply_rgb_view_mode_btn.clicked.connect(self.apply_rgb_view_mode)
        self.panel.rotate_left_btn.clicked.connect(lambda: self.rotate_camera(-10.0))
        self.panel.rotate_right_btn.clicked.connect(lambda: self.rotate_camera(10.0))
        self.panel.pitch_slider.valueChanged.connect(self.set_pitch)
        self.panel.search_point_btn.clicked.connect(self.search_assets_by_coordinate)
        self.panel.search_bbox_btn.clicked.connect(self.search_assets_by_bbox)
        self.panel.search_draw_box_btn.clicked.connect(lambda: self.set_search_draw_mode("box"))
        self.panel.search_draw_polygon_btn.clicked.connect(lambda: self.set_search_draw_mode("polygon"))
        self.panel.search_finish_polygon_btn.clicked.connect(self.finish_search_polygon)
        self.panel.search_clear_geometry_btn.clicked.connect(self.clear_search_geometry)
        self.panel.search_from_draw_btn.clicked.connect(self.search_assets_from_drawn_geometry)
        self.panel.add_annotation_btn.clicked.connect(self.add_annotation)
        self.panel.extract_profile_btn.clicked.connect(self.extract_dem_profile)
        self.bridge.mapClicked.connect(self.on_map_click)
        self.bridge.measurementUpdated.connect(self.on_measurement)
        self.bridge.jsLogReceived.connect(self.on_js_log)
        self.bridge.searchGeometryChanged.connect(self.on_search_geometry)
        self.panel.uploaded_assets_list.itemSelectionChanged.connect(self.preview_selected_uploaded_asset)

    def preview_selected_uploaded_asset(self) -> None:
        row = self.panel.uploaded_assets_list.currentRow()
        if row < 0:
            return
        item = self.panel.uploaded_assets_list.item(row, 0)
        if item is None:
            return
        asset = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(asset, dict):
            return

        file_path = str(asset.get("file_path") or "")
        if not file_path:
            return

        self._asset_cache[file_path] = asset
        self.state.selected_asset = asset
        self._select_asset_in_combo(file_path)
        loaded_asset = self._load_asset_layer(asset)
        if not loaded_asset:
            return
        self.panel.log(f"Layer added: {loaded_asset['file_name']}")
        self._logger.info(
            "Layer add requested from uploaded assets name=%s kind=%s url=%s",
            loaded_asset["file_name"],
            loaded_asset["kind"],
            loaded_asset["tile_url"],
        )

    def enqueue_selected_path(self) -> None:
        if not self._require_offline_endpoints("Save raster"):
            return
        path = self.panel.path_edit.text().strip()
        if not path:
            self.panel.log("Select a file path first.")
            return
        if not Path(path).exists():
            self.panel.log(f"Path does not exist: {path}")
            return
        try:
            job = self.api.enqueue_ingest_job([path])
        except httpx.HTTPError as exc:
            self._handle_api_error("Queue ingest", exc)
            return
        self.state.active_ingest_job_id = str(job.get("id"))
        self.state.pending_ingest_source_path = path
        self.state.auto_visualize_ingest_result = True
        self.panel.log(
            "Saved to ingest queue "
            f"id={job.get('id')} total={job.get('total_items')} status={job.get('status')}"
        )
        self.panel.log("Checkpointing and auto-resume are enabled for this job.")
        self._update_ingest_progress_ui(job, emit_detail=True)
        self._ingest_poll_timer.start()

    def search_assets_by_coordinate(self) -> None:
        if not self._require_offline_endpoints("Coordinate search"):
            return
        lon = float(self.panel.search_coord_lon.value())
        lat = float(self.panel.search_coord_lat.value())
        try:
            assets = self.api.search_assets_by_point(lon=lon, lat=lat)
        except httpx.HTTPError as exc:
            self._handle_api_error("Coordinate search", exc)
            return
        self._apply_search_results(assets, label=f"Coordinate search ({lon:.6f}, {lat:.6f})")

    def search_assets_by_bbox(self) -> None:
        if not self._require_offline_endpoints("BBox search"):
            return
        west = float(self.panel.search_west.value())
        south = float(self.panel.search_south.value())
        east = float(self.panel.search_east.value())
        north = float(self.panel.search_north.value())
        try:
            assets = self.api.search_assets_by_bbox(west=west, south=south, east=east, north=north)
        except httpx.HTTPError as exc:
            self._handle_api_error("BBox search", exc)
            return
        self._apply_search_results(assets, label="BBox search")

    def search_assets_from_drawn_geometry(self) -> None:
        if not self._require_offline_endpoints("Drawn geometry search"):
            return
        geometry_type = self.state.search_geometry_type
        payload = self.state.search_geometry_payload or {}
        if geometry_type is None:
            self.panel.log("Draw a search geometry first.")
            return

        try:
            if geometry_type == "bbox":
                assets = self.api.search_assets_by_bbox(
                    west=float(payload["west"]),
                    south=float(payload["south"]),
                    east=float(payload["east"]),
                    north=float(payload["north"]),
                )
            elif geometry_type == "polygon":
                points = [
                    (float(item["lon"]), float(item["lat"]))
                    for item in payload.get("points", [])
                ]
                assets = self.api.search_assets_by_polygon(
                    points=points,
                    buffer_meters=float(self.panel.search_buffer_m.value()),
                )
            else:
                self.panel.log(f"Unsupported drawn geometry type: {geometry_type}")
                return
        except (KeyError, ValueError, TypeError):
            self.panel.log("Invalid drawn geometry payload.")
            self._logger.exception("Invalid drawn geometry payload=%s", payload)
            return
        except httpx.HTTPError as exc:
            self._handle_api_error("Drawn geometry search", exc)
            return

        self._apply_search_results(assets, label=f"Drawn {geometry_type} search")

    def set_search_draw_mode(self, mode: str) -> None:
        self._run_js_call("setSearchDrawMode", mode)
        self.panel.log(f"Search draw mode enabled: {mode}")

    def finish_search_polygon(self) -> None:
        self._run_js_call("finishSearchPolygon")

    def clear_search_geometry(self) -> None:
        self._run_js_call("clearSearchGeometry")
        self.state.search_geometry_type = None
        self.state.search_geometry_payload = None
        self.panel.log("Search geometry cleared.")

    def on_search_geometry(self, geometry_type: str, payload_json: str) -> None:
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            self._logger.error("Invalid geometry payload JSON: %s", payload_json)
            return
        self.state.search_geometry_type = geometry_type
        self.state.search_geometry_payload = payload
        self.panel.log(f"Search geometry updated: type={geometry_type}")

    def _apply_search_results(self, assets: list[dict], label: str) -> None:
        self.panel.assets_combo.clear()
        self._asset_cache = {}
        local_missing_count = 0
        for asset in assets:
            if not self._asset_path_accessible_locally(asset):
                local_missing_count += 1
            self._asset_cache[asset["file_path"]] = asset
            display = f"{asset['file_name']} [{asset['kind']}]"
            self.panel.assets_combo.addItem(display, asset)
        self.panel.log(f"{label}: {self.panel.assets_combo.count()} assets")
        if local_missing_count:
            self.panel.log(
                f"Note: {local_missing_count} result(s) are remote-only paths; loading uses server-side tiles."
            )

    def browse_path(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self.panel,
            "Select raster file",
            "",
            "Raster Files (*.tif *.tiff *.jp2 *.j2k *.mbtiles);;All Files (*)",
        )
        if not path:
            return
        self.panel.path_edit.setText(path)
        self.panel.log(f"Selected file: {path}")
        self._logger.info("Selected file path: %s", path)

    def preview_selected_path(self) -> None:
        if not self._require_offline_endpoints("Preview raster"):
            return

        path = self.panel.path_edit.text().strip()
        if not path:
            self.panel.log("Select a file path first.")
            return
        source = Path(path)
        if not source.exists():
            self.panel.log(f"Path does not exist: {path}")
            return
        if not self.titiler.ensure_running():
            self.panel.log("TiTiler is not available; preview cannot be rendered.")
            self._logger.error("TiTiler unavailable during preview")
            return

        try:
            metadata = extract_metadata(source)
        except FileNotFoundError as exc:
            self.panel.log(str(exc))
            return
        except MetadataExtractorError as exc:
            self.panel.log(f"Preview failed: {exc}")
            self._logger.exception("Preview metadata extraction failed for path=%s", path)
            return

        centroid_x, centroid_y = metadata.bounds.centroid()
        preview_asset = {
            "id": f"preview:{source}",
            "file_name": metadata.file_name,
            "file_path": str(source),
            "kind": metadata.kind.value,
            "crs": metadata.crs,
            "centroid": {"lon": centroid_x, "lat": centroid_y},
            "bounds_wkt": metadata.bounds.to_wkt_polygon(),
            "tile_url": build_xyz_url(str(source)),
        }

        self.state.selected_asset = preview_asset
        bounds = self._asset_bounds(preview_asset)
        options = self._layer_options(preview_asset, bounds)
        self.panel.rgb_view_mode_combo.setCurrentIndex(0)
        self._set_layer_loading(True, f"Previewing {metadata.file_name}...")
        if self._add_layer(preview_asset, options):
            if not self._fly_through_asset(preview_asset):
                self._fly_to_asset(preview_asset)
            self.panel.log(
                "Preview ready: "
                f"{metadata.file_name} ({metadata.kind.value.upper()}) | "
                f"CRS {metadata.crs} | {metadata.width}x{metadata.height}"
            )
            return

        self._set_layer_loading(False, "Preview failed")

    def save_selected_path(self) -> None:
        # Save is queue-driven so checkpoint/resume protects long ingests.
        self.enqueue_selected_path()

    def refresh_assets(self) -> None:
        if not self._require_offline_endpoints("Catalog refresh"):
            return
        try:
            assets = self.api.list_assets()
        except httpx.HTTPError as exc:
            self._handle_api_error("Catalog refresh", exc)
            return
        self.panel.assets_combo.clear()
        for asset in assets:
            self._asset_cache[asset["file_path"]] = asset
            name_suffix = ""
            if not self._asset_path_accessible_locally(asset):
                name_suffix = " (remote)"
            label = f"{asset['file_name']} [{asset['kind']}]"
            label += name_suffix
            self.panel.assets_combo.addItem(label, asset)
        
        # Refresh uploaded assets list on server mode
        if self.app_mode == DesktopAppMode.SERVER:
            self.panel.refresh_uploaded_assets()
        shown = self.panel.assets_combo.count()
        self.panel.log(f"Catalog refreshed: {shown} assets")
        self._logger.info("Catalog refreshed visible=%s total=%s", shown, len(assets))

    def _select_asset_in_combo(self, file_path: str) -> bool:
        if not file_path:
            return False
        for index in range(self.panel.assets_combo.count()):
            item = self.panel.assets_combo.itemData(index)
            if not isinstance(item, dict):
                continue
            if str(item.get("file_path") or "") == file_path:
                self.panel.assets_combo.setCurrentIndex(index)
                return True
        return False

    def _poll_active_ingest_job(self) -> None:
        if not self._require_offline_endpoints("Ingest progress refresh"):
            self._ingest_poll_timer.stop()
            return
        job_id = self.state.active_ingest_job_id
        if not job_id:
            self._ingest_poll_timer.stop()
            return
        try:
            job = self.api.get_ingest_job(job_id)
        except httpx.HTTPError as exc:
            self._handle_api_error("Ingest progress refresh", exc)
            self._ingest_poll_timer.stop()
            return

        self._update_ingest_progress_ui(job, emit_detail=True)
        status = str(job.get("status") or "").lower()
        if status in {"completed", "failed", "partial"}:
            self._ingest_poll_timer.stop()
            if status in {"completed", "partial"} and self.state.auto_visualize_ingest_result:
                self._try_visualize_ingested_asset()

    def _update_ingest_progress_ui(self, job: dict, *, emit_detail: bool) -> None:
        status = str(job.get("status") or "unknown").lower()
        total_items = int(job.get("total_items") or 0)
        processed_items = int(job.get("processed_items") or 0)
        failed_items = int(job.get("failed_items") or 0)
        checkpoint = int(job.get("checkpoint_item_index") or 0)
        progress_percent = int(job.get("progress_percent") or 0)
        current_step = str(job.get("current_step") or self._default_step_for_status(status))
        current_item_path = str(job.get("current_item_path") or "")
        elapsed_seconds = job.get("elapsed_seconds")

        self.panel.ingest_progress_bar.setValue(max(0, min(progress_percent, 100)))
        self.panel.ingest_status_value.setText(status.upper())
        self.panel.ingest_step_value.setText(current_step)
        self.panel.ingest_counts_value.setText(
            f"Processed {processed_items}/{total_items} | Failed {failed_items} | Checkpoint {checkpoint}"
        )
        self.panel.ingest_item_value.setText(f"Source: {current_item_path or '-'}")
        self.panel.ingest_elapsed_value.setText(f"Elapsed {self._format_elapsed(elapsed_seconds)}")

        if emit_detail and (self._last_ingest_step != current_step or self._last_ingest_status != status):
            self.panel.append_ingest_detail(
                f"[{self._format_elapsed(elapsed_seconds)}] {status.upper()} - {current_step}"
            )
            self._last_ingest_step = current_step
            self._last_ingest_status = status

        if emit_detail and status in {"completed", "failed", "partial"}:
            self.panel.log(
                f"Ingest job {job.get('id')} finished with status={status} processed={processed_items}/{total_items} failed={failed_items}"
            )

    @staticmethod
    def _default_step_for_status(status: str) -> str:
        mapping = {
            "queued": "Queued for metadata ingest",
            "running": "Processing source metadata",
            "completed": "Metadata indexing completed",
            "partial": "Completed with partial failures",
            "failed": "Ingest failed",
            "paused": "Ingest paused",
        }
        return mapping.get(status, "Ingest status updated")

    @staticmethod
    def _format_elapsed(elapsed_seconds: float | int | None) -> str:
        if elapsed_seconds is None:
            return "00:00"
        elapsed = max(0.0, float(elapsed_seconds))
        if 0.0 < elapsed < 1.0:
            return "<1s"

        total_seconds = max(0, int(round(elapsed)))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def _selected_asset(self) -> dict | None:
        item = self.panel.assets_combo.currentData()
        if isinstance(item, dict):
            if self._asset_path_accessible_locally(item) or self.app_mode == DesktopAppMode.CLIENT:
                return item
            self._logger.warning("Combo selected asset missing on disk path=%s", item.get("file_path"))
            return None
        if isinstance(self.state.selected_asset, dict):
            path = self.state.selected_asset.get("file_path", "")
            if self._asset_path_accessible_locally(self.state.selected_asset) or self.app_mode == DesktopAppMode.CLIENT:
                return self.state.selected_asset
            self._logger.warning("Ignoring stale selected asset path=%s", path)
            self.state.selected_asset = None
        return None

    def add_selected_layer(self) -> None:
        asset = self._selected_asset()
        if not asset:
            self.panel.log("No selected asset.")
            self._logger.warning("Add layer requested with no selected asset")
            return
        loaded_asset = self._load_asset_layer(asset)
        if not loaded_asset:
            return
        self.panel.log(f"Layer added: {loaded_asset['file_name']}")
        self._logger.info(
            "Layer add requested name=%s kind=%s url=%s",
            loaded_asset["file_name"],
            loaded_asset["kind"],
            loaded_asset["tile_url"],
        )

    def _load_asset_layer(self, asset: dict) -> dict | None:
        self._set_layer_loading(True, f"Loading {asset['file_name']}...")
        if self.app_mode != DesktopAppMode.CLIENT and not Path(asset["file_path"]).exists():
            self.panel.log(f"File not found on disk: {asset['file_path']}")
            self._logger.error("Cannot add layer; file missing path=%s", asset["file_path"])
            self._set_layer_loading(False, "Layer load failed")
            return None
        if not self.titiler.ensure_running():
            self.panel.log("Warning: TiTiler could not start. Layer may not draw.")
            self._logger.error("TiTiler unavailable before add layer")
        bounds = self._asset_bounds(asset)
        if bounds is None:
            try:
                fresh = self.api.register_raster(asset["file_path"])
                self._asset_cache[fresh["file_path"]] = fresh
                asset = fresh
                bounds = self._asset_bounds(asset)
                self._logger.info("Refreshed metadata for selected asset before layer add")
            except httpx.HTTPError:
                self._logger.exception("Failed to refresh metadata before layer add")
        options = self._layer_options(asset, bounds)
        if self._add_layer(asset, options):
            self._fly_through_asset(asset)
        else:
            self._set_layer_loading(False, "Layer load failed")
            return None
        self.state.selected_asset = asset
        return asset

    def _fly_through_asset(self, asset: dict) -> bool:
        bounds = self._asset_bounds(asset)
        if bounds is None:
            center = self._asset_centroid(asset)
            if center is None:
                self._logger.warning("Fly-through unavailable for asset=%s", asset.get("file_name"))
                return False
            # Fallback micro-bounds around centroid when exact bounds are unavailable.
            delta = 0.01
            bounds = {
                "west": center["lon"] - delta,
                "south": center["lat"] - delta,
                "east": center["lon"] + delta,
                "north": center["lat"] + delta,
            }

        self._run_js_call(
            "flyThroughBounds",
            bounds["west"],
            bounds["south"],
            bounds["east"],
            bounds["north"],
        )
        return True

    def _try_visualize_ingested_asset(self) -> None:
        source_path = self.state.pending_ingest_source_path
        if not source_path:
            return

        try:
            assets = self.api.list_assets()
        except httpx.HTTPError as exc:
            self._handle_api_error("Load ingested asset", exc)
            return

        match = next((asset for asset in assets if asset.get("file_path") == source_path), None)
        if not isinstance(match, dict):
            self.panel.log("Ingest completed, but catalog item is not yet visible. Use Refresh Assets.")
            return

        self._asset_cache[match["file_path"]] = match
        self.state.selected_asset = match
        self.refresh_assets()
        options = self._layer_options(match, self._asset_bounds(match))
        self._set_layer_loading(True, f"Loading {match['file_name']}...")
        if self._add_layer(match, options):
            self._fly_through_asset(match)
        else:
            self._set_layer_loading(False, "Layer load failed")
        self.panel.log(f"Auto-loaded ingested asset: {match['file_name']}")
        self.state.auto_visualize_ingest_result = False
        self.state.pending_ingest_source_path = None

    def apply_rgb_view_mode(self) -> None:
        mode = str(self.panel.rgb_view_mode_combo.currentData() or "3d")
        if self.state.active_layer_is_dem and mode == "2d":
            self.panel.log("DEM is terrain-only. 2D mode is disabled for DEM; staying in 3D.")
            self.panel.rgb_view_mode_combo.setCurrentIndex(0)
            self._run_js_call("setSceneMode", "3d")
            return

        self._run_js_call("setSceneMode", mode)
        mode_label = "2D map" if mode == "2d" else "3D terrain"
        self.panel.log(f"RGB view mode applied: {mode_label}")

    def apply_visual_settings(self) -> None:
        brightness = self.panel.brightness_slider.value() / 100.0
        contrast = self.panel.contrast_slider.value() / 100.0
        self._run_js_call("setImageryProperties", brightness, contrast)
        self.panel.log(f"Applied imagery settings brightness={brightness:.2f}, contrast={contrast:.2f}")
        self._logger.info("Applied imagery settings brightness=%.2f contrast=%.2f", brightness, contrast)

    def apply_dem_settings(self, _checked: bool | None = None, log_to_panel: bool = True) -> None:
        exaggeration = self.panel.dem_exaggeration_slider.value() / 100.0
        hillshade_strength = self.panel.dem_hillshade_slider.value() / 100.0
        azimuth = int(self.panel.dem_azimuth_slider.value())
        altitude = int(self.panel.dem_altitude_slider.value())
        self._run_js_call("setDemProperties", exaggeration, hillshade_strength, azimuth, altitude)
        if log_to_panel:
            self.panel.log(
                "Applied DEM settings "
                f"exaggeration={exaggeration:.2f}, hillshade={hillshade_strength:.2f}, "
                f"azimuth={azimuth}, altitude={altitude}"
            )
        self._logger.info(
            "Applied DEM settings exaggeration=%.2f hillshade=%.2f azimuth=%s altitude=%s",
            exaggeration,
            hillshade_strength,
            azimuth,
            altitude,
        )

    def rotate_camera(self, degrees: float) -> None:
        self._run_js_call("rotateCamera", degrees)
        self._logger.debug("Rotate camera degrees=%s", degrees)

    def set_pitch(self, degrees: int) -> None:
        self._run_js_call("setPitch", float(degrees))
        self._logger.debug("Set camera pitch degrees=%s", degrees)

    def on_map_click(self, lon: float, lat: float) -> None:
        self.state.clicked_points.append((lon, lat))
        self.state.clicked_points = self.state.clicked_points[-2:]
        self.panel.click_label.setText(f"Last click: lon={lon:.6f}, lat={lat:.6f}")
        self._logger.debug("Map click lon=%.6f lat=%.6f", lon, lat)

    def on_measurement(self, meters: float) -> None:
        self.panel.measure_label.setText(f"Last distance: {meters:.2f} m")
        self._logger.info("Measurement updated distance_m=%.2f", meters)

    def add_annotation(self) -> None:
        if not self.state.clicked_points:
            self.panel.log("Click on the globe first to place annotation.")
            self._logger.warning("Annotation requested without click")
            return
        text = self.panel.annotation_edit.text().strip()
        if not text:
            self.panel.log("Enter annotation text.")
            self._logger.warning("Annotation requested without text")
            return
        lon, lat = self.state.clicked_points[-1]
        self._run_js_call("addAnnotation", text, lon, lat)
        self.panel.log(f"Annotation added at {lon:.5f}, {lat:.5f}")
        self._logger.info("Annotation added lon=%.5f lat=%.5f text=%s", lon, lat, text)

    def extract_dem_profile(self) -> None:
        asset = self._selected_asset()
        if not asset:
            self.panel.log("Select a DEM asset first.")
            self._logger.warning("Profile requested without selected asset")
            return
        if len(self.state.clicked_points) < 2:
            self.panel.log("Click two points on the globe to define transect.")
            self._logger.warning("Profile requested without two clicks")
            return
        samples = int(self.panel.profile_samples.value())
        try:
            result = self.api.extract_profile(asset["file_path"], self.state.clicked_points[-2:], samples=samples)
        except httpx.HTTPError as exc:
            self.panel.log(f"Profile extraction failed: {exc}")
            self._logger.exception("Profile extraction failed path=%s", asset["file_path"])
            return
        values = result.get("values", [])
        if not values:
            self.panel.log("Profile extraction returned no values.")
            self._logger.warning("Profile returned empty values path=%s", asset["file_path"])
            return
        preview = ", ".join(f"{v:.2f}" for v in values[:10])
        self.panel.log(f"Profile extracted ({len(values)} samples). First values: {preview}")
        self._logger.info("Profile extracted samples=%s path=%s", len(values), asset["file_path"])

    def _run_js_call(self, method: str, *args) -> None:
        encoded = ", ".join(json.dumps(arg) for arg in args)
        script = f"window.offlineGIS && window.offlineGIS.{method}({encoded});"
        self._logger.debug("JS call: %s args=%s", method, args)
        self.web_view.page().runJavaScript(script)

    def _asset_centroid(self, asset: dict) -> dict[str, float] | None:
        cached = self._asset_cache.get(asset["file_path"])
        if cached and isinstance(cached.get("centroid"), dict):
            c = cached["centroid"]
            if self._is_valid_lon_lat(c.get("lon"), c.get("lat")):
                return c
        bounds_wkt = asset.get("bounds_wkt")
        if not bounds_wkt:
            return None
        from offline_gis_app.utils.geometry import parse_bounds_wkt_polygon

        bounds = parse_bounds_wkt_polygon(bounds_wkt)
        lon, lat = bounds.centroid()
        if not self._is_valid_lon_lat(lon, lat):
            return None
        return {"lon": lon, "lat": lat}

    def _asset_bounds(self, asset: dict) -> dict[str, float] | None:
        bounds_wkt = asset.get("bounds_wkt")
        if not bounds_wkt:
            return None
        from offline_gis_app.utils.geometry import parse_bounds_wkt_polygon

        b = parse_bounds_wkt_polygon(bounds_wkt)
        if not self._is_valid_lon_lat(b.min_x, b.min_y) or not self._is_valid_lon_lat(b.max_x, b.max_y):
            self._logger.warning(
                "Skipping invalid bounds for file=%s min=(%s,%s) max=(%s,%s)",
                asset.get("file_path"),
                b.min_x,
                b.min_y,
                b.max_x,
                b.max_y,
            )
            return None
        return {"west": b.min_x, "south": b.min_y, "east": b.max_x, "north": b.max_y}

    def _fly_to_asset(self, asset: dict) -> bool:
        bounds = self._asset_bounds(asset)
        if bounds is not None:
            self._run_js_call(
                "flyToBounds",
                bounds["west"],
                bounds["south"],
                bounds["east"],
                bounds["north"],
            )
            return True
        center = self._asset_centroid(asset)
        if center is None:
            c = asset.get("centroid", {})
            self._logger.error("No valid fly-to target for asset=%s centroid=%s", asset.get("file_name"), c)
            return False
        self._run_js_call("flyTo", center["lon"], center["lat"], 9000)
        return True

    def _layer_options(self, asset: dict, bounds: dict[str, float] | None) -> dict:
        options: dict = {"bounds": bounds, "is_dem": self._is_dem_asset(asset)}
        try:
            tilejson = self.api.get_tilejson(asset["file_path"])
        except httpx.HTTPError as exc:
            self._logger.warning("TileJSON unavailable for %s: %s", asset["file_name"], exc)
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
            if self._is_valid_lon_lat(w, s) and self._is_valid_lon_lat(e, n):
                tilejson_bounds = {"west": float(w), "south": float(s), "east": float(e), "north": float(n)}
                if self._is_near_global_bounds(tilejson_bounds) and bounds and not self._is_near_global_bounds(bounds):
                    self._logger.warning(
                        "Ignoring near-global TileJSON bounds for %s and keeping catalog bounds.",
                        asset.get("file_name"),
                    )
                else:
                    options["bounds"] = tilejson_bounds

        raster_query = self._raster_render_query(asset)
        if raster_query:
            options["query"] = raster_query
        self._logger.info("Layer options for %s: %s", asset["file_name"], options)
        return options

    def _add_layer(self, asset: dict, options: dict) -> bool:
        tile_url = str(asset.get("tile_url") or "")
        if not self._is_offline_safe_url(tile_url):
            self.panel.log(f"Blocked non-offline tile URL for {asset.get('file_name', 'asset')}")
            self._logger.error("Blocked non-offline tile URL: %s", tile_url)
            return False

        is_dem = bool(options.get("is_dem"))
        if is_dem:
            self.state.active_layer_is_dem = True
            self._run_js_call("addDemLayer", asset["file_name"], asset["tile_url"], options)
            self._run_js_call("setSceneModeControlEnabled", False)
            self.panel.rgb_view_mode_combo.setCurrentIndex(0)
            self.panel.rgb_view_mode_combo.setEnabled(False)
            self.panel.apply_rgb_view_mode_btn.setEnabled(False)
            if not self._dem_settings_are_default():
                self.apply_dem_settings(log_to_panel=False)
            self._logger.info("DEM terrain layer requested name=%s", asset["file_name"])
            return True
        self.state.active_layer_is_dem = False
        self.panel.rgb_view_mode_combo.setEnabled(True)
        self.panel.apply_rgb_view_mode_btn.setEnabled(True)
        self._run_js_call("setSceneModeControlEnabled", True)
        mode = str(self.panel.rgb_view_mode_combo.currentData() or "3d").lower()
        if mode not in {"2d", "3d"}:
            mode = "3d"
        self._run_js_call("setSceneMode", mode)
        self._run_js_call("addTileLayer", asset["file_name"], asset["tile_url"], asset["kind"], options)
        return True

    def _dem_settings_are_default(self) -> bool:
        return (
            int(self.panel.dem_exaggeration_slider.value()) == 150
            and int(self.panel.dem_hillshade_slider.value()) == 75
            and int(self.panel.dem_azimuth_slider.value()) == 45
            and int(self.panel.dem_altitude_slider.value()) == 45
        )

    def _is_dem_asset(self, asset: dict) -> bool:
        kind = str(asset.get("kind", "")).lower()
        file_name = str(asset.get("file_name", "")).lower()
        if kind == "dem" or "dem" in file_name:
            return True
        try:
            info = self.api.get_cog_info(asset["file_path"])
        except (httpx.HTTPError, KeyError, TypeError):
            return False
        try:
            return int(info.get("count", 0) or 0) == 1
        except (TypeError, ValueError):
            return False

    def _raster_render_query(self, asset: dict) -> dict[str, object]:
        try:
            info = self.api.get_cog_info(asset["file_path"])
        except httpx.HTTPError:
            return {}
        band_count = int(info.get("count", 1) or 1)
        is_dem = str(asset.get("kind", "")).lower() == "dem" or "dem" in str(asset.get("file_name", "")).lower()
        query: dict[str, object] = {}

        # Always constrain multi-band non-DEM rasters to RGB to avoid TiTiler PNG encoding failures.
        if band_count >= 3 and not is_dem:
            query["bidx"] = [1, 2, 3]

        try:
            stats = self.api.get_cog_statistics(asset["file_path"])
        except httpx.HTTPError as exc:
            self._logger.warning("Statistics unavailable for %s: %s", asset["file_name"], exc)
            return query

        if not isinstance(stats, dict) or not stats:
            return query

        if band_count >= 3 and not is_dem:
            lows = []
            highs = []
            for i in range(1, min(3, band_count) + 1):
                stat = stats.get(f"b{i}")
                if not isinstance(stat, dict):
                    continue
                low = stat.get("percentile_2", stat.get("min"))
                high = stat.get("percentile_98", stat.get("max"))
                if low is None or high is None:
                    continue
                lows.append(float(low))
                highs.append(float(high))
            if len(lows) == 3 and max(highs) > min(lows):
                query["rescale"] = f"{min(lows)},{max(highs)}"
            return query

        first_band = stats.get("b1") if isinstance(stats.get("b1"), dict) else next(iter(stats.values()))
        if not isinstance(first_band, dict):
            return {}
        low = first_band.get("percentile_2", first_band.get("min"))
        high = first_band.get("percentile_98", first_band.get("max"))
        if low is None or high is None or float(high) <= float(low):
            return query
        if is_dem:
            return {"rescale": f"{float(low)},{float(high)}", "colormap_name": "terrain"}
        return {"rescale": f"{float(low)},{float(high)}"}

    @staticmethod
    def _is_valid_lon_lat(lon, lat) -> bool:
        if lon is None or lat is None:
            return False
        try:
            lon_v = float(lon)
            lat_v = float(lat)
        except (TypeError, ValueError):
            return False
        return -180.0 <= lon_v <= 180.0 and -90.0 <= lat_v <= 90.0

    @staticmethod
    def _is_near_global_bounds(bounds: dict[str, float] | None) -> bool:
        if not isinstance(bounds, dict):
            return False
        try:
            west = float(bounds.get("west"))
            south = float(bounds.get("south"))
            east = float(bounds.get("east"))
            north = float(bounds.get("north"))
        except (TypeError, ValueError):
            return False
        return west <= -179.5 and east >= 179.5 and south <= -84.5 and north >= 84.5

    def on_js_log(self, level: str, message: str) -> None:
        normalized = level.lower().strip()
        if self._layer_loading_active and (
            "Fly-through started" in message
            or "Fly-to bounds" in message
            or "Fly-to lon=" in message
        ):
            self._set_layer_loading(False, "Layer ready")

        if "Tile provider error for" in message:
            self._logger.warning("JS: %s", message)
            return
        if normalized == "debug":
            self._logger.debug("JS: %s", message)
            return
        if normalized in {"warn", "warning"}:
            self._logger.warning("JS: %s", message)
            return
        if normalized == "error":
            self._logger.error("JS: %s", message)
            if self._layer_loading_active:
                self._set_layer_loading(False, "Layer load failed")
            return
        self._logger.info("JS: %s", message)

    def _set_layer_loading(self, active: bool, message: str) -> None:
        self._layer_loading_active = active
        self.panel.set_layer_loading(active, message)

    def _asset_path_accessible_locally(self, asset: dict) -> bool:
        path = str(asset.get("file_path") or "")
        if not path:
            return False
        return Path(path).exists()

    def _validate_offline_endpoints(self) -> bool:
        api_ok = self._is_offline_safe_url(self.api.base_url)
        titiler_ok = self._is_offline_safe_url(self.api.titiler_base_url)
        if api_ok and titiler_ok:
            return True

        self.panel.log("Offline guard: API/TiTiler endpoints must be local or private-network addresses.")
        if not api_ok:
            self.panel.log(f"Blocked API endpoint: {self.api.base_url}")
        if not titiler_ok:
            self.panel.log(f"Blocked TiTiler endpoint: {self.api.titiler_base_url}")
        self._logger.error(
            "Offline endpoint validation failed api=%s titiler=%s",
            self.api.base_url,
            self.api.titiler_base_url,
        )
        return False

    def _require_offline_endpoints(self, action: str) -> bool:
        if self._offline_endpoints_valid:
            return True
        self.panel.log(f"{action} blocked by offline guard. Configure local/private API and TiTiler endpoints.")
        self._logger.warning("Blocked action by offline guard: %s", action)
        return False

    @staticmethod
    def _is_offline_safe_url(url: str) -> bool:
        try:
            parsed = urlparse(url)
        except ValueError:
            return False

        if parsed.scheme == "file":
            return True
        if parsed.scheme not in {"http", "https"}:
            return False

        host = (parsed.hostname or "").lower()
        if not host:
            return False
        if host in {"localhost", "127.0.0.1", "::1"}:
            return True

        try:
            ip = ipaddress.ip_address(host)
            return ip.is_private or ip.is_loopback or ip.is_link_local
        except ValueError:
            # LAN aliases and mDNS hostnames are accepted in offline deployments.
            return host.endswith(".local") or "." not in host
