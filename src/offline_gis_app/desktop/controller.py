from __future__ import annotations

import csv
import datetime as dt
import ipaddress
import json
import logging
import math
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import httpx
from pyproj import Transformer
from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal
from PySide6.QtWidgets import QFileDialog
from PySide6.QtWebEngineWidgets import QWebEngineView

from offline_gis_app.desktop.api_client import DesktopApiClient
from offline_gis_app.desktop.api_server_manager import ApiServerManager
from offline_gis_app.desktop.app_mode import DesktopAppMode
from offline_gis_app.desktop.bridge import WebBridge
from offline_gis_app.desktop.control_panel import ControlPanel
from offline_gis_app.desktop.state import DesktopState
from offline_gis_app.desktop.titiler_manager import TiTilerManager
from offline_gis_app.services.scientific_measurements import (
    compute_slope_aspect,
    compute_viewshed,
    compute_volume,
    measure_distance,
    measure_shadow_height,
)
from offline_gis_app.services.metadata_extractor import MetadataExtractorError, extract_metadata
from offline_gis_app.services.tile_url_builder import build_xyz_url


class _MeasurementWorkerSignals(QObject):
    finished = Signal(str, object, str)


class _MeasurementWorker(QRunnable):
    def __init__(self, name: str, task: Callable[[], object]):
        super().__init__()
        self._name = name
        self._task = task
        self.signals = _MeasurementWorkerSignals()

    def run(self) -> None:  # type: ignore[override]
        try:
            result = self._task()
            self.signals.finished.emit(self._name, result, "")
        except Exception as exc:  # pragma: no cover - runtime defensive branch
            self.signals.finished.emit(self._name, None, str(exc))


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
        toolbar_context_callback: Callable[[str], None] | None = None,
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
        self._toolbar_context_callback = toolbar_context_callback
        self._asset_cache: dict[str, dict] = {}
        self._dem_asset_kind_cache: dict[str, bool] = {}
        self._search_result_assets_by_path: dict[str, dict] = {}
        self._search_layer_visibility: dict[str, bool] = {}
        self._loaded_search_layer_keys: set[str] = set()
        self._active_dem_search_layer_key: str | None = None
        self._last_visible_focus_signature: tuple[float, float, float, float] | None = None
        self._offline_endpoints_valid = True
        self._layer_loading_active = False
        self._measurement_pool = QThreadPool(panel)
        self._measurement_pool.setMaxThreadCount(1)
        self._swipe_comparator_enabled = False
        self._hillshade_enabled = bool(self.panel.dem_hillshade_slider.value() > 0)
        self._last_hillshade_strength_percent = max(20, int(self.panel.dem_hillshade_slider.value()))
        self._distance_measure_mode_enabled = False
        self._add_point_mode_enabled = False
        self._shadow_height_mode_enabled = False
        self._pan_mode_enabled = True
        self._explicit_imagery_layer_visible = False
        self._explicit_dem_layer_visible = False
        self._last_distance_measurement_signature: tuple[float, float, float, float, float] | None = None
        self._last_profile_values: list[float] = []
        self._measurement_history: list[str] = []
        self._annotation_records: list[dict[str, object]] = []
        self._annotation_line_records: list[dict[str, object]] = []
        self._annotation_polygon_records: list[dict[str, object]] = []
        self._ingest_poll_timer = QTimer(panel)
        self._ingest_poll_timer.setInterval(1000)
        self._ingest_poll_timer.timeout.connect(self._poll_active_ingest_job)
        self._last_ingest_step: str | None = None
        self._last_ingest_status: str | None = None
        self._logger.info("Controller initialized mode=%s", self.app_mode.value)
        self._connect_signals()
        self._apply_display_control_mode()
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
        self._connect_button(self.panel.browse_btn.clicked, "Browse Path", self.browse_path)
        self._connect_button(self.panel.preview_btn.clicked, "Preview Path", self.preview_selected_path)
        self._connect_button(self.panel.save_btn.clicked, "Save Path", self.save_selected_path)
        self._connect_button(self.panel.refresh_assets_btn.clicked, "Refresh Assets", self.refresh_assets)
        self._connect_button(self.panel.add_layer_btn.clicked, "Add Layer", self.add_selected_layer)
        self.panel.brightness_slider.valueChanged.connect(self._on_visual_slider_changed)
        self.panel.contrast_slider.valueChanged.connect(self._on_visual_slider_changed)
        self.panel.dem_exaggeration_slider.valueChanged.connect(self._on_dem_slider_changed)
        self.panel.dem_hillshade_slider.valueChanged.connect(self._on_dem_slider_changed)
        self.panel.dem_azimuth_slider.valueChanged.connect(self._on_dem_slider_changed)
        self.panel.dem_altitude_slider.valueChanged.connect(self._on_dem_slider_changed)
        self.panel.dem_color_mode_combo.currentIndexChanged.connect(self._on_dem_color_mode_changed)
        self._connect_button(self.panel.apply_rgb_view_mode_btn.clicked, "Apply RGB View Mode", self.apply_rgb_view_mode)
        self._connect_button(self.panel.rotate_left_btn.clicked, "Rotate Left", lambda: self.rotate_camera(-10.0))
        self._connect_button(self.panel.rotate_right_btn.clicked, "Rotate Right", lambda: self.rotate_camera(10.0))
        self.panel.pitch_slider.valueChanged.connect(self.set_pitch)
        self._connect_button(self.panel.search_point_btn.clicked, "Search by Coordinate", self.search_assets_by_coordinate)
        self._connect_button(self.panel.search_draw_polygon_btn.clicked, "Draw Search Polygon", self.set_search_draw_mode)
        self._connect_button(self.panel.search_finish_polygon_btn.clicked, "Finish Search Polygon", self.finish_search_polygon)
        self._connect_button(self.panel.search_clear_geometry_btn.clicked, "Clear Search Geometry", self.clear_search_geometry)
        self._connect_button(self.panel.search_from_draw_btn.clicked, "Search from Drawn Geometry", self.search_assets_from_drawn_geometry)
        self.panel.search_result_visibility_toggled.connect(self.toggle_search_result_visibility)
        self._connect_button(self.panel.add_annotation_btn.clicked, "Add Annotation", self.add_annotation)
        self._connect_button(self.panel.extract_profile_btn.clicked, "Extract DEM Profile", self.extract_dem_profile)
        self.bridge.mapClicked.connect(self.on_map_click)
        self.bridge.measurementUpdated.connect(self.on_measurement)
        self.bridge.jsLogReceived.connect(self.on_js_log)
        self.bridge.searchGeometryChanged.connect(self.on_search_geometry)
        self.panel.uploaded_assets_list.itemSelectionChanged.connect(self.preview_selected_uploaded_asset)
        self.panel.measurement_result_clear_selected_requested.connect(self.clear_selected_measurement_result)
        self.panel.measurement_result_clear_all_requested.connect(self.clear_all_measurement_results)

    def _connect_button(self, signal, label: str, callback: Callable[..., object]) -> None:
        signal.connect(
            lambda *args, _label=label, _callback=callback: self._on_button_invoked(
                _label,
                _callback,
                *args,
            )
        )

    def _on_button_invoked(self, label: str, callback: Callable[..., object], *args) -> None:
        self._logger.debug("UI button clicked: %s args=%s", label, args)
        try:
            callback(*args)
        except TypeError:
            callback()
        except Exception:  # pragma: no cover - runtime defensive branch
            self.panel.log(f"Action failed: {label}. Check logs for details.")
            self._logger.exception("UI button failed: %s", label)

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
        buffer_meters = float(self.panel.search_buffer_m.value())
        self.panel.set_search_busy(True, "Searching around coordinate...", progress=8)
        try:
            self.panel.set_search_busy(True, "Preparing query...", progress=18)
            if buffer_meters <= 0:
                assets = self.api.search_assets_by_point(lon=lon, lat=lat)
            else:
                polygon_points = self._coordinate_buffer_polygon(lon, lat, buffer_meters)
                assets = self.api.search_assets_by_polygon(points=polygon_points, buffer_meters=0.0)
            self.panel.set_search_busy(True, "Rendering results...", progress=78)
            self._apply_search_results(
                assets,
                label=f"Coordinate search ({lon:.6f}, {lat:.6f}) buffer={int(buffer_meters)}m",
            )
            self.panel.set_search_busy(True, "Finalizing...", progress=97)
        except httpx.HTTPError as exc:
            self._handle_api_error("Coordinate search", exc)
            return
        finally:
            self.panel.set_search_busy(False)

    def search_assets_from_drawn_geometry(self, *, auto_load_overlap: bool = False) -> None:
        if not self._require_offline_endpoints("Drawn geometry search"):
            self.panel.set_search_busy(False)
            return
        geometry_type = self.state.search_geometry_type
        payload = self.state.search_geometry_payload or {}
        if geometry_type is None:
            self.panel.log("Draw a search geometry first.")
            self.panel.set_search_busy(False)
            return

        if geometry_type != "polygon":
            self.panel.log("Only polygon draw search is enabled.")
            self.panel.set_search_busy(False)
            return

        self.panel.set_search_busy(True, "Searching polygon overlap...", progress=12)
        try:
            self.panel.set_search_busy(True, "Preparing polygon query...", progress=24)
            points = [
                (float(item["lon"]), float(item["lat"]))
                for item in payload.get("points", [])
            ]
            self.panel.set_search_busy(True, "Querying catalog...", progress=42)
            assets = self.api.search_assets_by_polygon(
                points=points,
                buffer_meters=float(self.panel.search_buffer_m.value()),
            )
            self.panel.set_search_busy(True, "Rendering results...", progress=80)
            self._apply_search_results(assets, label=f"Drawn {geometry_type} search")
            if auto_load_overlap and assets:
                first_asset = assets[0]
                if isinstance(first_asset, dict):
                    first_path = str(first_asset.get("file_path") or "")
                    self._select_asset_in_combo(first_path)
                    self.panel.log(f"Overlap preview loaded: {first_asset.get('file_name', 'asset')}")
            self.panel.set_search_busy(True, "Finalizing...", progress=97)
        except (KeyError, ValueError, TypeError):
            self.panel.log("Invalid drawn geometry payload.")
            self._logger.exception("Invalid drawn geometry payload=%s", payload)
            return
        except httpx.HTTPError as exc:
            self._handle_api_error("Drawn geometry search", exc)
            return
        finally:
            self.panel.set_search_busy(False)

    def set_search_draw_mode(self) -> None:
        if self._distance_measure_mode_enabled:
            self._distance_measure_mode_enabled = False
            self._run_js_call("setDistanceMeasureMode", False)
        if self._add_point_mode_enabled:
            self._add_point_mode_enabled = False
        if self._shadow_height_mode_enabled:
            self._shadow_height_mode_enabled = False
        self._pan_mode_enabled = False
        self._run_js_call("setSearchDrawMode", "polygon")
        self.panel.log("Polygon draw mode enabled.")

    def finish_search_polygon(self) -> None:
        self._run_js_call("finishSearchPolygon")

    def clear_search_geometry(self) -> None:
        self._run_js_call("clearSearchGeometry")
        self.state.search_geometry_type = None
        self.state.search_geometry_payload = None
        self.panel.log("Search geometry cleared.")

    @staticmethod
    def _coordinate_buffer_polygon(lon: float, lat: float, buffer_meters: float) -> list[tuple[float, float]]:
        lat_offset = buffer_meters / 111_320.0
        lon_scale = max(0.1, math.cos(math.radians(lat)))
        lon_offset = buffer_meters / (111_320.0 * lon_scale)
        return [
            (lon - lon_offset, lat - lat_offset),
            (lon + lon_offset, lat - lat_offset),
            (lon + lon_offset, lat + lat_offset),
            (lon - lon_offset, lat + lat_offset),
        ]

    def on_search_geometry(self, geometry_type: str, payload_json: str) -> None:
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            self._logger.error("Invalid geometry payload JSON: %s", payload_json)
            return
        self.state.search_geometry_type = geometry_type
        self.state.search_geometry_payload = payload
        self.panel.log(f"Search geometry updated: type={geometry_type}")
        if geometry_type == "polygon":
            self._update_coordinate_inputs_from_polygon(payload)
            self.panel.set_search_busy(True, "Polygon ready. Starting overlap search...", progress=6)
            QTimer.singleShot(
                0,
                lambda: self.search_assets_from_drawn_geometry(auto_load_overlap=True),
            )

    def _apply_search_results(self, assets: list[dict], label: str) -> None:
        self.panel.assets_combo.clear()
        self._asset_cache = {}
        previous_assets = self._search_result_assets_by_path
        previously_visible_paths = {
            path for path, is_visible in self._search_layer_visibility.items() if is_visible
        }
        had_visible_assets = bool(previously_visible_paths)
        self._search_result_assets_by_path = {}
        local_missing_count = 0
        for asset in assets:
            if not self._asset_path_accessible_locally(asset):
                local_missing_count += 1
            file_path = str(asset.get("file_path") or "")
            if not file_path:
                continue
            self._asset_cache[file_path] = asset
            self._search_result_assets_by_path[file_path] = asset
            display = f"{asset['file_name']} [{asset['kind']}]"
            self.panel.assets_combo.addItem(display, asset)

        current_paths = set(self._search_result_assets_by_path.keys())
        stale_visible_paths = previously_visible_paths - current_paths
        for stale_path in stale_visible_paths:
            self._run_js_call("setLayerVisibility", stale_path, False)
            self._loaded_search_layer_keys.discard(stale_path)
            stale_asset = previous_assets.get(stale_path)
            if isinstance(stale_asset, dict) and self._is_dem_asset(stale_asset):
                self.state.active_layer_is_dem = False
                self._active_dem_search_layer_key = None
                self.panel.rgb_view_mode_combo.setEnabled(True)
                self.panel.apply_rgb_view_mode_btn.setEnabled(True)

        self._search_layer_visibility = {
            path: bool(self._search_layer_visibility.get(path, True))
            for path in self._search_result_assets_by_path
        }

        self._sync_search_visibility_layers()
        self._focus_visible_search_assets(force=not had_visible_assets)

        self.panel.update_search_results(assets, self._search_layer_visibility)
        self.panel.log(f"{label}: {self.panel.assets_combo.count()} assets")
        if local_missing_count:
            self.panel.log(
                f"Note: {local_missing_count} result(s) are remote-only paths; loading uses server-side tiles."
            )

    def toggle_search_result_visibility(self, file_path: str, visible: bool) -> None:
        normalized_path = str(file_path or "").strip()
        if not normalized_path:
            self.panel.log("Visibility toggle ignored: missing asset path.")
            return

        asset = self._search_result_assets_by_path.get(normalized_path)
        if not isinstance(asset, dict):
            self.panel.log("Visibility toggle ignored: asset is no longer in current search results.")
            return

        next_visible = bool(visible)
        if next_visible and self._is_dem_asset(asset):
            for path, candidate in self._search_result_assets_by_path.items():
                if path != normalized_path and self._is_dem_asset(candidate):
                    self._search_layer_visibility[path] = False

        self._search_layer_visibility[normalized_path] = next_visible
        self._sync_search_visibility_layers()

        if self._search_layer_visibility.get(normalized_path, False):
            self.panel.log(f"Shown on map: {asset.get('file_name', 'asset')}")
        else:
            self.panel.log(f"Hidden from map: {asset.get('file_name', 'asset')}")

        self._focus_visible_search_assets(force=False)
        self.panel.update_search_results(list(self._search_result_assets_by_path.values()), self._search_layer_visibility)

    def _sync_search_visibility_layers(self) -> None:
        for file_path, asset in self._search_result_assets_by_path.items():
            should_show = bool(self._search_layer_visibility.get(file_path, False))
            is_dem_asset = self._is_dem_asset(asset)

            if not should_show:
                self._run_js_call("setLayerVisibility", file_path, False)
                if is_dem_asset and self._active_dem_search_layer_key == file_path:
                    self.state.active_layer_is_dem = False
                    self._active_dem_search_layer_key = None
                    self._apply_display_control_mode()
                continue

            if is_dem_asset and file_path in self._loaded_search_layer_keys:
                self._run_js_call("setLayerVisibility", file_path, True)
                self.state.active_layer_is_dem = True
                self._active_dem_search_layer_key = file_path
                self._apply_display_control_mode()
                continue

            if is_dem_asset and self._active_dem_search_layer_key and self._active_dem_search_layer_key != file_path:
                self._search_layer_visibility[file_path] = False
                self._run_js_call("setLayerVisibility", file_path, False)
                continue

            if is_dem_asset and self._active_dem_search_layer_key == file_path:
                continue

            if (not is_dem_asset) and file_path in self._loaded_search_layer_keys:
                self._run_js_call("setLayerVisibility", file_path, True)
                continue

            loaded = self._load_asset_layer(
                asset,
                replace_existing=False,
                layer_key=file_path,
                auto_fly_to=False,
                apply_scene_mode=False,
                show_loading=False,
            )
            if not loaded:
                self._search_layer_visibility[file_path] = False
                continue

            self._loaded_search_layer_keys.add(file_path)

        self._apply_display_control_mode()

    def _focus_visible_search_assets(self, *, force: bool) -> None:
        visible_assets = [
            asset
            for path, asset in self._search_result_assets_by_path.items()
            if self._search_layer_visibility.get(path, False)
        ]
        if not visible_assets:
            self._last_visible_focus_signature = None
            return

        union_bounds: dict[str, float] | None = None
        for asset in visible_assets:
            bounds = self._asset_bounds(asset)
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
            if not force and self._last_visible_focus_signature == signature:
                return
            self._last_visible_focus_signature = signature
            self._run_js_call(
                "focusBounds",
                union_bounds["west"],
                union_bounds["south"],
                union_bounds["east"],
                union_bounds["north"],
            )
            return

        self._fly_to_asset(visible_assets[0])

    def _update_coordinate_inputs_from_polygon(self, payload: dict) -> None:
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
        self.panel.search_coord_lon.setValue(center_lon)
        self.panel.search_coord_lat.setValue(center_lat)

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

    def _load_asset_layer(
        self,
        asset: dict,
        *,
        replace_existing: bool = True,
        layer_key: str | None = None,
        auto_fly_to: bool = True,
        apply_scene_mode: bool = True,
        show_loading: bool = True,
    ) -> dict | None:
        if show_loading:
            self._set_layer_loading(True, f"Loading {asset['file_name']}...")
        if self.app_mode != DesktopAppMode.CLIENT and not Path(asset["file_path"]).exists():
            self.panel.log(f"File not found on disk: {asset['file_path']}")
            self._logger.error("Cannot add layer; file missing path=%s", asset["file_path"])
            if show_loading:
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
        options["replace_existing"] = bool(replace_existing)
        if layer_key:
            options["layer_key"] = layer_key
        options["apply_scene_mode"] = bool(apply_scene_mode)
        if self._add_layer(asset, options):
            if auto_fly_to:
                self._fly_through_asset(asset)
        else:
            if show_loading:
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
            self._apply_display_control_mode()
            return

        self._run_js_call("setSceneMode", mode)
        self._apply_display_control_mode()
        mode_label = "2D map" if mode == "2d" else "3D terrain"
        self.panel.log(f"RGB view mode applied: {mode_label}")

    def _on_visual_slider_changed(self, _value: int) -> None:
        self.apply_visual_settings(log_to_panel=False)

    def _on_dem_slider_changed(self, _value: int) -> None:
        self.apply_dem_settings(log_to_panel=False)

    def _on_dem_color_mode_changed(self, _index: int) -> None:
        self.apply_dem_color_mode(log_to_panel=False)

    def apply_visual_settings(self, log_to_panel: bool = True) -> None:
        brightness = self.panel.brightness_slider.value() / 100.0
        contrast = self.panel.contrast_slider.value() / 100.0
        self._run_js_call("setImageryProperties", brightness, contrast)
        if log_to_panel:
            self.panel.log(f"Applied imagery settings brightness={brightness:.2f}, contrast={contrast:.2f}")
            self._logger.info("Applied imagery settings brightness=%.2f contrast=%.2f", brightness, contrast)
            return
        self._logger.debug("Live imagery settings brightness=%.2f contrast=%.2f", brightness, contrast)

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
            return
        self._logger.debug(
            "Live DEM settings exaggeration=%.2f hillshade=%.2f azimuth=%s altitude=%s",
            exaggeration,
            hillshade_strength,
            azimuth,
            altitude,
        )

    def apply_dem_color_mode(self, log_to_panel: bool = True) -> None:
        color_mode = str(self.panel.dem_color_mode_combo.currentData() or "gray")
        self._run_js_call("setDemColorMode", color_mode)
        if log_to_panel:
            label = "White relief" if color_mode == "gray" else "Color relief"
            self.panel.log(f"Applied DEM style: {label}")
            self._logger.info("Applied DEM style=%s", color_mode)
            return
        self._logger.debug("Live DEM style=%s", color_mode)

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

        if self._add_point_mode_enabled:
            self._add_annotation_at(lon, lat)
            return

        if self._shadow_height_mode_enabled:
            if len(self.state.clicked_points) < 2:
                self.panel.log("Shadow Height: base point captured. Click shadow tip point.")
                return
            self._toolbar_measure_shadow_height()
            self.state.clicked_points.clear()

    def on_measurement(self, meters: float) -> None:
        self.panel.measure_label.setText(f"Last distance: {meters:.2f} m")
        self._logger.info("Measurement updated distance_m=%.2f", meters)
        if not self._distance_measure_mode_enabled:
            return
        if len(self.state.clicked_points) < 2:
            self._logger.debug("Skipping distance measurement job: insufficient clicked points")
            return
        (lon1, lat1), (lon2, lat2) = self.state.clicked_points[-2], self.state.clicked_points[-1]
        signature = (round(lon1, 7), round(lat1, 7), round(lon2, 7), round(lat2, 7), round(meters, 2))
        if signature == self._last_distance_measurement_signature:
            self._logger.debug("Skipping duplicate distance measurement event signature=%s", signature)
            return
        self._last_distance_measurement_signature = signature
        self._enqueue_distance_measurement(lon1, lat1, lon2, lat2)

    def add_annotation(self) -> None:
        if not self.state.clicked_points:
            self.panel.log("Click on the globe first to place annotation.")
            self._logger.warning("Annotation requested without click")
            return
        lon, lat = self.state.clicked_points[-1]
        self._add_annotation_at(lon, lat)

    def _add_annotation_at(self, lon: float, lat: float) -> None:
        text = self.panel.annotation_edit.text().strip()
        if not text:
            text = "Point"
            self.panel.annotation_edit.setText(text)
            self.panel.log("Annotation text was empty. Using default label 'Point'.")
            self._logger.info("Annotation text missing; using default label '%s'", text)
        self._run_js_call("addAnnotation", text, lon, lat)
        self._annotation_records.append(
            {
                "type": "point",
                "lon": lon,
                "lat": lat,
                "text": text,
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        )
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
        self._last_profile_values = [float(v) for v in values]
        preview = ", ".join(f"{v:.2f}" for v in values[:10])
        self.panel.log(f"Profile extracted ({len(values)} samples). First values: {preview}")
        self._logger.info("Profile extracted samples=%s path=%s", len(values), asset["file_path"])

    def on_toolbar_group_disabled(self, group_name: str) -> None:
        if group_name == "measurement":
            self._distance_measure_mode_enabled = False
            self._add_point_mode_enabled = False
            self._shadow_height_mode_enabled = False
            self._pan_mode_enabled = True
            self._run_js_call("setDistanceMeasureMode", False)
            self._run_js_call("setSearchDrawMode", "none")
            self._run_js_call("setPanMode", True)
            self._run_js_call("clearMeasurements")
            self.clear_all_measurement_results()
            self.panel.log("Measurement toolbar disabled: measurement overlays cleared.")
            return
        if group_name == "visualization":
            if self._swipe_comparator_enabled:
                self._swipe_comparator_enabled = False
                self._run_js_call("setSwipeComparator", False)
            self.panel.log("Visualization toolbar disabled.")

    def handle_toolbar_action(self, action_label: str, checked: bool | None = None) -> bool | None:
        handlers: dict[str, Callable[[], None]] = {
            "Layer Compositor": self._toolbar_apply_layer_compositor,
            "Hillshade": self._toolbar_apply_hillshade,
            "Colour Relief": self._toolbar_set_color_relief,
            "Swipe Comparator": self._toolbar_toggle_swipe_comparator,
            "Distance / Azimuth": self._toolbar_measure_distance,
            "Polygon Area": self._toolbar_measure_polygon_area,
            "Elevation Profile": self.extract_dem_profile,
            "Volume Cut/Fill": self._toolbar_measure_volume,
            "Viewshed / LOS": self._toolbar_measure_viewshed,
            "Slope & Aspect": self._toolbar_measure_slope_aspect,
            "Clear Last": self._toolbar_clear_last,
            "Clear All": self._toolbar_clear_all,
            "Add Point": self._toolbar_toggle_add_point_mode,
            "Add Polygon": self._toolbar_add_polygon_annotation,
            "Shadow Height": self._toolbar_toggle_shadow_height_mode,
            "Save Annotations": self._toolbar_export_geopackage,
            "Pan": self._toolbar_set_pan_mode,
            "Zoom In": lambda: self._run_js_call("zoomIn"),
            "Zoom Out": lambda: self._run_js_call("zoomOut"),
            "Zoom to Extent": lambda: self._run_js_call("zoomToExtent"),
            "North Arrow": lambda: self._run_js_call("resetNorthUp"),
            "Open Raster": self.browse_path,
            "Open DEM": self.browse_path,
            "Save Project": self._toolbar_save_project,
            "Export GeoPackage": self._toolbar_export_geopackage,
            "Export Profile CSV": self._toolbar_export_profile_csv,
        }
        handler = handlers.get(action_label)
        if handler is None:
            self.panel.log(f"Toolbar action not mapped: {action_label}")
            self._logger.warning("Toolbar action not mapped: %s", action_label)
            return None
        self.panel.log(f"Toolbar action: {action_label}")
        self._logger.info("Toolbar action triggered: %s", action_label)
        try:
            if action_label == "Hillshade":
                return self._toolbar_apply_hillshade(enabled=checked)
            if action_label == "Swipe Comparator":
                return self._toolbar_toggle_swipe_comparator(enabled=checked)
            if action_label == "Distance / Azimuth":
                return self._toolbar_measure_distance(enabled=checked)
            if action_label == "Pan":
                return self._toolbar_set_pan_mode(enabled=checked)
            if action_label == "Add Point":
                return self._toolbar_toggle_add_point_mode(enabled=checked)
            if action_label == "Add Polygon":
                return self._toolbar_add_polygon_annotation(enabled=checked)
            if action_label == "Shadow Height":
                return self._toolbar_toggle_shadow_height_mode(enabled=checked)
            handler()
        except Exception:  # pragma: no cover - runtime defensive branch
            self.panel.log(f"Toolbar action failed: {action_label}")
            self._logger.exception("Toolbar action failed: %s", action_label)
        return None

    def available_swipe_layer_options(self) -> list[dict[str, object]]:
        options: list[dict[str, object]] = []
        for path, asset in self._search_result_assets_by_path.items():
            label = str(asset.get("file_name") or Path(path).name or "Layer")
            kind = str(asset.get("kind") or "")
            if kind:
                label = f"{label} [{kind}]"
            options.append(
                {
                    "path": path,
                    "label": label,
                    "visible": bool(self._search_layer_visibility.get(path, False)),
                }
            )
        return options

    def apply_swipe_comparator_selection(self, selected_paths: list[str]) -> bool:
        selected = [path for path in selected_paths if path in self._search_result_assets_by_path]
        if len(selected) < 2:
            self._swipe_comparator_enabled = False
            self._run_js_call("setSwipeComparator", False)
            self.panel.log("Swipe comparator disabled. Select at least two layers.")
            return False

        left_path = selected[0]
        right_path = selected[1]
        left_asset = self._search_result_assets_by_path.get(left_path) or {}
        right_asset = self._search_result_assets_by_path.get(right_path) or {}
        left_label = str(left_asset.get("file_name") or Path(left_path).name or "Layer A")
        right_label = str(right_asset.get("file_name") or Path(right_path).name or "Layer B")
        self._run_js_call("setSwipeComparatorLayers", left_path, right_path, left_label, right_label)

        selected_set = set(selected)
        for path in self._search_result_assets_by_path:
            self._search_layer_visibility[path] = path in selected_set

        self._sync_search_visibility_layers()
        self.panel.update_search_results(list(self._search_result_assets_by_path.values()), self._search_layer_visibility)
        return self._toolbar_toggle_swipe_comparator(enabled=True)

    def get_dem_color_mode(self) -> str:
        return str(self.panel.dem_color_mode_combo.currentData() or "gray")

    def set_dem_color_mode(self, mode: str, *, log_to_panel: bool = True) -> bool:
        if mode not in {"gray", "terrain"}:
            mode = "gray"
        if not self._selected_dem_path():
            if log_to_panel:
                self.panel.log("Colour relief requires a visible DEM layer.")
            self._logger.warning("DEM color mode set requested without visible DEM")
            return False

        combo_index = self.panel.dem_color_mode_combo.findData(mode)
        if combo_index >= 0 and self.panel.dem_color_mode_combo.currentIndex() != combo_index:
            self.panel.dem_color_mode_combo.setCurrentIndex(combo_index)
        self.apply_dem_color_mode(log_to_panel=log_to_panel)
        return True

    def _visible_imagery_layer_paths(self) -> list[str]:
        visible_layers: list[str] = []
        for path, asset in self._search_result_assets_by_path.items():
            if not self._search_layer_visibility.get(path, False):
                continue
            if self._is_dem_asset(asset):
                continue
            visible_layers.append(path)
        if self._explicit_imagery_layer_visible:
            selected = self._selected_asset()
            if isinstance(selected, dict) and not self._is_dem_asset(selected):
                selected_path = str(selected.get("file_path") or "")
                if selected_path and selected_path not in visible_layers:
                    visible_layers.append(selected_path)
        return visible_layers

    def _available_imagery_layer_paths(self) -> list[str]:
        available_paths: list[str] = []
        for path, asset in self._search_result_assets_by_path.items():
            if self._is_dem_asset(asset):
                continue
            available_paths.append(path)
        if self._explicit_imagery_layer_visible:
            selected = self._selected_asset()
            if isinstance(selected, dict) and not self._is_dem_asset(selected):
                selected_path = str(selected.get("file_path") or "")
                if selected_path and selected_path not in available_paths:
                    available_paths.append(selected_path)
        return available_paths

    def _visible_dem_layer_count(self) -> int:
        has_visible_search_dem = any(
            self._search_layer_visibility.get(path, False) and self._is_dem_asset(asset)
            for path, asset in self._search_result_assets_by_path.items()
        )
        if has_visible_search_dem or self._explicit_dem_layer_visible:
            return 1
        return 0

    def swipe_comparator_candidate_count(self) -> int:
        return len(self._visible_imagery_layer_paths()) + self._visible_dem_layer_count()

    def can_enable_swipe_comparator(self) -> bool:
        return self.swipe_comparator_candidate_count() >= 2

    def can_attempt_enable_swipe_comparator(self) -> bool:
        if self.can_enable_swipe_comparator():
            return True
        return len(self._available_imagery_layer_paths()) >= 2

    def _auto_enable_second_swipe_imagery_layer(self) -> bool:
        visible_imagery = self._visible_imagery_layer_paths()
        if len(visible_imagery) >= 2:
            return True

        available_imagery = self._available_imagery_layer_paths()
        if len(available_imagery) < 2:
            return False

        changed = False
        visible_set = set(visible_imagery)
        for path in available_imagery:
            if path in visible_set:
                continue
            if path not in self._search_result_assets_by_path:
                continue
            self._search_layer_visibility[path] = True
            visible_set.add(path)
            changed = True
            if len(visible_set) >= 2:
                break

        if changed:
            self._sync_search_visibility_layers()
            self.panel.update_search_results(list(self._search_result_assets_by_path.values()), self._search_layer_visibility)
            self.panel.log("Swipe comparator: enabled an additional visible raster layer for comparison.")

        return self.can_enable_swipe_comparator()

    def _enqueue_distance_measurement(self, lon1: float, lat1: float, lon2: float, lat2: float) -> None:
        dem_path = self._selected_dem_path()

        distance_info = measure_distance(lon1, lat1, lon2, lat2, dem_path=None)
        self._annotation_line_records.append(
            {
                "coords": [(lon1, lat1), (lon2, lat2)],
                "feature_type": "road",
                "length_m": float(distance_info.distance_m),
                "width_m": 0.0,
                "condition": "intact",
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        )

        def task() -> object:
            return measure_distance(lon1, lat1, lon2, lat2, dem_path=dem_path)

        def formatter(result: object) -> str:
            d = result
            return (
                "Distance/Azimuth: "
                f"2D={d.distance_m:.3f} m, az_fwd={d.azimuth_fwd_deg:.2f} deg, az_back={d.azimuth_back_deg:.2f} deg"
                + (f", dz={d.dz_m:+.3f} m, 3D={d.distance_3d_m:.3f} m" if d.distance_3d_m is not None else "")
            )

        self._submit_measurement_job("Distance/Azimuth", task, formatter)

    def _submit_measurement_job(self, name: str, task: Callable[[], object], formatter: Callable[[object], str]) -> None:
        worker = _MeasurementWorker(name=name, task=task)
        worker.signals.finished.connect(
            lambda job_name, result, error, fmt=formatter: self._on_measurement_job_finished(job_name, result, error, fmt)
        )
        self._measurement_pool.start(worker)
        self.panel.log(f"{name} started...")

    def _on_measurement_job_finished(
        self,
        name: str,
        result: object,
        error: str,
        formatter: Callable[[object], str],
    ) -> None:
        if error:
            self.panel.log(f"{name} failed: {error}")
            self._logger.error("Measurement job failed name=%s error=%s", name, error)
            return
        message = formatter(result)
        self.panel.log(message)
        self._record_measurement_result(name, message)

    def _record_measurement_result(self, name: str, details: str) -> None:
        timestamp = dt.datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {name}: {details}"
        self._measurement_history.append(entry)
        self.panel.add_measurement_result_entry(entry)

    def clear_selected_measurement_result(self) -> None:
        row = self.panel.selected_measurement_result_row()
        if row < 0 or row >= len(self._measurement_history):
            return
        self._measurement_history.pop(row)
        self.panel.remove_measurement_result_row(row)

    def clear_all_measurement_results(self) -> None:
        self._measurement_history.clear()
        self.panel.clear_measurement_result_entries()

    def _selected_dem_path(self) -> str | None:
        selected = self._selected_asset()
        if selected and self._is_dem_asset(selected):
            return str(selected.get("file_path") or "") or None
        if self._active_dem_search_layer_key:
            asset = self._search_result_assets_by_path.get(self._active_dem_search_layer_key)
            if isinstance(asset, dict):
                return str(asset.get("file_path") or "") or None
        for path, asset in self._search_result_assets_by_path.items():
            if self._search_layer_visibility.get(path, False) and self._is_dem_asset(asset):
                return str(asset.get("file_path") or "") or None
        return None

    def _current_polygon_lonlat(self) -> list[tuple[float, float]] | None:
        payload = self.state.search_geometry_payload or {}
        points = payload.get("points")
        if not isinstance(points, list) or len(points) < 3:
            return None
        out: list[tuple[float, float]] = []
        for point in points:
            if not isinstance(point, dict):
                continue
            lon = point.get("lon")
            lat = point.get("lat")
            if isinstance(lon, (int, float)) and isinstance(lat, (int, float)):
                out.append((float(lon), float(lat)))
        return out if len(out) >= 3 else None

    def _toolbar_set_color_relief(self) -> None:
        current_mode = self.get_dem_color_mode()
        target_mode = "terrain" if current_mode == "gray" else "gray"
        self.set_dem_color_mode(target_mode, log_to_panel=True)
        self._logger.info("Colour relief toggled mode=%s", target_mode)

    def _toolbar_toggle_swipe_comparator(self, enabled: bool | None = None) -> bool:
        candidate_count = self.swipe_comparator_candidate_count()
        next_state = (not self._swipe_comparator_enabled) if enabled is None else bool(enabled)

        if next_state and candidate_count < 2:
            if self._auto_enable_second_swipe_imagery_layer():
                candidate_count = self.swipe_comparator_candidate_count()

        if next_state and candidate_count < 2:
            self.panel.log("Swipe comparator needs at least two visible raster layers.")
            self._swipe_comparator_enabled = False
            return False

        self._swipe_comparator_enabled = next_state
        self._run_js_call("setSwipeComparator", self._swipe_comparator_enabled)
        if self._swipe_comparator_enabled:
            self._run_js_call("setSwipePosition", 0.5)
            self.panel.log("Swipe comparator enabled. Drag divider on map to compare georeferenced layers.")
            self._logger.info("Swipe comparator enabled candidate_layers=%s", candidate_count)
            return True
        self.panel.log("Swipe comparator disabled.")
        self._logger.info("Swipe comparator disabled")
        return False

    def _toolbar_apply_layer_compositor(self) -> None:
        self.apply_visual_settings(log_to_panel=True)
        self.panel.log("Layer compositor updated from current brightness/contrast controls.")

    def _toolbar_apply_hillshade(self, enabled: bool | None = None) -> bool:
        if not self._selected_dem_path():
            self.panel.log("Hillshade requires a visible DEM layer.")
            self._logger.warning("Hillshade requested without visible DEM")
            self._hillshade_enabled = False
            return False

        next_state = (not self._hillshade_enabled) if enabled is None else bool(enabled)
        current_slider = int(self.panel.dem_hillshade_slider.value())
        if next_state:
            target_value = current_slider if current_slider > 0 else self._last_hillshade_strength_percent
            target_value = max(10, target_value)
            self._last_hillshade_strength_percent = target_value
            if current_slider != target_value:
                self.panel.dem_hillshade_slider.setValue(target_value)
            self.apply_dem_settings(log_to_panel=True)
            self.panel.log("Hillshade enabled.")
            self._hillshade_enabled = True
            return True

        if current_slider > 0:
            self._last_hillshade_strength_percent = current_slider
        if current_slider != 0:
            self.panel.dem_hillshade_slider.setValue(0)
        self.apply_dem_settings(log_to_panel=True)
        self.panel.log("Hillshade disabled.")
        self._hillshade_enabled = False
        return False

    def _toolbar_measure_distance(self, enabled: bool | None = None) -> bool:
        self._distance_measure_mode_enabled = (not self._distance_measure_mode_enabled) if enabled is None else bool(enabled)
        if self._distance_measure_mode_enabled:
            self._add_point_mode_enabled = False
            self._shadow_height_mode_enabled = False
        self._pan_mode_enabled = not self._distance_measure_mode_enabled
        self._last_distance_measurement_signature = None
        if self._distance_measure_mode_enabled:
            self._run_js_call("setSearchDrawMode", "none")
        self._run_js_call("setDistanceMeasureMode", self._distance_measure_mode_enabled)
        if not self._distance_measure_mode_enabled:
            self.panel.log("Distance tool disabled.")
            self._logger.info("Distance measure mode disabled")
            return False
        self.state.clicked_points.clear()
        self._run_js_call("clearMeasurements")
        self.panel.log(
            "Distance tool enabled. Click first point, move cursor to preview, click second point to measure. "
            "Right-click to stop drawing."
        )
        self._logger.info("Distance measure mode enabled")
        return True

    def _toolbar_set_pan_mode(self, enabled: bool | None = None) -> bool:
        next_state = (not self._pan_mode_enabled) if enabled is None else bool(enabled)
        self._pan_mode_enabled = next_state
        if next_state:
            if self._distance_measure_mode_enabled:
                self._distance_measure_mode_enabled = False
                self._run_js_call("setDistanceMeasureMode", False)
            if self._add_point_mode_enabled:
                self._add_point_mode_enabled = False
            if self._shadow_height_mode_enabled:
                self._shadow_height_mode_enabled = False
            self._run_js_call("setSearchDrawMode", "none")
            self._run_js_call("setPanMode", True)
            self.panel.log("Pan mode enabled.")
            self._logger.info("Pan mode enabled")
            return True
        self._run_js_call("setPanMode", False)
        self.panel.log("Pan mode disabled.")
        self._logger.info("Pan mode disabled")
        return False

    def _toolbar_measure_polygon_area(self) -> None:
        polygon = self._current_polygon_lonlat()
        if not polygon:
            self.panel.log("Draw a polygon first, then run Polygon Area.")
            return
        area_m2, perimeter_m, _orientation = self._polygon_metrics_for_export(polygon)
        compactness = (4.0 * math.pi * area_m2) / (perimeter_m * perimeter_m) if perimeter_m > 0.0 else 0.0
        message = (
            "Polygon Area: "
            f"planimetric={area_m2:.2f} m2, perimeter={perimeter_m:.2f} m, compactness={compactness:.4f}"
        )
        self.panel.log(message)
        self._record_measurement_result("Polygon Area", message)
        self._logger.info(
            "Polygon area measured area_m2=%.3f perimeter_m=%.3f compactness=%.6f",
            area_m2,
            perimeter_m,
            compactness,
        )

    def _toolbar_measure_volume(self) -> None:
        polygon = self._current_polygon_lonlat()
        if not polygon:
            self.panel.log("Draw a polygon first, then run Volume Cut/Fill.")
            return
        dem_path = self._selected_dem_path()
        if not dem_path:
            self.panel.log("Select or show a DEM layer first.")
            return

        def task() -> object:
            return compute_volume(polygon, dem_path)

        def formatter(result: object) -> str:
            m = result
            return (
                "Volume Cut/Fill: "
                f"cut={m.cut_volume_m3:.3f} m3, fill={m.fill_volume_m3:.3f} m3, net={m.net_volume_m3:+.3f} m3, "
                f"ref={m.reference_elevation_m:.3f} m, void={100.0 * m.void_fraction:.1f}%"
            )

        self._submit_measurement_job("Volume Cut/Fill", task, formatter)

    def _toolbar_measure_slope_aspect(self) -> None:
        polygon = self._current_polygon_lonlat()
        if not polygon:
            self.panel.log("Draw a polygon first, then run Slope & Aspect.")
            return
        dem_path = self._selected_dem_path()
        if not dem_path:
            self.panel.log("Select or show a DEM layer first.")
            return

        def task() -> object:
            return compute_slope_aspect(polygon, dem_path)

        def formatter(result: object) -> str:
            m = result
            area_txt = ", ".join(f"{k}:{v:.1f}m2" for k, v in m.area_by_class_m2.items())
            return (
                "Slope & Aspect: "
                f"mean={m.mean_slope_deg:.2f} deg, std={m.std_slope_deg:.2f} deg, max={m.max_slope_deg:.2f} deg; "
                f"classes[{area_txt}]"
            )

        self._submit_measurement_job("Slope & Aspect", task, formatter)

    def _toolbar_measure_viewshed(self) -> None:
        if not self.state.clicked_points:
            self.panel.log("Click observer point on map first, then run Viewshed / LOS.")
            return
        dem_path = self._selected_dem_path()
        if not dem_path:
            self.panel.log("Select or show a DEM layer first.")
            return
        lon, lat = self.state.clicked_points[-1]

        def task() -> object:
            return compute_viewshed(lon, lat, dem_path, max_radius_m=400.0)

        def formatter(result: object) -> str:
            m = result
            return (
                "Viewshed/LOS: "
                f"visible={m.visible_area_m2:.1f} m2 / {m.total_area_m2:.1f} m2 "
                f"({100.0 * m.visible_fraction:.1f}%), max_dist={m.max_visible_distance_m:.1f} m"
            )

        self._submit_measurement_job("Viewshed / LOS", task, formatter)

    def _toolbar_measure_shadow_height(self) -> None:
        if len(self.state.clicked_points) < 2:
            self.panel.log("Click object base and shadow tip points before Shadow Height.")
            return
        dem_path = self._selected_dem_path()
        (base_lon, base_lat), (tip_lon, tip_lat) = self.state.clicked_points[-2], self.state.clicked_points[-1]
        acquired = dt.datetime.now(dt.timezone.utc)

        def task() -> object:
            return measure_shadow_height(
                base_lon,
                base_lat,
                tip_lon,
                tip_lat,
                acquisition_datetime_utc=acquired,
                dem_path=dem_path,
                imagery_resolution_m=0.05,
            )

        def formatter(result: object) -> str:
            m = result
            h = m.corrected_height_m if m.corrected_height_m is not None else m.estimated_height_m
            warn = f" warning={m.warning}" if m.warning else ""
            return (
                "Shadow Height: "
                f"height={h:.2f} m +/- {m.uncertainty_m:.2f} m, sun_elev={m.solar_elevation_deg:.2f} deg, "
                f"sun_az={m.solar_azimuth_deg:.2f} deg, reliable={m.reliable}{warn}"
            )

        self._submit_measurement_job("Shadow Height", task, formatter)

    def _toolbar_toggle_shadow_height_mode(self, enabled: bool | None = None) -> bool:
        next_state = (not self._shadow_height_mode_enabled) if enabled is None else bool(enabled)
        self._shadow_height_mode_enabled = next_state
        if not next_state:
            self.panel.log("Shadow Height tool disabled.")
            return False

        self._distance_measure_mode_enabled = False
        self._add_point_mode_enabled = False
        self._pan_mode_enabled = False
        self.state.clicked_points.clear()
        self._run_js_call("setDistanceMeasureMode", False)
        self._run_js_call("setSearchDrawMode", "none")
        self._run_js_call("setPanMode", False)
        self.panel.log("Shadow Height enabled. Click base point, then shadow tip point.")
        return True

    def _toolbar_toggle_add_point_mode(self, enabled: bool | None = None) -> bool:
        next_state = (not self._add_point_mode_enabled) if enabled is None else bool(enabled)
        self._add_point_mode_enabled = next_state
        if not next_state:
            self.panel.log("Add Point tool disabled.")
            return False

        self._distance_measure_mode_enabled = False
        self._shadow_height_mode_enabled = False
        self._pan_mode_enabled = False
        self._run_js_call("setDistanceMeasureMode", False)
        self._run_js_call("setSearchDrawMode", "none")
        self._run_js_call("setPanMode", False)
        self.panel.log("Add Point enabled. Click map to place annotation points.")
        return True

    def _toolbar_clear_last(self) -> None:
        if self.state.clicked_points:
            self.state.clicked_points = self.state.clicked_points[:-1]
        self._run_js_call("clearMeasurements")
        self.panel.log("Cleared last measurement click.")

    def _toolbar_clear_all(self) -> None:
        self.state.clicked_points.clear()
        self.state.search_geometry_type = None
        self.state.search_geometry_payload = None
        self._distance_measure_mode_enabled = False
        self._add_point_mode_enabled = False
        self._shadow_height_mode_enabled = False
        self._pan_mode_enabled = True
        self._run_js_call("clearOverlays")
        self._run_js_call("setDistanceMeasureMode", False)
        self._run_js_call("setSearchDrawMode", "none")
        self._run_js_call("setPanMode", True)
        self._measurement_history.clear()
        self.panel.clear_measurement_result_entries()
        self.panel.log("Cleared all temporary measurements and overlays.")

    @staticmethod
    def _utm_epsg_for_lon_lat(lon: float, lat: float) -> int:
        zone = int((lon + 180.0) // 6.0) + 1
        return 32600 + zone if lat >= 0 else 32700 + zone

    def _polygon_metrics_for_export(self, polygon_points: list[tuple[float, float]]) -> tuple[float, float, float]:
        if not polygon_points:
            return 0.0, 0.0, 0.0
        if polygon_points[0] != polygon_points[-1]:
            polygon_points = polygon_points + [polygon_points[0]]
        lon_c = sum(p[0] for p in polygon_points) / len(polygon_points)
        lat_c = sum(p[1] for p in polygon_points) / len(polygon_points)
        epsg = self._utm_epsg_for_lon_lat(lon_c, lat_c)
        transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
        projected = [transformer.transform(lon, lat) for lon, lat in polygon_points]

        area = 0.0
        for i in range(len(projected) - 1):
            area += (projected[i][0] * projected[i + 1][1]) - (projected[i + 1][0] * projected[i][1])
        area = abs(area) * 0.5

        perimeter = 0.0
        for i in range(len(polygon_points) - 1):
            d = measure_distance(
                polygon_points[i][0],
                polygon_points[i][1],
                polygon_points[i + 1][0],
                polygon_points[i + 1][1],
                dem_path=None,
            )
            perimeter += d.distance_m

        orientation = 0.0
        longest_len = -1.0
        for i in range(len(projected) - 1):
            dx = projected[i + 1][0] - projected[i][0]
            dy = projected[i + 1][1] - projected[i][1]
            edge_len = math.sqrt(dx * dx + dy * dy)
            if edge_len <= longest_len:
                continue
            longest_len = edge_len
            orientation = (math.degrees(math.atan2(dx, dy))) % 180.0
        return float(area), float(perimeter), float(orientation)

    def _toolbar_add_polygon_annotation(self, enabled: bool | None = None) -> bool:
        if enabled is False:
            self.clear_search_geometry()
            self.panel.log("Polygon draw disabled.")
            return False

        polygon = self._current_polygon_lonlat()
        if not polygon:
            self._distance_measure_mode_enabled = False
            self._add_point_mode_enabled = False
            self._shadow_height_mode_enabled = False
            self._pan_mode_enabled = False
            self._run_js_call("setDistanceMeasureMode", False)
            self.set_search_draw_mode()
            self.panel.log("Polygon draw enabled. Finish polygon, then tap Add Polygon again to save annotation.")
            return True
        area, perimeter, orientation = self._polygon_metrics_for_export(polygon)
        self._annotation_polygon_records.append(
            {
                "coords": polygon,
                "feature_type": "building",
                "condition": "intact",
                "area_m2": area,
                "perimeter_m": perimeter,
                "orientation_deg": orientation,
                "notes": "",
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        )
        self.panel.log(
            "Polygon annotation saved: "
            f"area={area:.2f} m2, perimeter={perimeter:.2f} m, orientation={orientation:.1f} deg"
        )
        self.clear_search_geometry()
        return False

    def _toolbar_export_profile_csv(self) -> None:
        if not self._last_profile_values:
            self.panel.log("No profile values available. Run Elevation Profile first.")
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self.panel,
            "Export Profile CSV",
            "profile_export.csv",
            "CSV Files (*.csv)",
        )
        if not file_path:
            return
        output_path = Path(file_path)
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["index", "elevation_m"])
            for idx, value in enumerate(self._last_profile_values):
                writer.writerow([idx, f"{value:.6f}"])
        self.panel.log(f"Profile CSV exported: {output_path}")

    def _toolbar_export_annotations_geojson(self) -> None:
        if not self._annotation_records and not self._annotation_line_records and not self._annotation_polygon_records:
            self.panel.log("No annotations captured yet.")
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self.panel,
            "Export Annotation GeoJSON",
            "annotations.geojson",
            "GeoJSON (*.geojson)",
        )
        if not file_path:
            return
        features = []
        for item in self._annotation_records:
            lon = float(item.get("lon") or 0.0)
            lat = float(item.get("lat") or 0.0)
            properties = {
                "type": item.get("type", "point"),
                "text": item.get("text", ""),
                "created_at": item.get("created_at", ""),
            }
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": properties,
                }
            )
        for item in self._annotation_line_records:
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": item.get("coords", [])},
                    "properties": {
                        "feature_type": item.get("feature_type", "road"),
                        "length_m": item.get("length_m", 0.0),
                        "width_m": item.get("width_m", 0.0),
                        "condition": item.get("condition", "intact"),
                        "created_at": item.get("created_at", ""),
                    },
                }
            )
        for item in self._annotation_polygon_records:
            ring = item.get("coords", [])
            if ring and ring[0] != ring[-1]:
                ring = list(ring) + [ring[0]]
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [ring]},
                    "properties": {
                        "feature_type": item.get("feature_type", "building"),
                        "condition": item.get("condition", "intact"),
                        "area_m2": item.get("area_m2", 0.0),
                        "perimeter_m": item.get("perimeter_m", 0.0),
                        "orientation_deg": item.get("orientation_deg", 0.0),
                        "notes": item.get("notes", ""),
                        "created_at": item.get("created_at", ""),
                    },
                }
            )
        payload = {"type": "FeatureCollection", "features": features}
        Path(file_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.panel.log(f"Annotation export complete: {file_path}")

    def _toolbar_export_geopackage(self) -> None:
        if not self._annotation_records and not self._annotation_line_records and not self._annotation_polygon_records:
            self.panel.log("No annotations captured yet.")
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self.panel,
            "Export Annotation GeoPackage",
            "annotations.gpkg",
            "GeoPackage (*.gpkg)",
        )
        if not file_path:
            return

        try:
            import fiona
            from fiona.crs import CRS as FionaCRS
        except Exception:
            self.panel.log("Fiona is unavailable. Falling back to GeoJSON export.")
            self._toolbar_export_annotations_geojson()
            return

        point_schema = {
            "geometry": "Point",
            "properties": {
                "category": "str",
                "confidence": "str",
                "height_m": "float",
                "created_at": "str",
                "notes": "str",
                "class_level": "str",
            },
        }
        with fiona.open(
            file_path,
            "w",
            driver="GPKG",
            layer="annotations_point",
            crs=FionaCRS.from_epsg(4326),
            schema=point_schema,
        ) as sink:
            for item in self._annotation_records:
                lon = float(item.get("lon") or 0.0)
                lat = float(item.get("lat") or 0.0)
                sink.write(
                    {
                        "geometry": {"type": "Point", "coordinates": (lon, lat)},
                        "properties": {
                            "category": "other",
                            "confidence": "possible",
                            "height_m": -9999.0,
                            "created_at": str(item.get("created_at") or ""),
                            "notes": str(item.get("text") or ""),
                            "class_level": "UNCLASS",
                        },
                    }
                )

        line_schema = {
            "geometry": "LineString",
            "properties": {
                "feature_type": "str",
                "length_m": "float",
                "width_m": "float",
                "condition": "str",
            },
        }
        with fiona.open(
            file_path,
            "a",
            driver="GPKG",
            layer="annotations_line",
            crs=FionaCRS.from_epsg(4326),
            schema=line_schema,
        ) as sink:
            for item in self._annotation_line_records:
                sink.write(
                    {
                        "geometry": {"type": "LineString", "coordinates": item.get("coords", [])},
                        "properties": {
                            "feature_type": str(item.get("feature_type") or "road"),
                            "length_m": float(item.get("length_m") or 0.0),
                            "width_m": float(item.get("width_m") or 0.0),
                            "condition": str(item.get("condition") or "intact"),
                        },
                    }
                )

        polygon_schema = {
            "geometry": "Polygon",
            "properties": {
                "feature_type": "str",
                "condition": "str",
                "area_m2": "float",
                "perimeter_m": "float",
                "orientation_deg": "float",
                "notes": "str",
            },
        }
        with fiona.open(
            file_path,
            "a",
            driver="GPKG",
            layer="annotations_polygon",
            crs=FionaCRS.from_epsg(4326),
            schema=polygon_schema,
        ) as sink:
            for item in self._annotation_polygon_records:
                ring = item.get("coords", [])
                if ring and ring[0] != ring[-1]:
                    ring = list(ring) + [ring[0]]
                sink.write(
                    {
                        "geometry": {"type": "Polygon", "coordinates": [ring]},
                        "properties": {
                            "feature_type": str(item.get("feature_type") or "building"),
                            "condition": str(item.get("condition") or "intact"),
                            "area_m2": float(item.get("area_m2") or 0.0),
                            "perimeter_m": float(item.get("perimeter_m") or 0.0),
                            "orientation_deg": float(item.get("orientation_deg") or 0.0),
                            "notes": str(item.get("notes") or ""),
                        },
                    }
                )

        self.panel.log(f"GeoPackage export complete: {file_path}")

    def _toolbar_save_project(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self.panel,
            "Save Project",
            "offline_gis_project.json",
            "JSON Files (*.json)",
        )
        if not file_path:
            return
        payload = {
            "selected_asset": self.state.selected_asset,
            "clicked_points": self.state.clicked_points,
            "search_geometry_type": self.state.search_geometry_type,
            "search_geometry_payload": self.state.search_geometry_payload,
            "search_visibility": self._search_layer_visibility,
            "saved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        Path(file_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.panel.log(f"Project saved: {file_path}")

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
        from_search_results = bool(str(options.get("layer_key") or "").strip())
        if is_dem:
            if bool(options.get("replace_existing", True)) and not from_search_results:
                self._explicit_imagery_layer_visible = False
            if not from_search_results:
                self._explicit_dem_layer_visible = True
            self.state.active_layer_is_dem = True
            layer_key = str(options.get("layer_key") or "")
            self._active_dem_search_layer_key = layer_key or None
            self._run_js_call("addDemLayer", asset["file_name"], asset["tile_url"], options)
            self._run_js_call("setSceneModeControlEnabled", False)
            self.panel.rgb_view_mode_combo.setCurrentIndex(0)
            self.panel.rgb_view_mode_combo.setEnabled(False)
            self.panel.apply_rgb_view_mode_btn.setEnabled(False)
            self._apply_display_control_mode()
            self._logger.info("DEM terrain layer requested name=%s", asset["file_name"])
            return True
        replace_existing = bool(options.get("replace_existing", True))
        apply_scene_mode = bool(options.get("apply_scene_mode", True))
        if replace_existing:
            if not from_search_results:
                self._explicit_dem_layer_visible = False
            self.state.active_layer_is_dem = False
            self._active_dem_search_layer_key = None
            self.panel.rgb_view_mode_combo.setEnabled(True)
            self.panel.apply_rgb_view_mode_btn.setEnabled(True)
            self._run_js_call("setSceneModeControlEnabled", True)
            self._apply_display_control_mode()
        mode = str(self.panel.rgb_view_mode_combo.currentData() or "3d").lower()
        if mode not in {"2d", "3d"}:
            mode = "3d"
        if apply_scene_mode:
            if self.state.active_layer_is_dem:
                self._run_js_call("setSceneModeControlEnabled", False)
                self._run_js_call("setSceneMode", "3d")
            else:
                self._run_js_call("setSceneMode", mode)
        self._run_js_call("addTileLayer", asset["file_name"], asset["tile_url"], asset["kind"], options)
        if not from_search_results:
            self._explicit_imagery_layer_visible = True
        self._apply_display_control_mode()
        return True

    def _apply_display_control_mode(self) -> None:
        dem_visible = any(
            self._search_layer_visibility.get(path, False) and self._is_dem_asset(asset)
            for path, asset in self._search_result_assets_by_path.items()
        )
        imagery_visible = any(
            self._search_layer_visibility.get(path, False) and (not self._is_dem_asset(asset))
            for path, asset in self._search_result_assets_by_path.items()
        )
        if self._explicit_dem_layer_visible:
            dem_visible = True
        if self._explicit_imagery_layer_visible:
            imagery_visible = True

        for widget in (
            self.panel.brightness_slider,
            self.panel.contrast_slider,
        ):
            widget.setEnabled(imagery_visible)

        for widget in (
            self.panel.dem_exaggeration_slider,
            self.panel.dem_hillshade_slider,
            self.panel.dem_azimuth_slider,
            self.panel.dem_altitude_slider,
            self.panel.dem_color_mode_combo,
        ):
            widget.setEnabled(dem_visible)

        # Camera controls stay available in all cases.
        self.panel.pitch_slider.setEnabled(True)
        self.panel.rotate_left_btn.setEnabled(True)
        self.panel.rotate_right_btn.setEnabled(True)

        if self._toolbar_context_callback is not None:
            if dem_visible and imagery_visible:
                self._toolbar_context_callback("mixed")
            elif dem_visible:
                self._toolbar_context_callback("dem")
            elif imagery_visible:
                self._toolbar_context_callback("imagery")
            else:
                self._toolbar_context_callback("none")

        if self._swipe_comparator_enabled and not self.can_enable_swipe_comparator():
            self._swipe_comparator_enabled = False
            self._run_js_call("setSwipeComparator", False)
            self.panel.log("Swipe comparator disabled: at least two visible raster layers are required.")

    def _is_dem_asset(self, asset: dict) -> bool:
        file_path = str(asset.get("file_path") or "")
        if file_path and file_path in self._dem_asset_kind_cache:
            return self._dem_asset_kind_cache[file_path]

        kind = str(asset.get("kind", "")).lower()
        file_name = str(asset.get("file_name", "")).lower()
        if kind == "dem" or "dem" in file_name:
            if file_path:
                self._dem_asset_kind_cache[file_path] = True
            return True
        try:
            info = self.api.get_cog_info(asset["file_path"])
        except (httpx.HTTPError, KeyError, TypeError):
            if file_path:
                self._dem_asset_kind_cache[file_path] = False
            return False
        try:
            is_dem = int(info.get("count", 0) or 0) == 1
            if file_path:
                self._dem_asset_kind_cache[file_path] = is_dem
            return is_dem
        except (TypeError, ValueError):
            if file_path:
                self._dem_asset_kind_cache[file_path] = False
            return False

    def _raster_render_query(self, asset: dict) -> dict[str, object]:
        try:
            info = self.api.get_cog_info(asset["file_path"])
        except httpx.HTTPError:
            return {}
        band_count = int(info.get("count", 1) or 1)
        is_dem = str(asset.get("kind", "")).lower() == "dem" or "dem" in str(asset.get("file_name", "")).lower()
        query: dict[str, object] = {}
        nodata_value = info.get("nodata_value", info.get("nodata"))
        try:
            if nodata_value is not None:
                query["nodata"] = float(nodata_value)
        except (TypeError, ValueError):
            pass

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
        if is_dem:
            # For scientific DEM display, keep colorbar values tied to true dataset extremes.
            low = first_band.get("min")
            high = first_band.get("max")
        else:
            low = first_band.get("percentile_2", first_band.get("min"))
            high = first_band.get("percentile_98", first_band.get("max"))
        if low is None or high is None or float(high) <= float(low):
            return query
        if is_dem:
            color_mode = str(self.panel.dem_color_mode_combo.currentData() or "gray")
            query["rescale"] = f"{float(low)},{float(high)}"
            query["colormap_name"] = color_mode
            return query
        query["rescale"] = f"{float(low)},{float(high)}"
        return query

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
