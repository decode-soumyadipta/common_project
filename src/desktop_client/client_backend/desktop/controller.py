from __future__ import annotations

import datetime as dt
import ipaddress
import json
import logging
import math
import re
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import httpx
from pyproj import Transformer
from qtpy.QtCore import QSignalBlocker, QThreadPool, QTimer, Qt
from qtpy.QtWebEngineWidgets import QWebEngineView
from qtpy.QtWidgets import QFileDialog

from desktop_client.client_backend.desktop.api_client import DesktopApiClient
from desktop_client.client_backend.desktop.api_server_manager import ApiServerManager
from desktop_client.client_backend.desktop.app_mode import DesktopAppMode
from desktop_client.client_backend.desktop.bridge import WebBridge
from desktop_client.client_backend.desktop.coordinators import (
    ComparatorCoordinator,
    MeasurementCoordinator,
    ProjectIoCoordinator,
    ToolbarActionCoordinator,
    SearchCoordinator,
    VisualizationCoordinator,
    ExportCoordinator,
)
from desktop_client.client_backend.desktop.coordinators.elevation_profile_coordinator import (
    ElevationProfileCoordinator,
)
from desktop_client.client_backend.desktop.control_panel import ControlPanel
from desktop_client.client_backend.desktop.performance_service import (
    DesktopPerformanceService,
)
from desktop_client.client_backend.desktop.state import DesktopState
from desktop_client.client_backend.desktop.titiler_manager import TiTilerManager
from desktop_client.client_backend.measurement_tools import (
    compute_fill_volume,
    compute_slope_aspect,
    compute_viewshed,
    compute_volume,
    measure_polygon_area,
    measure_shadow_height,
)
from core_shared.ingestion.services.metadata_extractor import (
    MetadataExtractorError,
    extract_metadata,
)
from core_shared.ingestion.services.tile_url_builder import build_xyz_url


def _fmt_vol(m3: float) -> str:
    """Format a volume in m³ with appropriate units.

    Thresholds (correct SI):
      >= 1e9  → km³  (1 km³ = 1,000,000,000 m³)
      >= 1e6  → Mm³  (mega-cubic-metres, useful for large earthworks)
      else    → m³
    For sub-metre DEM / cm-resolution imagery the volumes are always m³.
    """
    if m3 >= 1_000_000_000:
        return f"{m3 / 1_000_000_000:.3f} km³"
    if m3 >= 1_000_000:
        return f"{m3 / 1_000_000:.3f} Mm³"
    return f"{m3:.3f} m³"


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
        self.api_server = api_server_manager or ApiServerManager(
            base_url=self.api.base_url
        )
        self.titiler = titiler_manager or TiTilerManager()
        self.performance = DesktopPerformanceService()
        self.state = DesktopState()
        self._logger = logging.getLogger("desktop.controller")
        self._toolbar_context_callback = toolbar_context_callback
        self._asset_cache: dict[str, dict] = {}
        self._dem_asset_kind_cache: dict[str, bool] = {}
        self._search_result_assets_by_path: dict[str, dict] = {}
        self._search_layer_visibility: dict[str, bool] = {}
        self._last_synced_visibility: dict[
            str, bool
        ] = {}  # Track last synced state to avoid unnecessary JS calls
        self._loaded_search_layer_keys: set[str] = set()
        self._active_dem_search_layer_key: str | None = None
        self._last_visible_focus_signature: tuple[float, float, float, float] | None = (
            None
        )
        self._offline_endpoints_valid = True
        self._layer_loading_active = False
        self._layer_loading_timeout_ms = 30000
        self._layer_loading_timeout_timer = QTimer(panel)
        self._layer_loading_timeout_timer.setSingleShot(True)
        self._layer_loading_timeout_timer.timeout.connect(
            self._on_layer_loading_timeout
        )
        self._measurement_pool = QThreadPool(panel)
        self._measurement_pool.setMaxThreadCount(1)
        self._swipe_comparator_enabled = False
        self._comparator_selected_pane: str | None = None
        self._comparator_selected_layer_type: str | None = None
        self._distance_measure_mode_enabled = False
        self._add_point_mode_enabled = False
        self._shadow_height_mode_enabled = False
        self._pan_mode_enabled = True
        self._polygon_area_mode_enabled = False
        self._volume_mode_enabled = False
        self._viewshed_mode_enabled = False
        self._polygon_drawing_context = "none"  # "none", "search", "measurement"
        self._explicit_imagery_layer_visible = False
        self._explicit_dem_layer_visible = False
        self._last_distance_measurement_signature: (
            tuple[float, float, float, float, float] | None
        ) = None
        self._default_profile_samples = 200
        self._default_annotation_text = "Point"
        self._measurement_done_hooks: dict[str, Callable[[], None]] = {}
        self._on_slope_aspect_done: Callable[[], None] | None = None
        self._last_profile_values: list[float] = []
        self._measurement_history: list[str] = []
        self._annotation_records: list[dict[str, object]] = []
        self._annotation_line_records: list[dict[str, object]] = []
        self._annotation_polygon_records: list[dict[str, object]] = []

        # Event-driven architecture performance tracking
        self._event_driven_enabled = False
        self._terabyte_scale_assets_loaded = 0
        self._performance_metrics = {
            "layer_load_times": [],
            "search_times": [],
            "render_performance": "optimal",
        }
        self._ingest_poll_timer = QTimer(panel)
        self._ingest_poll_timer.setInterval(
            500
        )  # Poll every 500ms for real-time updates
        self._ingest_poll_timer.timeout.connect(self._poll_active_ingest_job)
        self._last_ingest_step: str | None = None
        self._last_ingest_status: str | None = None
        self._ingest_poll_start_time: dt.datetime | None = (
            None  # Track when polling started
        )
        self._search = SearchCoordinator(self)
        self._comparator = ComparatorCoordinator(self)
        self._project_io = ProjectIoCoordinator(self)
        self._export = ExportCoordinator(self)
        self._toolbar_actions = ToolbarActionCoordinator(self)
        self._viz = VisualizationCoordinator(self)
        self._measure = MeasurementCoordinator(self)
        self._elevation_profile = ElevationProfileCoordinator(self)
        self._logger.info("Controller initialized mode=%s", self.app_mode.value)
        self._connect_signals()
        self._apply_display_control_mode()
        # Defer startup network and process work so the main window can render
        # immediately instead of appearing as a silent/no-window launch.
        QTimer.singleShot(0, self._bootstrap_startup_tasks)

    def _bootstrap_startup_tasks(self) -> None:
        try:
            self._prepare_api_runtime()
            self.refresh_assets()

            # Initialize event-driven architecture for terabyte-scale performance
            self._initialize_event_driven_mode()

            # Refresh uploaded assets list on server mode
            if self.app_mode == DesktopAppMode.SERVER:
                self.panel.refresh_uploaded_assets()
        except Exception:  # pragma: no cover - runtime defensive branch
            self.panel.log("Startup initialization failed. Check logs for details.")
            self._logger.exception("Deferred startup tasks failed")

    def _initialize_event_driven_mode(self) -> None:
        """Initialize event-driven architecture for ultra-high performance with terabyte-scale data."""
        try:
            # Enable event-driven mode in the JavaScript bridge
            self._run_js_call("enableEventDrivenMode", True)

            # Apply terabyte-scale optimizations
            optimization_options = {
                "screenSpaceError": 1.5,  # Reduce detail for smoother performance
                "tileCacheSize": 2000,  # Aggressive tile caching
            }
            self._run_js_call("optimizeForTerabyteScale", optimization_options)

            self._event_driven_enabled = True
            self.panel.log(
                "Event-driven architecture initialized for terabyte-scale performance"
            )
            self._logger.info("Event-driven mode initialized successfully")

        except Exception:
            self._logger.warning(
                "Event-driven mode initialization failed", exc_info=True
            )
            self.panel.log("Warning: Event-driven optimizations not available")

    def _track_performance_metric(
        self, metric_type: str, value: float, context: str = ""
    ) -> None:
        """Track performance metrics for event-driven architecture."""
        if not self._event_driven_enabled:
            return

        if metric_type in self._performance_metrics:
            if isinstance(self._performance_metrics[metric_type], list):
                self._performance_metrics[metric_type].append(
                    {
                        "value": value,
                        "context": context,
                        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
                    }
                )

                # Keep only recent metrics (last 50 entries)
                if len(self._performance_metrics[metric_type]) > 50:
                    self._performance_metrics[metric_type] = self._performance_metrics[
                        metric_type
                    ][-50:]

        # Log significant performance events
        if metric_type == "layer_load_times" and value > 5.0:
            self._logger.info("Event-driven layer load: %.2fs %s", value, context)
        elif metric_type == "search_times" and value > 2.0:
            self._logger.info("Event-driven search: %.2fs %s", value, context)

    def _get_performance_summary(self) -> dict:
        """Get performance summary for event-driven architecture."""
        if not self._event_driven_enabled:
            return {"status": "disabled"}

        summary = {
            "status": "enabled",
            "terabyte_assets_loaded": self._terabyte_scale_assets_loaded,
            "render_performance": self._performance_metrics.get(
                "render_performance", "unknown"
            ),
        }

        # Calculate average load times
        load_times = self._performance_metrics.get("layer_load_times", [])
        if load_times:
            avg_load_time = sum(m["value"] for m in load_times) / len(load_times)
            summary["avg_layer_load_time"] = round(avg_load_time, 2)

        # Calculate average search times
        search_times = self._performance_metrics.get("search_times", [])
        if search_times:
            avg_search_time = sum(m["value"] for m in search_times) / len(search_times)
            summary["avg_search_time"] = round(avg_search_time, 2)

        return summary

    def _clear_asset_caches(self) -> None:
        """Clear asset catalog caches to ensure fresh data on next fetch.

        NOTE: _search_result_assets_by_path and _search_layer_visibility are
        intentionally NOT cleared here – those belong to the user's active
        search session and must survive catalog refreshes.
        """
        self._asset_cache.clear()
        self._dem_asset_kind_cache.clear()
        # Do NOT clear _search_result_assets_by_path or _search_layer_visibility

        # Clear additional state variables that might cache data
        self._active_dem_search_layer_key = None
        self._last_visible_focus_signature = None

        # Clear performance metrics cache
        if hasattr(self, "_performance_metrics"):
            self._performance_metrics = {
                "layer_load_times": [],
                "search_times": [],
                "render_performance": "optimal",
            }

        # Clear any API client caches
        if hasattr(self.api, "_cache"):
            self.api._cache.clear()

        # Clear only the assets combo box - this is necessary as it's the main catalog selector
        self.panel.assets_combo.clear()

        # NOTE: We no longer clear search_results_table or uploaded_assets_list here.
        # This ensures that clicking 'Refresh' doesn't wipe the user's current view.
        # The tables will be updated naturally when fresh data arrives.

        # Reset state variables
        self.state.selected_asset = None
        if hasattr(self.state, "active_ingest_job_id"):
            self.state.active_ingest_job_id = None
        if hasattr(self.state, "pending_ingest_source_path"):
            self.state.pending_ingest_source_path = None

        # Log the cache clearing (removed the refresh call to prevent infinite loop)
        self._logger.info("Asset caches cleared successfully")
        self.panel.log("Asset caches cleared")

        self._logger.debug("All asset caches cleared")

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

        # Client mode: auto-start only for local loopback targets; remote LAN targets are never auto-started.
        if self.api.api_ready():
            self.panel.log(f"API ready: {self.api.base_url}")
            return
        if self.api_server.ensure_running():
            self.panel.log(f"API ready: {self.api.base_url}")
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
            status_code = (
                exc.response.status_code if exc.response is not None else "unknown"
            )
            detail = self._http_error_detail(exc)
            message = f"{action} failed with API status {status_code}."
            if detail:
                message = f"{message} Detail: {detail}"
            self.panel.log(f"{message} Check API logs and refresh again.")
            self._logger.error(
                "%s failed with status=%s detail=%s", action, status_code, detail
            )
            return
        self.panel.log(f"{action} failed: {exc}")
        self._logger.error("%s failed: %s", action, exc)

    @staticmethod
    def _http_error_detail(exc: httpx.HTTPStatusError) -> str:
        if exc.response is None:
            return ""
        try:
            payload = exc.response.json()
            if isinstance(payload, dict):
                detail = payload.get("detail")
                if detail is not None:
                    return str(detail)
            return str(payload)
        except Exception:  # noqa: BLE001
            body = (exc.response.text or "").strip()
            return body[:300]

    def _connect_signals(self) -> None:
        # File selection buttons
        self._connect_button(
            self.panel.browse_files_btn.clicked, "Browse Files", self.browse_files
        )
        self._connect_button(
            self.panel.clear_selection_btn.clicked,
            "Clear Selection",
            self.clear_file_selection,
        )
        self._connect_button(
            self.panel.ingest_btn.clicked, "Ingest Files", self.enqueue_selected_files
        )

        # Asset management
        self._connect_button(
            self.panel.refresh_assets_btn.clicked, "Refresh Assets", self.refresh_assets
        )
        # add_layer_btn was removed; no connection needed

        # Asset deletion
        self.panel.asset_delete_requested.connect(self.delete_asset)

        # Display controls
        self.panel.brightness_slider.valueChanged.connect(
            self._on_visual_slider_changed
        )
        self.panel.contrast_slider.valueChanged.connect(self._on_visual_slider_changed)
        self.panel.dem_hillshade_slider.valueChanged.connect(
            self._on_dem_slider_changed
        )
        self.panel.dem_color_mode_combo.currentIndexChanged.connect(
            self._on_dem_color_mode_changed
        )
        self._connect_button(
            self.panel.apply_rgb_view_mode_btn.clicked,
            "Apply RGB View Mode",
            self.apply_rgb_view_mode,
        )
        self._connect_button(
            self.panel.rotate_left_btn.clicked,
            "Rotate Left",
            lambda: self.rotate_camera(-10.0),
        )
        self._connect_button(
            self.panel.rotate_right_btn.clicked,
            "Rotate Right",
            lambda: self.rotate_camera(10.0),
        )
        self.panel.pitch_slider.valueChanged.connect(self.set_pitch)
        self._connect_button(
            self.panel.search_point_btn.clicked,
            "Search by Coordinate",
            self.search_assets_by_coordinate,
        )
        self._connect_button(
            self.panel.search_draw_polygon_btn.clicked,
            "Draw Search Polygon",
            self.set_search_draw_mode,
        )
        self._connect_button(
            self.panel.search_finish_polygon_btn.clicked,
            "Finish Search Polygon",
            self.finish_search_polygon,
        )
        self._connect_button(
            self.panel.search_clear_geometry_btn.clicked,
            "Clear Search Geometry",
            self.clear_search_geometry,
        )
        self._connect_button(
            self.panel.search_from_draw_btn.clicked,
            "Search from Drawn Geometry",
            self.search_assets_from_drawn_geometry,
        )
        self.panel.search_result_visibility_toggled.connect(
            self.toggle_search_result_visibility
        )
        self.panel.search_layers_reordered.connect(self.reorder_search_result_layers)
        self.bridge.mapClicked.connect(self.on_map_click)
        self.bridge.measurementUpdated.connect(self.on_measurement)
        self.bridge.jsLogReceived.connect(self.on_js_log)
        self.bridge.searchGeometryChanged.connect(self.on_search_geometry)
        self.bridge.comparatorPaneStateChanged.connect(self.on_comparator_pane_state)
        self.panel.uploaded_assets_list.itemSelectionChanged.connect(
            self.preview_selected_uploaded_asset
        )
        self.panel.measurement_result_clear_selected_requested.connect(
            self.clear_selected_measurement_result
        )
        self.panel.measurement_result_clear_all_requested.connect(
            self.clear_all_measurement_results
        )
        self.panel.uploaded_assets_refresh_requested.connect(self._clear_asset_caches)

    def _connect_button(
        self, signal, label: str, callback: Callable[..., object]
    ) -> None:
        signal.connect(
            lambda *args, _label=label, _callback=callback: self._on_button_invoked(
                _label,
                _callback,
                *args,
            )
        )

    def _on_button_invoked(
        self, label: str, callback: Callable[..., object], *args
    ) -> None:
        try:
            callback(*args)
        except TypeError:
            callback()
        except Exception:  # pragma: no cover - runtime defensive branch
            self.panel.log(f"Action failed: {label}. Check logs for details.")
            self._logger.exception("UI button failed: %s", label)

    def preview_selected_uploaded_asset(self) -> None:
        """Load and flyto the selected asset from uploaded assets table."""
        row = self.panel.uploaded_assets_list.currentRow()
        if row < 0:
            return

        # Get asset data from the first column (serial number column)
        item = self.panel.uploaded_assets_list.item(row, 0)
        if item is None:
            return

        asset = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(asset, dict):
            return

        file_path = str(asset.get("file_path") or "")
        file_name = str(asset.get("file_name") or "Unknown")
        kind = str(asset.get("kind") or "Unknown").upper()

        if not file_path:
            return

        # Cache the asset
        self._asset_cache[file_path] = asset
        self.state.selected_asset = asset

        # Load the asset layer
        loaded_asset = self._load_asset_layer(asset)
        if not loaded_asset:
            self.panel.log(f"Failed to load asset: {file_name}")
            return

        self.panel.log(f"Loading {kind}: {file_name}")

        # Smooth flyto the asset region
        self._flyto_asset_bounds(asset, kind)

        self._logger.info(
            "Asset loaded and camera moved: name=%s kind=%s",
            file_name,
            kind,
        )

    def _flyto_asset_bounds(self, asset: dict, kind: str) -> None:
        """Smooth camera flyto for the asset bounds with smart 2D/3D rendering."""
        try:
            # Get asset bounds
            bounds = asset.get("bounds")
            if not bounds or len(bounds) != 4:
                self.panel.log("Asset bounds not available for flyto")
                return

            west, south, east, north = bounds

            # Calculate center and appropriate camera height
            center_lon = (west + east) / 2
            center_lat = (south + north) / 2

            # Calculate diagonal distance for camera height
            import math

            lat_diff = north - south
            lon_diff = east - west
            diagonal = math.sqrt(lat_diff**2 + lon_diff**2)

            # Camera height based on asset size (in degrees to meters approximation)
            # 1 degree ≈ 111km, we want to see the whole asset
            camera_height = diagonal * 111000 * 1.5  # 1.5x for padding
            camera_height = max(
                1000, min(camera_height, 50000000)
            )  # Clamp between 1km and 50,000km

            # Determine rendering mode based on asset type
            is_dem = kind in ["DEM", "ELEVATION"]

            # Smart camera positioning
            if is_dem:
                # For DEM: 3D view with tilt for terrain visualization
                pitch_degrees = -45  # Look down at 45 degrees
                heading_degrees = 0
                self.panel.log(f"Flying to DEM (3D view): {asset.get('file_name')}")
            else:
                # For imagery: 2D top-down view
                pitch_degrees = -90  # Straight down
                heading_degrees = 0
                self.panel.log(f"Flying to imagery (2D view): {asset.get('file_name')}")

            # Execute smooth flyto
            self._run_js_call(
                "flyToLocation",
                {
                    "longitude": center_lon,
                    "latitude": center_lat,
                    "height": camera_height,
                    "heading": heading_degrees,
                    "pitch": pitch_degrees,
                    "roll": 0,
                    "duration": 2.0,  # 2 second smooth animation
                },
            )

            self._logger.info(
                "Camera flyto: lon=%.4f lat=%.4f height=%.0f pitch=%d (mode=%s)",
                center_lon,
                center_lat,
                camera_height,
                pitch_degrees,
                "3D" if is_dem else "2D",
            )

        except Exception as e:
            self._logger.error("Flyto failed: %s", e, exc_info=True)
            self.panel.log(f"Camera movement failed: {e}")


    def search_assets_by_coordinate(self) -> None:
        """Search assets by coordinate using server-side metadata processing."""
        self._search.search_assets_by_coordinate_event_driven()

    def search_assets_from_drawn_geometry(self) -> None:
        """Search assets from drawn geometry using server-side processing."""
        self._search.search_assets_from_drawn_geometry_event_driven()

    def _set_search_draw_button_checked(self, checked: bool) -> None:
        button = self.panel.search_draw_polygon_btn
        if button.isChecked() != checked:
            button.blockSignals(True)
            button.setChecked(checked)
            button.blockSignals(False)

    def set_search_draw_mode(self, enabled: bool | None = None) -> None:
        self._search.set_search_draw_mode(enabled)

    def finish_search_polygon(self) -> None:
        self._search.finish_search_polygon()

    def clear_search_geometry(self) -> None:
        self._search.clear_search_geometry()

    def _set_annotation_overlay_visible(self, visible: bool) -> None:
        self._run_js_call("setAnnotationVisibility", bool(visible))

    def _set_measurement_cursor_enabled(self, enabled: bool) -> None:
        self._run_js_call("setMeasurementCursor", bool(enabled))

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

    def on_search_geometry(self, geometry_type: str, payload_json: str) -> None:
        self._search.on_search_geometry(geometry_type, payload_json)

    @staticmethod
    def _set_slider_from_float_value(
        slider, raw_value: object, scale: float = 1.0
    ) -> None:
        if not isinstance(raw_value, (int, float)):
            return
        scaled = int(round(float(raw_value) * scale))
        slider.setValue(max(slider.minimum(), min(slider.maximum(), scaled)))

    def on_comparator_pane_state(self, payload_json: str) -> None:
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            self._logger.warning(
                "Invalid comparator pane state payload JSON: %s", payload_json
            )
            return

        if not isinstance(payload, dict):
            self._logger.warning(
                "Invalid comparator pane state payload type: %s", type(payload).__name__
            )
            return

        pane = str(payload.get("pane") or "").strip().lower()
        layer_type = str(payload.get("layer_type") or "").strip().lower()
        if pane not in {"left", "right"}:
            pane = "left"
        self._comparator_selected_pane = pane
        self._comparator_selected_layer_type = (
            layer_type if layer_type in {"dem", "imagery"} else None
        )

        imagery = (
            payload.get("imagery") if isinstance(payload.get("imagery"), dict) else {}
        )
        dem = payload.get("dem") if isinstance(payload.get("dem"), dict) else {}

        blockers = [
            QSignalBlocker(self.panel.brightness_slider),
            QSignalBlocker(self.panel.contrast_slider),
            QSignalBlocker(self.panel.dem_hillshade_slider),
            QSignalBlocker(self.panel.dem_color_mode_combo),
        ]
        try:
            self._set_slider_from_float_value(
                self.panel.brightness_slider, imagery.get("brightness"), scale=100.0
            )
            self._set_slider_from_float_value(
                self.panel.contrast_slider, imagery.get("contrast"), scale=100.0
            )
            self._set_slider_from_float_value(
                self.panel.dem_hillshade_slider, dem.get("hillshade_alpha"), scale=100.0
            )

            color_mode = str(dem.get("color_mode") or "").strip().lower()
            if color_mode:
                color_mode_index = self.panel.dem_color_mode_combo.findData(color_mode)
                if color_mode_index >= 0:
                    self.panel.dem_color_mode_combo.setCurrentIndex(color_mode_index)
        finally:
            del blockers

        self.panel._update_display_value_labels()
        self._apply_display_control_mode()
        self._logger.debug(
            "Comparator pane selected pane=%s type=%s",
            self._comparator_selected_pane,
            self._comparator_selected_layer_type,
        )

    def _apply_search_results(self, assets: list[dict], label: str) -> None:
        """Apply search results with standard processing."""
        self._apply_search_results_internal(assets, label, event_driven=False)

    def _apply_search_results_event_driven(
        self, assets: list[dict], label: str
    ) -> None:
        """Apply search results with event-driven optimization for terabyte-scale performance."""
        self._apply_search_results_internal(assets, label, event_driven=True)

    def _apply_search_results_internal(
        self, assets: list[dict], label: str, event_driven: bool = False
    ) -> None:
        """Internal method to apply search results with optional event-driven optimization."""
        assets = self._dedupe_assets(assets)
        self.panel.assets_combo.clear()
        self._asset_cache = {}
        previous_assets = self._search_result_assets_by_path
        previously_visible_paths = {
            path
            for path, is_visible in self._search_layer_visibility.items()
            if is_visible
        }
        had_visible_assets = bool(previously_visible_paths)
        self._search_result_assets_by_path = {}
        local_missing_count = 0

        # Event-driven optimization: Pre-process assets for terabyte-scale performance
        if event_driven:
            assets = self._preprocess_assets_for_terabyte_scale(assets)

        for asset in assets:
            if not self._asset_path_accessible_locally(asset):
                local_missing_count += 1
            file_path = str(asset.get("file_path") or "").replace("\\", "/")
            if not file_path:
                continue
            self._asset_cache[file_path] = asset
            self._search_result_assets_by_path[file_path] = asset

            # Event-driven display optimization
            display_suffix = ""
            if event_driven and asset.get("performance_tier") == "ultra_large":
                display_suffix = " [TB-Scale]"
            elif event_driven and asset.get("performance_tier") == "large":
                display_suffix = " [Large]"

            display = f"{asset['file_name']} [{asset['kind']}]{display_suffix}"
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

        # CRITICAL FIX: Always force 3D mode when search results are found
        if assets:
            self._logger.info("Search results found - forcing 3D mode for consistency")
            self._run_js_call("setSceneMode", "3d")
            # Update the RGB view mode combo to reflect 3D mode
            self.panel.rgb_view_mode_combo.setCurrentIndex(0)  # 0 = "3D Terrain Scene"
            self._apply_display_control_mode()  # This will enable/disable pitch slider based on mode
            self.panel.log("Search results displayed in 3D mode")

        # Event-driven layer synchronization
        if event_driven:
            self._sync_search_visibility_layers_event_driven()
        else:
            self._sync_search_visibility_layers()

        # FIX 1 — Layer order: enforce display order matching the UI list.
        # UI display sort: imagery (non-DEM) at row 0 = visually ON TOP in Cesium.
        # IMPORTANT: sort imagery before DEM so JS raises imagery to the top correctly.
        # (Previously we used dict insertion order which was API order = DEM first → wrong.)
        ordered_keys = sorted(
            [
                p.replace("\\", "/")
                for p in self._search_result_assets_by_path.keys()
                if self._search_layer_visibility.get(p, True)
            ],
            key=lambda p: (
                1 if self._is_dem_asset(self._search_result_assets_by_path.get(p, {})) else 0,
                p,  # stable tie-break by path
            ),
        )
        if ordered_keys:
            self._run_js_call("enforceLayerDisplayOrder", ordered_keys)

        # FIX 2 — Fly-to: single controlled fly-to AFTER layers+order are set,
        # so the globe is never blank during flight.
        self._focus_visible_search_assets_with_enhanced_behavior(
            force=not had_visible_assets,
            is_first_search=not had_visible_assets,
            asset_count=len(assets),
        )

        self.panel.update_search_results(assets, self._search_layer_visibility)

        # Enhanced logging for event-driven mode
        if event_driven:
            terabyte_count = sum(
                1 for a in assets if a.get("performance_tier") == "ultra_large"
            )
            large_count = sum(1 for a in assets if a.get("performance_tier") == "large")
            self.panel.log(
                f"{label}: {self.panel.assets_combo.count()} assets (TB-scale: {terabyte_count}, Large: {large_count})"
            )
        else:
            self.panel.log(f"{label}: {self.panel.assets_combo.count()} assets")

        if local_missing_count:
            self.panel.log(
                f"Note: {local_missing_count} result(s) are remote-only paths; loading uses server-side tiles."
            )

    def _preprocess_assets_for_terabyte_scale(self, assets: list[dict]) -> list[dict]:
        """Preprocess assets for terabyte-scale performance optimization."""
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

        self._logger.info(
            "Preprocessed %d assets for terabyte-scale performance", len(processed)
        )
        return processed

    @staticmethod
    def _asset_identity_key(asset: dict) -> str:
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
        name = str(asset.get("file_name") or asset.get("file_path") or "").lower()
        return ".cog." in name or name.endswith(".cog.tif") or name.endswith(".cog.tiff")

    def _dedupe_assets(self, assets: list[dict]) -> list[dict]:
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
                                        from core_shared.ingestion.services.tile_url_builder import build_xyz_url
                                        asset["tile_url"] = build_xyz_url(cand)
                                    except Exception as e:
                                        self._logger.error("Failed to build tile_url for reverted asset: %s", e)
                                self._logger.info("Reverted isolated COG asset to original path: %s", cand)
                                break
                        except Exception:
                            pass
                            
        if len(deduped) != len(assets):
            self._logger.info("Deduped assets: %d -> %d (Original non-COG preferred)", len(assets), len(deduped))
        return deduped

    def _sync_search_visibility_layers_event_driven(self) -> None:
        """Synchronize search visibility layers with event-driven optimization."""
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

            if (
                is_dem_asset
                and self._active_dem_search_layer_key
                and self._active_dem_search_layer_key != file_path
            ):
                self._search_layer_visibility[file_path] = False
                self._run_js_call("setLayerVisibility", file_path, False)
                continue

            if is_dem_asset and self._active_dem_search_layer_key == file_path:
                continue

            if (not is_dem_asset) and file_path in self._loaded_search_layer_keys:
                self._run_js_call("setLayerVisibility", file_path, True)
                continue

            # Event-driven layer loading with server optimization
            loaded = self._load_asset_layer_event_driven(
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

    def _load_asset_layer_event_driven(
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
        if show_loading:
            performance_tier = asset.get("performance_tier", "standard")
            loading_msg = f"Loading {asset['file_name']} [{performance_tier}]..."
            self._set_layer_loading(True, loading_msg)

        # Use existing _load_asset_layer but with event-driven flags
        options = self._get_server_optimized_layer_options(asset)
        options["replace_existing"] = replace_existing
        if layer_key:
            options["layer_key"] = str(layer_key).replace("\\", "/")
        options["apply_scene_mode"] = apply_scene_mode
        options["event_driven"] = True

        if self._add_layer_event_driven(asset, options):
            if auto_fly_to:
                self._fly_through_asset_event_driven(asset)
        else:
            if show_loading:
                self._set_layer_loading(False, "Layer load failed")
            return None

        self.state.selected_asset = asset
        return asset

    def toggle_search_result_visibility(self, file_path: str, visible: bool) -> None:
        """Toggle visibility of a search result layer with debug logging."""
        print(f"\n{'=' * 80}")
        print(f"DEBUG: toggle_search_result_visibility called")
        print(f"  file_path: {file_path}")
        print(f"  visible (requested): {visible}")
        print(f"  Current visibility map: {self._search_layer_visibility}")
        print(f"{'=' * 80}\n")

        normalized_path = str(file_path or "").strip().replace("\\", "/")
        if not normalized_path:
            print("DEBUG: Visibility toggle ignored: missing asset path")
            self.panel.log("Visibility toggle ignored: missing asset path.")
            return

        asset = self._search_result_assets_by_path.get(normalized_path)
        if not isinstance(asset, dict):
            print(
                f"DEBUG: Visibility toggle ignored: asset not in search results for path={normalized_path}"
            )
            print(
                f"DEBUG: Available paths in search results: {list(self._search_result_assets_by_path.keys())}"
            )
            self.panel.log(
                "Visibility toggle ignored: asset is no longer in current search results."
            )
            return

        next_visible = bool(visible)
        print(
            f"DEBUG: Asset found: {asset.get('file_name')}, kind={asset.get('kind')}, next_visible={next_visible}"
        )

        if next_visible and self._is_dem_asset(asset):
            print("DEBUG: Showing DEM - hiding other DEM layers")
            for path, candidate in self._search_result_assets_by_path.items():
                if path != normalized_path and self._is_dem_asset(candidate):
                    self._search_layer_visibility[path] = False
                    print(f"DEBUG: Hiding other DEM: {candidate.get('file_name')}")

        self._search_layer_visibility[normalized_path] = next_visible
        print(f"DEBUG: Updated visibility map: {normalized_path} = {next_visible}")
        print(
            f"DEBUG: Full visibility map after update: {self._search_layer_visibility}"
        )

        self._sync_search_visibility_layers()

        if self._search_layer_visibility.get(normalized_path, False):
            self.panel.log(f"Shown on map: {asset.get('file_name', 'asset')}")
            print(f"DEBUG: Layer shown: {asset.get('file_name')}")
        else:
            self.panel.log(f"Hidden from map: {asset.get('file_name', 'asset')}")
            print(f"DEBUG: Layer hidden: {asset.get('file_name')}")

        print(f"DEBUG: Calling panel.update_search_results to refresh UI")
        self.panel.update_search_results(
            list(self._search_result_assets_by_path.values()),
            self._search_layer_visibility,
        )
        print(f"DEBUG: toggle_search_result_visibility completed\n")

    def _sync_search_visibility_layers(self) -> None:
        """Sync layer visibility between UI and globe with debug logging - optimized to only update changed layers."""
        print(f"\n{'=' * 80}")
        print(f"DEBUG: _sync_search_visibility_layers called")
        print(f"  Current visibility map: {self._search_layer_visibility}")
        print(f"  Last synced visibility: {self._last_synced_visibility}")
        print(f"  Loaded layer keys: {self._loaded_search_layer_keys}")
        print(f"  Active DEM layer key: {self._active_dem_search_layer_key}")
        print(f"{'=' * 80}\n")

        for file_path, asset in self._search_result_assets_by_path.items():
            should_show = bool(self._search_layer_visibility.get(file_path, False))
            last_synced = self._last_synced_visibility.get(file_path, None)
            is_dem_asset = self._is_dem_asset(asset)
            file_name = asset.get("file_name", "unknown")
            is_loaded = file_path in self._loaded_search_layer_keys

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
                    self._run_js_call("setLayerVisibility", file_path, False)
                    self._last_synced_visibility[file_path] = False
                    if is_dem_asset and self._active_dem_search_layer_key == file_path:
                        self.state.active_layer_is_dem = False
                        self._active_dem_search_layer_key = None
                        self._apply_display_control_mode()
                        print(f"  DEM deactivated")
                else:
                    print(f"  SKIP: Layer not loaded, no need to hide")
                continue

            if is_dem_asset and is_loaded:
                print(f"  ACTION: Showing DEM layer via setLayerVisibility")
                self._run_js_call("setLayerVisibility", file_path, True)
                self._last_synced_visibility[file_path] = True
                self.state.active_layer_is_dem = True
                self._active_dem_search_layer_key = file_path
                self._apply_display_control_mode()
                print(f"  DEM activated")
                continue

            if (
                is_dem_asset
                and self._active_dem_search_layer_key
                and self._active_dem_search_layer_key != file_path
            ):
                print(f"  ACTION: Hiding DEM (another DEM is active)")
                self._search_layer_visibility[file_path] = False
                if is_loaded:
                    self._run_js_call("setLayerVisibility", file_path, False)
                    self._last_synced_visibility[file_path] = False
                continue

            if is_dem_asset and self._active_dem_search_layer_key == file_path:
                print(f"  SKIP: DEM already active")
                continue

            if (not is_dem_asset) and is_loaded:
                print(f"  ACTION: Showing imagery layer via setLayerVisibility")
                self._run_js_call("setLayerVisibility", file_path, True)
                self._last_synced_visibility[file_path] = True
                continue

            if not is_loaded:
                print(f"  ACTION: Loading new layer")
                loaded = self._load_asset_layer(
                    asset,
                    replace_existing=False,
                    layer_key=file_path,
                    auto_fly_to=False,
                    apply_scene_mode=False,
                    show_loading=False,
                )
                if not loaded:
                    print(f"  ERROR: Failed to load layer")
                    self._search_layer_visibility[file_path] = False
                    continue

                self._loaded_search_layer_keys.add(file_path)
                self._last_synced_visibility[file_path] = True
                print(f"  SUCCESS: Layer loaded and added to loaded keys")

        self._apply_display_control_mode()
        print(f"DEBUG: _sync_search_visibility_layers completed\n")

    def _focus_visible_search_assets(self, *, force: bool) -> None:
        """Legacy focus function - delegates to enhanced version."""
        self._focus_visible_search_assets_with_enhanced_behavior(
            force=force,
            is_first_search=force,
            asset_count=len(self._search_result_assets_by_path),
        )

    def _focus_visible_search_assets_with_enhanced_behavior(
        self, *, force: bool, is_first_search: bool, asset_count: int
    ) -> None:
        """Enhanced focus function with improved multi-asset handling and first-search auto-flyto."""
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

            # Enhanced behavior for multiple assets and first search
            if is_first_search:
                if len(visible_assets) == 1:
                    # Single asset: fly to it with appropriate zoom
                    self._logger.info("First search: Flying to single asset")
                    self._fly_to_asset(visible_assets[0])
                    self.panel.log(
                        f"Focused on search result: {visible_assets[0].get('file_name', 'asset')}"
                    )
                else:
                    # Multiple assets: fit all in view with padding
                    self._logger.info(
                        f"First search: Fitting {len(visible_assets)} assets in view"
                    )
                    self._run_js_call(
                        "focusBoundsWithPadding",
                        union_bounds["west"],
                        union_bounds["south"],
                        union_bounds["east"],
                        union_bounds["north"],
                        1.5,  # 50% padding to ensure all assets are visible
                    )
                    self.panel.log(f"Focused on {len(visible_assets)} search results")
            else:
                # Subsequent searches: use standard focus without animation
                self._run_js_call(
                    "focusBounds",
                    union_bounds["west"],
                    union_bounds["south"],
                    union_bounds["east"],
                    union_bounds["north"],
                )
            return

        # Fallback: focus on first visible asset
        self._fly_to_asset(visible_assets[0])

    def reorder_search_result_layers(self, reordered_layers: list[dict]) -> None:
        """Handle drag-and-drop reordering of search result layers with real-time globe updates."""
        print(f"\n{'=' * 80}")
        print(f"DEBUG: reorder_search_result_layers called in controller!")
        print(f"  reordered_layers: {reordered_layers}")
        print(f"{'=' * 80}\n")
        try:
            if not reordered_layers:
                print("DEBUG: No reordered layers, returning")
                return

            print(f"DEBUG: Processing {len(reordered_layers)} layers")

            # Track performance for event-driven architecture
            import time

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
                if normalized_path in self._search_result_assets_by_path:
                    asset = self._search_result_assets_by_path[normalized_path]
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
                self.panel.log("Layer reordering failed: No matching assets found")
                print(
                    "ERROR: No matching assets found in _search_result_assets_by_path"
                )
                print(
                    f"DEBUG: Available asset paths: {list(self._search_result_assets_by_path.keys())}"
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
                if file_path not in self._loaded_search_layer_keys:
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
                    loaded = self._load_asset_layer_event_driven(
                        asset,
                        replace_existing=False,
                        layer_key=file_path,
                        auto_fly_to=False,
                        apply_scene_mode=False,
                        show_loading=False,
                    )

                    if loaded:
                        self._loaded_search_layer_keys.add(file_path)
                        print(f"  Successfully loaded missing layer: {file_path}")
                    else:
                        print(f"  Failed to load missing layer: {file_path}")

                # Small delay to allow layers to initialize
                import time

                time.sleep(0.1)

            # Update the Cesium layer stack order using event-driven approach
            if self._event_driven_enabled:
                self._reorder_layers_event_driven(reordered_assets)
            else:
                self._reorder_layers_standard(reordered_assets)

            # Track performance metrics
            elapsed_time = time.time() - start_time
            self._track_performance_metric(
                "layer_reorder_times", elapsed_time, f"layers={len(reordered_layers)}"
            )

            # Log the successful reordering
            layer_names = [
                asset.get("file_name", "Unknown") for asset in reordered_assets
            ]
            if len(layer_names) <= 3:
                self.panel.log(f"Layers reordered: {', '.join(layer_names)}")
            else:
                self.panel.log(
                    f"Layers reordered: {', '.join(layer_names[:3])} and {len(layer_names) - 3} more"
                )

            self._logger.info(
                "Search result layers reordered: %d layers in %.3fs",
                len(reordered_layers),
                elapsed_time,
            )

        except Exception as e:
            self.panel.log(f"Layer reordering failed: {str(e)}")
            self._logger.error(
                "Failed to reorder search result layers: %s", e, exc_info=True
            )

    def _reorder_layers_event_driven(self, reordered_assets: list[dict]) -> None:
        """Reorder layers using event-driven approach for optimal performance.

        CRITICAL: We reorder ALL layers that are loaded, regardless of current visibility.
        The visibility state is managed separately by the toggle buttons.
        """
        try:
            print(f"\n{'=' * 80}")
            print(
                f"DEBUG: _reorder_layers_event_driven called with {len(reordered_assets)} assets"
            )
            print(
                f"DEBUG: Current _loaded_search_layer_keys: {self._loaded_search_layer_keys}"
            )
            print(
                f"DEBUG: Current _search_result_assets_by_path keys: {list(self._search_result_assets_by_path.keys())}"
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
                if file_path not in self._loaded_search_layer_keys:
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
                        "is_dem": self._is_dem_asset(asset),
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
                self._run_js_call("reorderLayersEventDriven", layer_commands)
                self._logger.info(
                    "EVENT_DRIVEN: Sent %d layer reorder commands", len(layer_commands)
                )

                # Force additional render after reordering
                self._run_js_call("requestSceneRender")
                print(f"DEBUG: Reorder commands sent successfully")
            else:
                print(f"WARNING: No loaded layers found to reorder")
                self._logger.warning("EVENT_DRIVEN: No loaded layers found to reorder")
                self.panel.log("Layer reordering: No loaded layers found on map")

                # Debug: Show what layers we have vs what we're looking for
                print(
                    f"DEBUG: Available loaded layer keys: {self._loaded_search_layer_keys}"
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
            self.panel.log(
                f"Layer reordering: Event-driven approach failed, using fallback"
            )
            self._reorder_layers_standard(reordered_assets)

    def _reorder_layers_standard(self, reordered_assets: list[dict]) -> None:
        """Reorder layers using standard approach.

        CRITICAL: Reorder ALL loaded layers, not just visible ones.
        """
        try:
            # For standard approach, we need to manipulate the Cesium layer stack
            # by raising/lowering layers to achieve the desired order
            loaded_layers = []
            for asset in reordered_assets:
                file_path = str(asset.get("file_path", "")).replace("\\", "/")
                if not file_path:
                    continue

                # Check if layer is loaded (not just visible)
                if file_path in self._loaded_search_layer_keys:
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
                self._run_js_call("raiseLayerToTop", layer_key)

        except Exception as e:
            self._logger.error("Standard layer reordering failed: %s", e)

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

    def browse_files(self) -> None:
        """Browse and select multiple raster files based on selected format."""
        from qtpy.QtWidgets import QFileDialog

        # Get selected format from dropdown
        format_index = self.panel.format_combo.currentIndex()

        # Define file filters based on format
        if format_index == 0:  # GeoTIFF
            file_filter = (
                "GeoTIFF and world files (*.tif *.tiff *.tfw *.tifw);;All Files (*)"
            )
            dialog_title = "Select GeoTIFF files and optional .tfw world files"
        elif format_index == 1:  # JPEG2000 + PRJ
            # Include world files (.j2w, .jgw) in the filter
            file_filter = "JPEG2000 and auxiliary files (*.jp2 *.j2k *.prj *.j2w *.jgw);;All Files (*)"
            dialog_title = "Select JPEG2000 files and their .prj/.j2w files"
        elif format_index == 2:  # MBTiles
            file_filter = "MBTiles (*.mbtiles);;All Files (*)"
            dialog_title = "Select MBTiles files"
        else:
            file_filter = (
                "Raster Files (*.tif *.tiff *.jp2 *.j2k *.mbtiles);;All Files (*)"
            )
            dialog_title = "Select raster files"

        files, _ = QFileDialog.getOpenFileNames(
            self.panel, dialog_title, "", file_filter
        )

        if files:
            self.panel.add_selected_files(files)

            # Count valid files after validation
            valid_count = self.panel.selected_files_list.count()

            if valid_count > 0:
                self.panel.log(f"Selected {valid_count} valid file(s) for ingestion")

                # Log file details (first 5)
                for i in range(min(5, valid_count)):
                    item = self.panel.selected_files_list.item(i)
                    if item:
                        self.panel.log(f"  - {item.text()}")

                if valid_count > 5:
                    self.panel.log(f"  ... and {valid_count - 5} more files")
            else:
                self.panel.log("No valid files selected after validation")

    def clear_file_selection(self) -> None:
        """Clear the current file selection."""
        self.panel.clear_selected_files()
        self.panel.log("File selection cleared")

    def enqueue_selected_files(self) -> None:
        """Enqueue the selected files for ingestion."""
        if not self._require_offline_endpoints("Ingest files"):
            return
        if not self.api.api_ready():
            self.panel.log(
                f"API unavailable at {self.api.base_url}. Start API/server desktop, then retry 'Ingest files'."
            )
            return

        selected_files = self.panel.get_selected_files()
        if not selected_files:
            self.panel.log(
                "No files selected. Use 'Select Files' or 'Select Folder' first."
            )
            return

        # Validate files exist
        from pathlib import Path

        valid_files = []
        for file_path in selected_files:
            path_obj = Path(file_path)
            if not path_obj.exists():
                self.panel.log(f"File not found: {path_obj.name}")
                continue
            if not path_obj.is_file():
                self.panel.log(f"Not a file: {path_obj.name}")
                continue
            valid_files.append(file_path)

        if not valid_files:
            self.panel.log("No valid files to ingest")
            return

        try:
            self.panel.log(f"Starting ingestion of {len(valid_files)} file(s)...")
            # Set progress bar to 0% initially (not infinite loading)
            self.panel.ingest_progress_bar.setRange(0, 100)
            self.panel.ingest_progress_bar.setValue(0)
            self.panel.ingest_status_value.setText("QUEUING")
            self.panel.ingest_step_value.setText("Submitting files for ingestion")

            # Submit to ingestion queue
            job_response = self.api.enqueue_ingest_job(valid_files)
            job_id = job_response.get("id")

            if job_id:
                self.panel.log(f"Ingestion job queued: {job_id}")
                self.panel.log(
                    f"Processing {len(valid_files)} file(s) in background..."
                )

                # Start monitoring the job
                self._start_ingest_monitoring(job_id)

                # Clear selection after successful submission
                self.panel.clear_selected_files()
                self.panel.validation_status_label.clear()
            else:
                self.panel.log("Failed to queue ingestion job")
                self.panel.ingest_progress_bar.setRange(0, 100)
                self.panel.ingest_progress_bar.setValue(0)
                self.panel.ingest_status_value.setText("FAILED")

        except Exception as e:
            self._logger.error(
                "Failed to enqueue files for ingestion: %s", e, exc_info=True
            )
            self.panel.log(f"Ingestion failed: {e}")
            self.panel.ingest_progress_bar.setRange(0, 100)
            self.panel.ingest_progress_bar.setValue(0)
            self.panel.ingest_status_value.setText("FAILED")

    def _start_ingest_monitoring(self, job_id: str) -> None:
        """Start monitoring an ingestion job by setting up the polling timer."""
        # Set the active job ID in state
        self.state.active_ingest_job_id = str(job_id)

        # Record polling start time for timeout tracking
        self._ingest_poll_start_time = dt.datetime.now(dt.timezone.utc)

        # Start the polling timer (polls every 500ms)
        self._ingest_poll_timer.start()

        self._logger.info("Started monitoring ingestion job: %s", job_id)

    def delete_asset(self, asset_data: dict) -> None:
        """Delete an asset from the database and catalog."""
        if not self._require_offline_endpoints("Delete asset"):
            return
        if not self.api.api_ready():
            self.panel.log(
                f"API unavailable at {self.api.base_url}. Start API/server desktop, then retry."
            )
            return

        asset_id = asset_data.get("id")
        filename = asset_data.get("file_name", "Unknown")

        if not asset_id:
            self.panel.log(f"Cannot delete asset: missing ID for {filename}")
            return

        try:
            self.panel.log(f"Deleting asset: {filename}...")

            # Call delete API endpoint
            success = self.api.delete_asset(asset_id)

            if success:
                self.panel.log(f"Asset deleted successfully: {filename}")

                # Clear caches and refresh the assets list
                self._clear_asset_caches()

                # Refresh the uploaded assets list to reflect the deletion
                if self.app_mode == DesktopAppMode.SERVER:
                    from qtpy.QtCore import QTimer

                    QTimer.singleShot(100, self.panel.refresh_uploaded_assets)

                # Also refresh the main assets combo if in unified/client mode
                if self.app_mode in [DesktopAppMode.UNIFIED, DesktopAppMode.CLIENT]:
                    QTimer.singleShot(200, self.refresh_assets)

            else:
                self.panel.log(f"Failed to delete asset: {filename}")

        except Exception as e:
            self._logger.error(
                "Failed to delete asset %s: %s", filename, e, exc_info=True
            )
            self.panel.log(f"Delete failed: {e}")

    def refresh_assets(self) -> None:
        if not self._require_offline_endpoints("Catalog refresh"):
            return

        # Clear all caches first to ensure fresh data
        self._clear_asset_caches()

        try:
            # Force a fresh API call without any caching
            assets = self.api.list_assets()
            assets = self._dedupe_assets(assets)

            # Log the API response for debugging
            self._logger.info(f"API returned {len(assets) if assets else 0} assets")

        except httpx.HTTPError as exc:
            self._handle_api_error("Catalog refresh", exc)
            return

        # Clear only asset-catalog caches — do NOT touch search layer state
        self.panel.assets_combo.clear()
        self._asset_cache.clear()
        self._dem_asset_kind_cache.clear()
        # NOTE: _search_result_assets_by_path and _search_layer_visibility are
        # intentionally preserved so that the Search Results table is unaffected
        # by a catalog refresh.

        # Check if assets is empty or None
        if not assets:
            self.panel.log("Catalog refreshed: 0 assets (database is empty)")
            self._logger.info("Catalog refreshed: database is empty")

            # Force refresh uploaded assets list to show empty state
            if self.app_mode == DesktopAppMode.SERVER:
                from qtpy.QtCore import QTimer

                QTimer.singleShot(100, self.panel.refresh_uploaded_assets)
            return

        for asset in assets:
            self._asset_cache[asset["file_path"]] = asset
            name_suffix = ""
            if not self._asset_path_accessible_locally(asset):
                name_suffix = " (remote)"
            label = f"{asset['file_name']} [{asset['kind']}]"
            label += name_suffix
            self.panel.assets_combo.addItem(label, asset)

        # Force refresh uploaded assets list on server mode
        if self.app_mode == DesktopAppMode.SERVER:
            # Use a small delay to ensure the API has processed any recent changes
            from qtpy.QtCore import QTimer

            QTimer.singleShot(100, lambda: self.panel.refresh_uploaded_assets())

        shown = self.panel.assets_combo.count()
        recommendation = self.performance.recommend_policy(
            asset_count=shown,
            dem_loaded=bool(self._explicit_dem_layer_visible),
        )
        self.panel.log(f"Catalog refreshed: {shown} assets")
        self.panel.log(
            "Render policy: "
            f"cache={recommendation.tile_cache_size}/terrain={recommendation.terrain_cache_size} "
            f"lod={recommendation.lod_mode}"
        )
        self._logger.info("Catalog refreshed visible=%s total=%s", shown, len(assets))
        self._logger.info("Render policy recommendation: %s", recommendation.reason)

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

        # Check for polling timeout (max 2 hours)
        if self._ingest_poll_start_time:
            elapsed = dt.datetime.now(dt.timezone.utc) - self._ingest_poll_start_time
            if elapsed.total_seconds() > 7200:  # 2 hours
                self._logger.warning(
                    "Ingest polling timeout after 2 hours, stopping polling for job %s",
                    job_id,
                )
                self.panel.log("Ingest polling timed out - job may have completed")
                self.panel.ingest_status_value.setText("TIMEOUT")
                self.panel.ingest_step_value.setText(
                    "Polling timed out - check job status manually"
                )
                self._ingest_poll_timer.stop()
                self.state.active_ingest_job_id = None
                self._ingest_poll_start_time = None
                return

        try:
            job = self.api.get_ingest_job(job_id)
        except httpx.HTTPError as exc:
            # Handle different types of HTTP errors
            if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
                status_code = exc.response.status_code
                if status_code == 404:
                    # Job not found - it was likely completed and cleaned up
                    self._logger.info("Ingest job completed and cleaned up: %s", job_id)

                    # Check if any new assets were actually added to the database
                    try:
                        current_asset_count = len(self.api.list_assets())
                        if hasattr(self, "_pre_ingest_asset_count"):
                            new_assets = (
                                current_asset_count - self._pre_ingest_asset_count
                            )
                            if new_assets > 0:
                                self.panel.log(
                                    f"Ingest completed: {new_assets} new assets added to database"
                                )
                                self.panel.ingest_step_value.setText(
                                    f"Completed: {new_assets} new assets added"
                                )
                            else:
                                self.panel.log(
                                    "Ingest completed: No new assets (files may already be in database)"
                                )
                                self.panel.ingest_step_value.setText(
                                    "Completed: No new files (duplicates skipped)"
                                )
                        else:
                            self.panel.log("Ingest job completed successfully")
                            self.panel.ingest_step_value.setText(
                                "Job completed and cleaned up"
                            )
                    except Exception:
                        self.panel.log("Ingest job completed successfully")
                        self.panel.ingest_step_value.setText(
                            "Job completed and cleaned up"
                        )

                    # Update UI to show completion
                    self.panel.ingest_status_value.setText("COMPLETED")
                    self.panel.ingest_progress_bar.setValue(100)

                    # Add informative completion message
                    self.panel.append_ingest_detail(
                        f"[COMPLETED] Job finished - check asset count for new additions"
                    )

                    # Stop polling and clear job ID
                    self._ingest_poll_timer.stop()
                    self.state.active_ingest_job_id = None
                    self._ingest_poll_start_time = None

                    # Auto-refresh the uploaded assets table when ingestion completes
                    if self.app_mode == DesktopAppMode.SERVER:
                        from qtpy.QtCore import QTimer

                        QTimer.singleShot(
                            500, lambda: self.panel.refresh_uploaded_assets()
                        )

                    return
                elif status_code >= 500:
                    # Server error - log but continue polling
                    self._logger.warning(
                        "Ingest progress refresh failed with server error %s, continuing to poll",
                        status_code,
                    )
                    return
            # For other errors, handle normally and stop polling
            self._handle_api_error("Ingest progress refresh", exc)
            self._ingest_poll_timer.stop()
            self.state.active_ingest_job_id = None
            self._ingest_poll_start_time = None
            return

        self._update_ingest_progress_ui(job, emit_detail=True)
        status = str(job.get("status") or "").lower()
        if status in {"completed", "failed", "partial"}:
            self._ingest_poll_timer.stop()
            self.state.active_ingest_job_id = None
            self._ingest_poll_start_time = None

            # Auto-refresh the uploaded assets table when ingestion completes
            if self.app_mode == DesktopAppMode.SERVER and status in {
                "completed",
                "partial",
            }:
                from qtpy.QtCore import QTimer

                QTimer.singleShot(500, lambda: self.panel.refresh_uploaded_assets())

    def stop_ingest_polling(self) -> None:
        """Manually stop ingest job polling."""
        if self._ingest_poll_timer.isActive():
            self._ingest_poll_timer.stop()
            self.state.active_ingest_job_id = None
            self._ingest_poll_start_time = None
            self.panel.log("Ingest polling stopped manually")
            self.panel.ingest_status_value.setText("STOPPED")
            self.panel.ingest_step_value.setText("Polling stopped by user")

    def _update_ingest_progress_ui(self, job: dict, *, emit_detail: bool) -> None:
        status = str(job.get("status") or "unknown").lower()
        total_items = int(job.get("total_items") or 0)
        processed_items = int(job.get("processed_items") or 0)
        failed_items = int(job.get("failed_items") or 0)
        checkpoint = int(job.get("checkpoint_item_index") or 0)
        progress_percent = int(job.get("progress_percent") or 0)
        current_step = str(
            job.get("current_step") or self._default_step_for_status(status)
        )
        current_item_path = str(job.get("current_item_path") or "")
        elapsed_seconds = job.get("elapsed_seconds")

        # Extract just the filename from the full path
        current_filename = Path(current_item_path).name if current_item_path else "-"

        # Ensure progress bar shows actual progress
        self.panel.ingest_progress_bar.setValue(max(0, min(progress_percent, 100)))
        self.panel.ingest_status_value.setText(status.upper())
        self.panel.ingest_step_value.setText(current_step)
        # Enhanced progress display with duplicate detection info
        if status.lower() == "completed" and processed_items == 0 and total_items > 0:
            # Likely all files were duplicates
            self.panel.ingest_counts_value.setText(
                f"Analyzed: {total_items} files | New: 0 | Duplicates skipped: {total_items}"
            )
        elif status.lower() == "completed" and processed_items < total_items:
            # Some files were duplicates
            skipped = total_items - processed_items - failed_items
            self.panel.ingest_counts_value.setText(
                f"Processed: {processed_items}/{total_items} | Failed: {failed_items} | Skipped: {skipped}"
            )
        else:
            # Normal progress display
            self.panel.ingest_counts_value.setText(
                f"Processed: {processed_items}/{total_items} | Failed: {failed_items}"
            )
        self.panel.ingest_item_value.setText(f"Current: {current_filename}")
        self.panel.ingest_elapsed_value.setText(
            f"Elapsed: {self._format_elapsed(elapsed_seconds)}"
        )

        # Log progress updates for debugging
        if emit_detail:
            self._logger.debug(
                "Progress update: %d%% (%d/%d processed, %d failed) - %s",
                progress_percent,
                processed_items,
                total_items,
                failed_items,
                current_step,
            )

        if emit_detail and (
            self._last_ingest_step != current_step or self._last_ingest_status != status
        ):
            self.panel.append_ingest_detail(
                f"[{self._format_elapsed(elapsed_seconds)}] {status.upper()} - {current_step}"
            )
            self._last_ingest_step = current_step
            self._last_ingest_status = status

        if emit_detail and status in {"completed", "failed", "partial"}:
            self.panel.log(
                f"Ingest job {job.get('id')} finished | Status: {status.upper()} | "
                f"Processed: {processed_items}/{total_items} | Failed: {failed_items}"
            )
            # Auto-refresh the uploaded assets table when ingestion completes
            if self.app_mode == DesktopAppMode.SERVER and status in {
                "completed",
                "partial",
            }:
                QTimer.singleShot(500, self.panel.refresh_uploaded_assets)

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
            if (
                self._asset_path_accessible_locally(item)
                or self.app_mode == DesktopAppMode.CLIENT
            ):
                return item
            self._logger.warning(
                "Combo selected asset missing on disk path=%s", item.get("file_path")
            )
            return None
        if isinstance(self.state.selected_asset, dict):
            path = self.state.selected_asset.get("file_path", "")
            if (
                self._asset_path_accessible_locally(self.state.selected_asset)
                or self.app_mode == DesktopAppMode.CLIENT
            ):
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

        # Find the best version of the file (prioritize Web Mercator projected files)
        original_file_path = asset["file_path"]
        best_file_path = self._find_best_file_version(original_file_path)

        # Update asset to use the best file version
        if best_file_path != original_file_path:
            asset = dict(asset)  # Don't mutate the original
            asset["file_path"] = best_file_path
            asset["tile_url"] = build_xyz_url(best_file_path)
            self._logger.info(
                f"Updated asset to use optimized file: {Path(best_file_path).name}"
            )
        else:
            self._logger.debug(
                f"Using original asset file: {Path(original_file_path).name}"
            )

        if (
            self.app_mode != DesktopAppMode.CLIENT
            and not Path(asset["file_path"]).exists()
        ):
            self.panel.log(f"File not found on disk: {asset['file_path']}")
            self._logger.error(
                "Cannot add layer; file missing path=%s", asset["file_path"]
            )
            if show_loading:
                self._set_layer_loading(False, "Layer load failed")
            return None

        # Auto-convert to COG if the source is a plain GeoTIFF.
        # Non-COG files fail to tile on Windows and are slower everywhere.
        # The COG is written next to the source (e.g. dem.cog.tif) and reused.
        if self.app_mode != DesktopAppMode.CLIENT:
            try:
                from core_shared.ingestion.services.cog_service import (
                    CogPreparationService,
                )

                src_path = Path(asset["file_path"])
                self._logger.info(
                    "COG check: %s is_cog=%s",
                    src_path.name,
                    CogPreparationService._looks_like_cog(src_path),
                )
                if not CogPreparationService._looks_like_cog(src_path):
                    self.panel.log(
                        f"Converting to COG for fast tiling: {src_path.name}…"
                    )
                    if show_loading:
                        self._set_layer_loading(
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
                    asset["tile_url"] = build_xyz_url(str(cog_result.working_path))
                    self._logger.info("COG tile_url updated to: %s", asset["tile_url"])
                    if cog_result.converted:
                        self.panel.log(f"COG ready: {cog_result.working_path.name}")
            except Exception:
                self._logger.warning("COG preparation failed", exc_info=True)
        if not self.titiler.ensure_running():
            detail = getattr(self.titiler, "last_error", "") or ""
            if detail:
                self.panel.log("TiTiler failed to start: " + detail.strip())
                self._logger.error(
                    "TiTiler unavailable before add layer: %s", detail.strip()
                )
            else:
                self.panel.log("Warning: TiTiler could not start. Layer may not draw.")
                self._logger.error("TiTiler unavailable before add layer")
        bounds = self._asset_bounds(asset)
        if bounds is None:
            try:
                fresh = self.api.register_raster(asset["file_path"])
                self._asset_cache[fresh["file_path"]] = fresh
                asset = fresh
                bounds = self._asset_bounds(asset)
                self._logger.info(
                    "Refreshed metadata for selected asset before layer add"
                )
            except httpx.HTTPError:
                self._logger.exception("Failed to refresh metadata before layer add")
        options = self._layer_options(asset, bounds)
        options["replace_existing"] = bool(replace_existing)
        if layer_key:
            options["layer_key"] = str(layer_key).replace("\\", "/")
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

        self._run_js_call(
            "flyThroughBounds",
            bounds["west"],
            bounds["south"],
            bounds["east"],
            bounds["north"],
        )
        return True

    def _try_visualize_ingested_asset(self) -> None:
        """Try to visualize newly ingested assets with event-driven server-side processing.

        For folder ingests, loads up to 5 most recent assets automatically.
        Uses server-side metadata processing for ultra-high performance with terabyte-scale data.
        All processing happens on server, client only requests metadata and tile URLs.
        """
        source_path = self.state.pending_ingest_source_path
        if not source_path:
            return

        # Event-driven approach: Request server to process and return optimized metadata
        try:
            # Server-side metadata processing for terabyte-scale performance
            assets = self._request_server_processed_assets(source_path)
        except httpx.HTTPError as exc:
            self._handle_api_error("Load ingested asset", exc)
            return

        self.refresh_assets()

        # Check if source_path is a folder
        source_path_obj = Path(source_path)
        is_folder = source_path_obj.is_dir()

        if is_folder:
            # Server-side folder processing for terabyte-scale data
            matching_assets = self._get_server_processed_folder_assets(
                assets, source_path_obj
            )

            if not matching_assets:
                self.panel.log(
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

            self.panel.log(
                f"Auto-loading {len(assets_to_load)} most recent asset(s) from {len(matching_assets)} total"
            )

            # Event-driven layer loading with server-side tile preparation
            self._load_assets_event_driven(assets_to_load)
        else:
            # Single file ingest with server-side processing
            match = self._find_server_processed_asset(assets, source_path)

            if not isinstance(match, dict):
                self.panel.log(
                    "Ingest completed, but catalog item is not yet visible. Use Refresh Assets."
                )
                self._logger.info(
                    "Ingest completed but asset not found in catalog yet source=%s (this is normal for large files)",
                    source_path,
                )
                return

            # Event-driven single asset loading
            self._load_single_asset_event_driven(match)

        self.state.auto_visualize_ingest_result = False
        self.state.pending_ingest_source_path = None

    def _request_server_processed_assets(self, source_path: str) -> list[dict]:
        """Request server to process and return optimized asset metadata."""
        try:
            # Use existing API but with server-side optimization hints
            assets = self.api.list_assets()
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
        # Strategy 1: Server-side exact path matching
        match = next(
            (
                asset
                for asset in assets
                if self._paths_equivalent(
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
        import time

        start_time = time.time()

        for idx, match in enumerate(assets_to_load):
            self._asset_cache[match["file_path"]] = match
            self.state.selected_asset = match

            # Track terabyte-scale assets
            if match.get("performance_tier") == "ultra_large":
                self._terabyte_scale_assets_loaded += 1

            # Request server-side tile preparation and optimization
            options = self._get_server_optimized_layer_options(match)

            if idx == 0:
                # For first asset, show loading indicator and fly to it
                self._set_layer_loading(True, f"Loading {match['file_name']}...")
                if self._add_layer_event_driven(match, options):
                    self._fly_through_asset_event_driven(match)
                else:
                    self._set_layer_loading(False, "Layer load failed")
            else:
                # For subsequent assets, just add them without flying
                self._add_layer_event_driven(match, options)

            self.panel.log(f"Auto-loaded: {match['file_name']}")

        # Track performance
        load_time = time.time() - start_time
        self._track_performance_metric(
            "layer_load_times", load_time, f"{len(assets_to_load)} assets"
        )

    def _load_single_asset_event_driven(self, match: dict) -> None:
        """Load single asset using event-driven architecture."""
        import time

        start_time = time.time()

        self._asset_cache[match["file_path"]] = match
        self.state.selected_asset = match

        # Track terabyte-scale assets
        if match.get("performance_tier") == "ultra_large":
            self._terabyte_scale_assets_loaded += 1

        # Request server-side optimization
        options = self._get_server_optimized_layer_options(match)

        self._set_layer_loading(True, f"Loading {match['file_name']}...")
        if self._add_layer_event_driven(match, options):
            self._fly_through_asset_event_driven(match)
        else:
            self._set_layer_loading(False, "Layer load failed")
        self.panel.log(f"Auto-loaded ingested asset: {match['file_name']}")

        # Track performance
        load_time = time.time() - start_time
        self._track_performance_metric(
            "layer_load_times", load_time, f"single asset: {match['file_name']}"
        )

    def _get_server_optimized_layer_options(self, asset: dict) -> dict:
        """Get layer options optimized by server-side processing."""
        bounds = self._asset_bounds(asset)
        options = self._layer_options(asset, bounds)

        # Add server-side optimization hints for terabyte-scale data
        options["server_optimized"] = True
        options["tile_cache_strategy"] = "aggressive"
        options["memory_efficient"] = True

        return options

    def _add_layer_event_driven(self, asset: dict, options: dict) -> bool:
        """Add layer using event-driven architecture with server-side processing."""
        # Test JavaScript bridge connectivity first
        if not self._test_js_bridge_connectivity():
            self._logger.warning(
                "JavaScript bridge connectivity test failed, falling back to standard layer loading"
            )
            self.panel.log(
                "Warning: JavaScript bridge issue detected, using fallback method"
            )
            return self._add_layer(asset, options)

        # Use existing _add_layer but with server optimization flags
        options["event_driven"] = True
        return self._add_layer(asset, options)

    def _fly_through_asset_event_driven(self, asset: dict) -> bool:
        """Fly through asset using server-optimized bounds."""
        # Use server-provided bounds for smooth navigation
        return self._fly_through_asset(asset)

    def apply_rgb_view_mode(self) -> None:
        self._viz.apply_rgb_view_mode()

    def _on_visual_slider_changed(self, _value: int) -> None:
        self._viz.on_visual_slider_changed(_value)

    def _on_dem_slider_changed(self, _value: int) -> None:
        self._viz.on_dem_slider_changed(_value)

    def _on_dem_color_mode_changed(self, _index: int) -> None:
        self._viz.apply_dem_color_mode(log_to_panel=True)

    def apply_visual_settings(self, log_to_panel: bool = True) -> None:
        self._viz.apply_visual_settings(log_to_panel=log_to_panel)

    def apply_dem_settings(
        self, _checked: bool | None = None, log_to_panel: bool = True
    ) -> None:
        self._viz.apply_dem_settings(_checked=_checked, log_to_panel=log_to_panel)

    def apply_dem_color_mode(self, log_to_panel: bool = True) -> None:
        self._viz.apply_dem_color_mode(log_to_panel=log_to_panel)

    def rotate_camera(self, degrees: float) -> None:
        self._viz.rotate_camera(degrees)

    def set_pitch(self, degrees: int) -> None:
        # Debounce: buffer rapid slider events, only fire after 80ms of silence.
        # Without this, the log shows 30-50 queued setPitch calls that all execute
        # on the JS thread AFTER the user has stopped — causing camera jumps.
        self._pending_pitch_degrees = int(degrees)
        if not hasattr(self, "_pitch_debounce_timer"):
            from PyQt5.QtCore import QTimer
            self._pitch_debounce_timer = QTimer()
            self._pitch_debounce_timer.setSingleShot(True)
            self._pitch_debounce_timer.timeout.connect(self._flush_pitch)
        self._pitch_debounce_timer.stop()
        self._pitch_debounce_timer.start(80)
        import logging
        logging.getLogger("desktop.controller").info(
            "set_pitch called: degrees=%d", degrees
        )

    def _flush_pitch(self) -> None:
        deg = getattr(self, "_pending_pitch_degrees", None)
        if deg is not None:
            self._viz.set_pitch(deg)


    def on_map_click(self, lon: float, lat: float) -> None:
        self.state.clicked_points.append((lon, lat))
        self.state.clicked_points = self.state.clicked_points[-2:]
        self.panel.click_label.setText(f"Last click: lon={lon:.6f}, lat={lat:.6f}")

        # Route to elevation profile coordinator first (it manages its own click state)
        if self._elevation_profile.active:
            self._elevation_profile.on_map_click(lon, lat)
            return

        if self._add_point_mode_enabled:
            self._add_annotation_at(lon, lat)
            return

        if self._viewshed_mode_enabled:
            self.panel.log(
                f"Observer point selected at lon={lon:.6f}, lat={lat:.6f}. Computing viewshed..."
            )
            self._toolbar_measure_viewshed()
            self.state.clicked_points.clear()
            return

        if self._shadow_height_mode_enabled:
            if len(self.state.clicked_points) < 2:
                self.panel.log(
                    "Shadow Height: base point captured. Click shadow tip point."
                )
                return
            self._toolbar_measure_shadow_height()
            self.state.clicked_points.clear()

    def on_measurement(self, meters: float) -> None:
        self.panel.measure_label.setText(f"Last distance: {meters:.2f} m")
        self._logger.info("Measurement updated distance_m=%.2f", meters)
        if not self._distance_measure_mode_enabled:
            return
        if len(self.state.clicked_points) < 2:
            return
        (lon1, lat1), (lon2, lat2) = (
            self.state.clicked_points[-2],
            self.state.clicked_points[-1],
        )
        signature = (
            round(lon1, 7),
            round(lat1, 7),
            round(lon2, 7),
            round(lat2, 7),
            round(meters, 2),
        )
        if signature == self._last_distance_measurement_signature:
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
        text = self._default_annotation_text
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

    def _toolbar_elevation_profile(self) -> bool:
        """Activate elevation profile two-click mode via the coordinator."""
        if self._elevation_profile.active:
            # Second click on button cancels the mode and clears all map overlays
            self._elevation_profile.deactivate()
            self.panel.log("Elevation Profile stopped.")
            return False
        activated = self._elevation_profile.activate()
        return activated

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
        samples = int(self._default_profile_samples)
        try:
            result = self.api.extract_profile(
                asset["file_path"], self.state.clicked_points[-2:], samples=samples
            )
        except httpx.HTTPError as exc:
            self.panel.log(f"Profile extraction failed: {exc}")
            self._logger.exception(
                "Profile extraction failed path=%s", asset["file_path"]
            )
            return
        values = result.get("values", [])
        if not values:
            self.panel.log("Profile extraction returned no values.")
            self._logger.warning(
                "Profile returned empty values path=%s", asset["file_path"]
            )
            return
        self._last_profile_values = [float(v) for v in values]
        preview = ", ".join(f"{v:.2f}" for v in values[:10])
        self.panel.log(
            f"Profile extracted ({len(values)} samples). First values: {preview}"
        )
        self._logger.info(
            "Profile extracted samples=%s path=%s", len(values), asset["file_path"]
        )

    def on_toolbar_group_disabled(self, group_name: str) -> None:
        if group_name == "measurement":
            self._distance_measure_mode_enabled = False
            self._add_point_mode_enabled = False
            self._set_annotation_overlay_visible(False)
            self._shadow_height_mode_enabled = False
            self._pan_mode_enabled = True
            self._run_js_call("setDistanceMeasureMode", False)
            self._run_js_call("setSearchDrawMode", "none")
            self._run_js_call("setPanMode", True)
            self._run_js_call("clearMeasurements")
            self.clear_all_measurement_results()
            self.panel.log(
                "Measurement toolbar disabled: measurement overlays cleared."
            )
            return
        if group_name == "visualization":
            if self._swipe_comparator_enabled:
                self._swipe_comparator_enabled = False
                self._run_js_call("setComparator", False)
            self.panel.log("Visualization toolbar disabled.")

    def handle_toolbar_action(
        self, action_label: str, checked: bool | None = None
    ) -> bool | None:
        return self._toolbar_actions.handle_toolbar_action(action_label, checked)

    def available_comparator_layer_options(self) -> list[dict[str, object]]:
        return self._comparator.available_comparator_layer_options()

    def available_swipe_layer_options(self) -> list[dict[str, object]]:
        return self._comparator.available_swipe_layer_options()

    def apply_comparator_selection(self, selected_paths: list[str]) -> bool:
        return self._comparator.apply_comparator_selection(selected_paths)

    def apply_swipe_comparator_selection(self, selected_paths: list[str]) -> bool:
        return self._comparator.apply_swipe_comparator_selection(selected_paths)

    def _visible_imagery_layer_paths(self) -> list[str]:
        return self._comparator._visible_imagery_layer_paths()

    def _available_imagery_layer_paths(self) -> list[str]:
        return self._comparator._available_imagery_layer_paths()

    def _visible_dem_layer_count(self) -> int:
        return self._comparator._visible_dem_layer_count()

    def comparator_candidate_count(self) -> int:
        return self._comparator.comparator_candidate_count()

    def swipe_comparator_candidate_count(self) -> int:
        return self._comparator.swipe_comparator_candidate_count()

    def can_enable_comparator(self) -> bool:
        return self._comparator.can_enable_comparator()

    def can_enable_swipe_comparator(self) -> bool:
        return self._comparator.can_enable_swipe_comparator()

    def can_attempt_enable_comparator(self) -> bool:
        return self._comparator.can_attempt_enable_comparator()

    def can_attempt_enable_swipe_comparator(self) -> bool:
        return self._comparator.can_attempt_enable_swipe_comparator()

    def _auto_enable_second_comparator_imagery_layer(self) -> bool:
        return self._comparator._auto_enable_second_comparator_imagery_layer()

    def _auto_enable_second_swipe_imagery_layer(self) -> bool:
        return self._comparator._auto_enable_second_swipe_imagery_layer()

    def _enqueue_distance_measurement(
        self, lon1: float, lat1: float, lon2: float, lat2: float
    ) -> None:
        self._measure.enqueue_distance_measurement(lon1, lat1, lon2, lat2)

    def _submit_measurement_job(
        self, name: str, task: Callable[[], object], formatter: Callable[[object], str]
    ) -> None:
        self._measure.submit_measurement_job(name, task, formatter)

    def _set_measurement_done_hook(
        self, name: str, hook: Callable[[], None] | None
    ) -> None:
        if hook is None:
            self._measurement_done_hooks.pop(name, None)
            return
        self._measurement_done_hooks[name] = hook

    def _on_measurement_named_job_done(self, name: str) -> None:
        hook = self._measurement_done_hooks.pop(name, None)
        if callable(hook):
            hook()

    def _on_measurement_job_finished(
        self,
        name: str,
        result: object,
        error: str,
        formatter: Callable[[object], str],
    ) -> None:
        self._measure.on_measurement_job_finished(name, result, error, formatter)
        self._on_measurement_named_job_done(name)

    def _record_measurement_result(self, name: str, details: str) -> None:
        self._measure.record_measurement_result(name, details)

    def clear_selected_measurement_result(self) -> None:
        self._measure.clear_selected_measurement_result()

    def clear_all_measurement_results(self) -> None:
        self._measure.clear_all_measurement_results()

    def _selected_dem_path(self) -> str | None:
        return self._measure.selected_dem_path()

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

    def _toolbar_toggle_comparator(self, enabled: bool | None = None) -> bool:
        return self._comparator._toolbar_toggle_comparator(enabled=enabled)

    def _toolbar_toggle_swipe_comparator(self, enabled: bool | None = None) -> bool:
        return self._comparator._toolbar_toggle_swipe_comparator(enabled=enabled)

    def disable_layer_compositor(self) -> None:
        self._run_js_call("setSwipeComparator", False)
        self.panel.log("Layer Compositor disabled.")

    def apply_layer_compositor_settings(
        self, enable_swipe: bool, swipe_paths: list[str], layer_alphas: dict[str, float]
    ) -> bool:
        for path, alpha in layer_alphas.items():
            asset = self._search_result_assets_by_path.get(path)
            if asset:
                layer_key = path
                self._run_js_call("setLayerAlpha", layer_key, alpha)

        if enable_swipe and len(swipe_paths) >= 2:
            left_path, right_path = swipe_paths[0], swipe_paths[1]
            left_asset = self._search_result_assets_by_path.get(left_path) or {}
            right_asset = self._search_result_assets_by_path.get(right_path) or {}
            left_label = str(
                left_asset.get("file_name") or Path(left_path).name or "Layer A"
            )
            right_label = str(
                right_asset.get("file_name") or Path(right_path).name or "Layer B"
            )
            self._run_js_call(
                "setSwipeComparatorLayers",
                left_path,
                right_path,
                left_label,
                right_label,
            )
            self._run_js_call("setSwipeComparator", True)
        else:
            self._run_js_call("setSwipeComparator", False)

        self.panel.log("Layer compositor settings applied.")
        return True

    def _toolbar_measure_distance(self, enabled: bool | None = None) -> bool:
        self._distance_measure_mode_enabled = (
            (not self._distance_measure_mode_enabled)
            if enabled is None
            else bool(enabled)
        )
        if self._distance_measure_mode_enabled:
            self._add_point_mode_enabled = False
            self._set_annotation_overlay_visible(False)
            self._shadow_height_mode_enabled = False
        self._pan_mode_enabled = not self._distance_measure_mode_enabled
        self._last_distance_measurement_signature = None
        if self._distance_measure_mode_enabled:
            # Disable pan mode in JS so clicks reach the distance tool handler
            self._run_js_call("setPanMode", False)
            self._run_js_call("setSearchDrawMode", "none")
        self._run_js_call("setDistanceMeasureMode", self._distance_measure_mode_enabled)
        if not self._distance_measure_mode_enabled:
            self.panel.log("Distance tool disabled.")
            self._logger.info("Distance measure mode disabled")
            return False
        self.state.clicked_points.clear()
        self._run_js_call("clearMeasurementEntities")
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
                self._set_annotation_overlay_visible(False)
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
            # Disable conflicting modes
            self._distance_measure_mode_enabled = False
            self._run_js_call("setDistanceMeasureMode", False)
            self._add_point_mode_enabled = False
            self._set_annotation_overlay_visible(False)
            self._shadow_height_mode_enabled = False
            self._viewshed_mode_enabled = False
            self._volume_mode_enabled = False
            self._pan_mode_enabled = False
            self._run_js_call("setAnnotationDrawingMode", False)

            # Enable polygon drawing mode for measurement
            self._polygon_drawing_context = "measurement"
            self._polygon_area_mode_enabled = True
            self.set_search_draw_mode(enabled=True)
            self._set_measurement_cursor_enabled(True)
            self.panel.log(
                "Draw a polygon on the map, then click Finish to calculate area."
            )
            return

        def task() -> object:
            dem_path = self._selected_dem_path()
            return measure_polygon_area(polygon, dem_path=dem_path)

        def formatter(result: object) -> str:
            m = result
            compactness = m.compactness_index
            return (
                "Polygon Area: "
                f"planimetric={m.planimetric_area_m2:.2f} m2, perimeter={m.perimeter_m:.2f} m, compactness={compactness:.4f}"
            )

        self._submit_measurement_job("Polygon Area", task, formatter)
        # Clear the measurement mode flag after calculation
        self._polygon_area_mode_enabled = False
        self._polygon_drawing_context = "none"
        self._set_measurement_cursor_enabled(False)

    def _toolbar_measure_volume(self) -> bool | None:
        self._logger.info(
            "FillVolume: enter computing=%s active=%s",
            getattr(self, "_fill_volume_computing", False),
            getattr(self, "_fill_volume_active", False),
        )
        # Guard: ignore clicks while analysis is already running
        if getattr(self, "_fill_volume_computing", False):
            self.panel.log("Fill Volume: analysis in progress, please wait")
            return True  # keep button highlighted

        # Toggle off: clear overlays, keep polygon for re-use on next tap
        if getattr(self, "_fill_volume_active", False):
            self._logger.info("FillVolume: toggling off")
            self._fill_volume_active = False
            self._fill_volume_computing = False
            self._volume_mode_enabled = False
            self._set_measurement_cursor_enabled(False)
            self._polygon_drawing_context = "none"
            self._run_js_call("clearFillVolumes")
            self.panel.log("Fill Volume: off (polygon kept — tap again to re-analyse)")
            return False

        self._logger.info("FillVolume: checking DEM path")
        # Need a DEM
        dem_path = self._selected_dem_path()
        if not dem_path:
            self.panel.log("Select or show a DEM layer first.")
            return False

        self._logger.info("FillVolume: getting polygon dem_path=%s", dem_path)
        # Get polygon — use existing drawn polygon, or auto-derive from DEM bounds
        polygon = self._current_polygon_lonlat()
        if not polygon:
            polygon = self._dem_bounds_polygon(dem_path)

        self._logger.info("FillVolume: polygon=%s", "found" if polygon else "none")

        if not polygon:
            # No DEM bounds available — fall back to draw mode
            self._logger.info("FillVolume: no polygon, entering draw mode")
            self._distance_measure_mode_enabled = False
            self._run_js_call("setDistanceMeasureMode", False)
            self._add_point_mode_enabled = False
            self._set_annotation_overlay_visible(False)
            self._shadow_height_mode_enabled = False
            self._viewshed_mode_enabled = False
            self._polygon_area_mode_enabled = False
            self._pan_mode_enabled = False
            self._polygon_drawing_context = "measurement"
            self._volume_mode_enabled = True
            self._fill_volume_active = False
            self.set_search_draw_mode(enabled=True)
            self.panel.log("Fill Volume: draw a polygon on the DEM, then click Finish")
            return True

        # Polygon ready — submit analysis
        self._logger.info(
            "FillVolume: submitting analysis polygon_pts=%d", len(polygon)
        )
        self._fill_volume_computing = True

        # Wire a one-shot relay so the worker thread can safely post progress
        # to the main thread without calling emit() directly across threads
        # (direct cross-thread emit is undefined behaviour in Qt and causes
        # segfaults on repeated invocations).
        # We use a small QObject relay whose signal is connected with
        # Qt.QueuedConnection — Qt then marshals the call onto the main thread.
        from qtpy.QtCore import QObject, Signal as _Signal, Qt as _Qt

        class _ProgressRelay(QObject):
            progress = _Signal(int, str)

        relay = _ProgressRelay()
        relay.progress.connect(
            self.bridge.on_loading_progress,
            _Qt.ConnectionType.QueuedConnection,
        )

        def task(_relay=relay) -> object:
            # _relay kept alive via default-arg capture for the worker's lifetime
            def progress_cb(pct: float, msg: str) -> None:
                _relay.progress.emit(int(pct), f"Fill Volume: {msg}")

            return compute_fill_volume(polygon, dem_path, progress_callback=progress_cb)

        def formatter(result: object) -> str:
            from desktop_client.client_backend.measurement_tools.models import (
                FillVolumeResult,
            )

            if not isinstance(result, FillVolumeResult):
                return "Fill Volume: no result"
            n = len(result.regions)
            total = sum(r.fill_volume_m3 for r in result.regions)
            if n == 0:
                return (
                    f"Fill Volume: no depressions found "
                    f"(ref={result.reference_elevation_m:.1f} m, "
                    f"void={100 * result.void_fraction:.1f}%)"
                )
            lines = [
                f"Fill Volume: {n} depression(s) found, "
                f"total fill={_fmt_vol(total)}, "
                f"ref={result.reference_elevation_m:.1f} m"
            ]
            for r in result.regions[:5]:
                lines.append(
                    f"  Region {r.region_id}: fill={_fmt_vol(r.fill_volume_m3)}, "
                    f"area={r.area_m2:.0f} m², depth max={r.max_depth_m:.2f} m"
                )
            return "\n".join(lines)

        def on_done(name: str, result: object, error: str, fmt) -> None:
            self._logger.info(
                "FillVolume: on_done called error=%s result_type=%s",
                error or "none",
                type(result).__name__,
            )
            self._fill_volume_computing = False
            self._active_fill_volume_worker = None  # release worker reference
            self._active_fill_volume_pool = None  # release pool reference
            self.bridge.loadingProgress.emit(100, "Fill Volume: Complete")
            self._measure.on_measurement_job_finished(name, result, error, fmt)
            if error or result is None:
                self._fill_volume_active = False
                return
            from desktop_client.client_backend.measurement_tools.models import (
                FillVolumeResult,
            )

            if not isinstance(result, FillVolumeResult) or not result.regions:
                self._run_js_call("clearFillVolumes")
                self._fill_volume_active = False
                return
            regions_payload = [
                {
                    "id": r.region_id,
                    "fill_volume_m3": r.fill_volume_m3,
                    "area_m2": r.area_m2,
                    "max_depth_m": r.max_depth_m,
                    "mean_depth_m": r.mean_depth_m,
                    "reference_elevation_m": r.reference_elevation_m,
                    "rim_elevation_m": r.rim_elevation_m,
                    "centroid_lon": r.centroid_lon,
                    "centroid_lat": r.centroid_lat,
                    "outline": [
                        {"lon": lon, "lat": lat} for lon, lat in r.outline_lonlat
                    ],
                }
                for r in result.regions
            ]
            self._run_js_call("drawFillVolumes", json.dumps(regions_payload))
            self._fill_volume_active = True

        from qtpy.QtCore import Qt, QThreadPool
        from desktop_client.client_backend.desktop.measurement_worker import (
            MeasurementWorker,
        )

        worker = MeasurementWorker(name="Fill Volume", task=task)
        # Keep a strong Python reference so the worker (and its signals QObject)
        # stays alive until on_done fires and clears it.
        self._active_fill_volume_worker = worker
        # Use a dedicated parentless pool per analysis — avoids bus error on macOS
        # caused by QThreadPool(parent=QWidget) thread state corruption across runs.
        pool = QThreadPool()
        pool.setMaxThreadCount(1)
        self._active_fill_volume_pool = pool
        self._logger.info(
            "FillVolume: worker created id=%s pool_active=%s",
            id(worker),
            pool.activeThreadCount(),
        )
        worker.signals.finished.connect(
            lambda job_name, res, err, fmt=formatter: on_done(job_name, res, err, fmt),
            Qt.QueuedConnection,
        )
        self.bridge.loadingProgress.emit(0, "Fill Volume: Starting analysis")
        self._logger.info("FillVolume: calling pool.start")
        pool.start(worker)
        self._logger.info("FillVolume: pool.start returned")
        self.panel.log("Fill Volume: Starting analysis")
        self._volume_mode_enabled = False
        self._polygon_drawing_context = "none"
        self._set_measurement_cursor_enabled(False)
        return True  # keep button highlighted while computing

    def _dem_bounds_polygon(self, dem_path: str) -> list[tuple[float, float]] | None:
        """Return a bounding-box polygon for the active DEM asset, or None."""
        # Try to get bounds from the asset cache
        for path, asset in self._asset_cache.items():
            if str(asset.get("file_path") or "") == dem_path and self._is_dem_asset(
                asset
            ):
                bounds = self._asset_bounds(asset)
                if bounds:
                    w, s, e, n = (
                        bounds["west"],
                        bounds["south"],
                        bounds["east"],
                        bounds["north"],
                    )
                    return [(w, s), (e, s), (e, n), (w, n), (w, s)]
        for path, asset in self._search_result_assets_by_path.items():
            if str(asset.get("file_path") or "") == dem_path and self._is_dem_asset(
                asset
            ):
                bounds = self._asset_bounds(asset)
                if bounds:
                    w, s, e, n = (
                        bounds["west"],
                        bounds["south"],
                        bounds["east"],
                        bounds["north"],
                    )
                    return [(w, s), (e, s), (e, n), (w, n), (w, s)]
        # Fallback: read bounds directly from the raster file
        try:
            import rasterio
            from pyproj import Transformer as _T

            with rasterio.open(dem_path) as src:
                b = src.bounds
                crs = src.crs
                if crs and not crs.is_geographic:
                    t = _T.from_crs(crs, "EPSG:4326", always_xy=True)
                    w, s = t.transform(b.left, b.bottom)
                    e, n = t.transform(b.right, b.top)
                else:
                    w, s, e, n = b.left, b.bottom, b.right, b.top
            return [(w, s), (e, s), (e, n), (w, n), (w, s)]
        except Exception:
            return None

        # Guard while computing
        if getattr(self, "_slope_aspect_computing", False):
            self.panel.log("Slope & Aspect: analysis in progress, please wait")
            return True

        # Need a DEM
        dem_path = self._selected_dem_path()
        if not dem_path:
            self.panel.log("Select or show a DEM layer first.")
            return False

        # Switch DEM colour mode to slope if not already slope/aspect
        mode = str(self.panel.dem_color_mode_combo.currentData() or "gray")
        if mode not in {"slope", "aspect"}:
            idx = self.panel.dem_color_mode_combo.findData("slope")
            if idx >= 0:
                self.panel.dem_color_mode_combo.setCurrentIndex(idx)
                self._viz.apply_dem_color_mode(log_to_panel=False)

        # No polygon yet — enter draw mode
        polygon = self._current_polygon_lonlat()
        if not polygon:
            self._distance_measure_mode_enabled = False
            self._run_js_call("setDistanceMeasureMode", False)
            self._add_point_mode_enabled = False
            self._set_annotation_overlay_visible(False)
            self._volume_mode_enabled = False
            self._polygon_area_mode_enabled = False
            self._pan_mode_enabled = False
            self._polygon_drawing_context = "measurement"
            self._slope_aspect_mode_enabled = True
            self.set_search_draw_mode(enabled=True)
            self._set_measurement_cursor_enabled(True)
            self.panel.log(
                "Draw a polygon on the map, then click Finish to calculate slope & aspect."
            )
            return True

        # Polygon ready — run async
        self._slope_aspect_computing = True
        self._polygon_drawing_context = "none"
        self._set_measurement_cursor_enabled(False)

        from qtpy.QtCore import QObject, Signal as _Signal, Qt as _Qt

        class _Relay(QObject):
            progress = _Signal(int, str)

        relay = _Relay()
        relay.progress.connect(
            self.bridge.on_loading_progress,
            _Qt.ConnectionType.QueuedConnection,
        )

        def task(_relay=relay) -> object:
            def _cb(pct: float, msg: str) -> None:
                _relay.progress.emit(int(pct), f"Slope & Aspect: {msg}")

            _cb(5, "Starting")
            result = compute_slope_aspect(polygon, dem_path)
            _cb(95, "Finalising")
            return result

        def formatter(result: object) -> str:
            m = result
            area_txt = ", ".join(
                f"{k}:{v:.1f}m²" for k, v in m.area_by_class_m2.items()
            )
            return (
                f"Slope & Aspect: mean={m.mean_slope_deg:.2f}°, "
                f"std={m.std_slope_deg:.2f}°, max={m.max_slope_deg:.2f}°; "
                f"classes[{area_txt}]"
            )

        def on_done(name: str, result: object, error: str, fmt) -> None:
            self._active_slope_aspect_worker = None
            self._active_slope_aspect_pool = None
            self.bridge.loadingProgress.emit(100, "Slope & Aspect: Complete")
            self._measure.on_measurement_job_finished(name, result, error, fmt)
            callback = getattr(self, "_on_slope_aspect_done", None)
            if callable(callback):
                callback()

        from qtpy.QtCore import Qt, QThreadPool
        from desktop_client.client_backend.desktop.measurement_worker import (
            MeasurementWorker,
        )

        worker = MeasurementWorker(name="Slope & Aspect", task=task)
        self._active_slope_aspect_worker = worker
        pool = QThreadPool()
        pool.setMaxThreadCount(1)
        self._active_slope_aspect_pool = pool
        worker.signals.finished.connect(
            lambda job_name, res, err, fmt=formatter: on_done(job_name, res, err, fmt),
            Qt.QueuedConnection,
        )
        self.bridge.loadingProgress.emit(0, "Slope & Aspect: Starting")
        pool.start(worker)
        self.panel.log("Slope & Aspect: Starting analysis")
        return True  # keep button highlighted

    def _toolbar_measure_viewshed(self) -> None:
        dem_path = self._selected_dem_path()
        if not dem_path:
            self.panel.log("Select or show a DEM layer first.")
            return
        if not self.state.clicked_points:
            # Disable conflicting modes
            self._distance_measure_mode_enabled = False
            self._run_js_call("setDistanceMeasureMode", False)
            self._add_point_mode_enabled = False
            self._set_annotation_overlay_visible(False)
            self._shadow_height_mode_enabled = False
            self._polygon_area_mode_enabled = False
            self._volume_mode_enabled = False
            self._run_js_call("setSearchDrawMode", "none")
            self._polygon_drawing_context = "none"
            self._pan_mode_enabled = False

            # Enable viewshed mode
            self._viewshed_mode_enabled = True
            self._set_measurement_cursor_enabled(True)
            self.panel.log(
                "Click on the map to select observer point for viewshed analysis."
            )
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
        self._viewshed_mode_enabled = False
        self._set_measurement_cursor_enabled(False)

    def _toolbar_measure_shadow_height(self) -> None:
        if len(self.state.clicked_points) < 2:
            self.panel.log(
                "Click object base and shadow tip points before Shadow Height."
            )
            return
        dem_path = self._selected_dem_path()
        (base_lon, base_lat), (tip_lon, tip_lat) = (
            self.state.clicked_points[-2],
            self.state.clicked_points[-1],
        )
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
            h = (
                m.corrected_height_m
                if m.corrected_height_m is not None
                else m.estimated_height_m
            )
            warn = f" warning={m.warning}" if m.warning else ""
            return (
                "Shadow Height: "
                f"height={h:.2f} m +/- {m.uncertainty_m:.2f} m, sun_elev={m.solar_elevation_deg:.2f} deg, "
                f"sun_az={m.solar_azimuth_deg:.2f} deg, reliable={m.reliable}{warn}"
            )

        self._submit_measurement_job("Shadow Height", task, formatter)

    def _toolbar_toggle_shadow_height_mode(self, enabled: bool | None = None) -> bool:
        next_state = (
            (not self._shadow_height_mode_enabled) if enabled is None else bool(enabled)
        )
        self._shadow_height_mode_enabled = next_state
        if not next_state:
            self.panel.log("Shadow Height tool disabled.")
            self._set_measurement_cursor_enabled(False)
            return False

        self._distance_measure_mode_enabled = False
        self._add_point_mode_enabled = False
        self._set_annotation_overlay_visible(False)
        self._pan_mode_enabled = False
        self.state.clicked_points.clear()
        self._run_js_call("setDistanceMeasureMode", False)
        self._run_js_call("setSearchDrawMode", "none")
        self._run_js_call("setPanMode", False)
        self._set_measurement_cursor_enabled(True)
        self.panel.log(
            "Shadow Height enabled. Click base point, then shadow tip point."
        )
        return True

    def _toolbar_toggle_add_point_mode(self, enabled: bool | None = None) -> bool:
        next_state = (
            (not self._add_point_mode_enabled) if enabled is None else bool(enabled)
        )
        self._add_point_mode_enabled = next_state
        if not next_state:
            # Don't hide placed annotations — they are persistent data
            self._set_measurement_cursor_enabled(False)
            self.panel.log("Add Point tool disabled.")
            return False

        # Disable conflicting modes (exclusivity enforced per user request)
        self._distance_measure_mode_enabled = False
        self._shadow_height_mode_enabled = False
        self._pan_mode_enabled = False
        self._add_point_mode_enabled = True # Current mode
        self._run_js_call("setDistanceMeasureMode", False)
        self._run_js_call("setPanMode", False)
        self._run_js_call("setSearchDrawMode", "none") # Disable Polygon Draw
        self._set_measurement_cursor_enabled(True)
        self._set_annotation_overlay_visible(True)
        self.panel.log("Add Point enabled. Click map to place annotation points.")
        return True

    def _toolbar_clear_last(self) -> None:
        if self.state.clicked_points:
            self.state.clicked_points = self.state.clicked_points[:-1]
        # Tell JS to undo the last point without exiting the drawing mode
        self._run_js_call("undoLastAction")
        self.panel.log("Undid last drawn point/action.")

    def _toolbar_clear_all(self) -> None:
        self.state.clicked_points.clear()
        self.state.search_geometry_type = None
        self.state.search_geometry_payload = None
        self._distance_measure_mode_enabled = False
        self._add_point_mode_enabled = False
        self._set_annotation_overlay_visible(False)
        self._shadow_height_mode_enabled = False
        self._pan_mode_enabled = True
        self._viewshed_mode_enabled = False
        self._run_js_call("clearOverlays")
        self._run_js_call("setDistanceMeasureMode", False)
        self._run_js_call("setSearchDrawMode", "none")
        self._run_js_call("setPanMode", True)
        self._set_measurement_cursor_enabled(False)
        self._measurement_history.clear()
        self.panel.clear_measurement_result_entries()
        self.panel.log("Cleared all temporary measurements and overlays.")

    @staticmethod
    def _utm_epsg_for_lon_lat(lon: float, lat: float) -> int:
        zone = int((lon + 180.0) // 6.0) + 1
        return 32600 + zone if lat >= 0 else 32700 + zone

    def _polygon_metrics_for_export(
        self, polygon_points: list[tuple[float, float]]
    ) -> tuple[float, float, float]:
        if not polygon_points:
            return 0.0, 0.0, 0.0

        m = measure_polygon_area(polygon_points, dem_path=None)

        # Keep orientation logic for export
        if polygon_points[0] != polygon_points[-1]:
            polygon_points = polygon_points + [polygon_points[0]]
        lon_c = sum(p[0] for p in polygon_points) / len(polygon_points)
        lat_c = sum(p[1] for p in polygon_points) / len(polygon_points)
        epsg = self._utm_epsg_for_lon_lat(lon_c, lat_c)
        transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
        projected = [transformer.transform(lon, lat) for lon, lat in polygon_points]

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
        return m.planimetric_area_m2, m.perimeter_m, float(orientation)

    def _toolbar_add_polygon_annotation(self, enabled: bool | None = None) -> bool:
        if enabled is False:
            # Just disable draw mode — polygons stay visible
            self._run_js_call("setSearchDrawMode", "none")
            self._set_measurement_cursor_enabled(False)
            self.panel.log("Polygon draw disabled.")
            return False

        polygon = self._current_polygon_lonlat()
        if not polygon:
            self._distance_measure_mode_enabled = False
            self._add_point_mode_enabled = False # Enforce exclusivity
            self._set_annotation_overlay_visible(True)
            self._run_js_call("setAnnotationDrawingMode", True)
            self._shadow_height_mode_enabled = False
            self._pan_mode_enabled = False
            self._run_js_call("setDistanceMeasureMode", False)
            self._run_js_call("setPanMode", False)
            self.set_search_draw_mode()
            self.panel.log(
                "Polygon draw enabled. Click points, right-click to finish."
            )
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
        # Polygon stays visible — don't clear geometry
        self._run_js_call("setSearchDrawMode", "none")
        self._set_measurement_cursor_enabled(False)
        return False

    def _toolbar_export_profile_csv(self) -> None:
        self._project_io.export_profile_csv()

    def _toolbar_export_annotations_geojson(self) -> None:
        self._project_io.export_annotations_geojson()

    def _toolbar_export_geopackage(self) -> None:
        self._export.export_geopackage()

    def _toolbar_export_pdf(self) -> None:
        self._export.export_pdf()

    def _toolbar_export_geotiff(self) -> None:
        self._export.export_geotiff()

    def _toolbar_save_project(self) -> None:
        self._project_io.save_project()

    def _run_js_call(self, method: str, *args) -> None:
        """Execute a JavaScript method call with enhanced error handling and debugging."""
        try:
            encoded = ", ".join(json.dumps(arg) for arg in args)
            script = f"window.offlineGIS && window.offlineGIS.{method}({encoded});"
            self.web_view.page().runJavaScript(script)

        except Exception as e:
            self._logger.error("JavaScript call failed: %s - %s", method, e)
            self.panel.log(f"JavaScript error: {method} failed - {str(e)}")

    def _test_js_bridge_connectivity(self) -> bool:
        """Test if the JavaScript bridge is working properly."""
        try:
            # Simple test call that should always work
            self._run_js_call("requestSceneRender")
            return True
        except Exception as e:
            self._logger.error("JavaScript bridge test failed: %s", e)
            return False

    def _asset_centroid(self, asset: dict) -> dict[str, float] | None:
        cached = self._asset_cache.get(asset["file_path"])
        if cached and isinstance(cached.get("centroid"), dict):
            c = cached["centroid"]
            if self._is_valid_lon_lat(c.get("lon"), c.get("lat")):
                return c
        bounds_wkt = asset.get("bounds_wkt")
        if not bounds_wkt:
            return None
        from core_shared.utils.geometry import parse_bounds_wkt_polygon

        bounds = parse_bounds_wkt_polygon(bounds_wkt)
        lon, lat = bounds.centroid()
        if not self._is_valid_lon_lat(lon, lat):
            return None
        return {"lon": lon, "lat": lat}

    def _asset_bounds(self, asset: dict) -> dict[str, float] | None:
        bounds_wkt = asset.get("bounds_wkt")
        if not bounds_wkt:
            return None
        from core_shared.utils.geometry import parse_bounds_wkt_polygon

        b = parse_bounds_wkt_polygon(bounds_wkt)
        if not self._is_valid_lon_lat(b.min_x, b.min_y) or not self._is_valid_lon_lat(
            b.max_x, b.max_y
        ):
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
            self._logger.error(
                "No valid fly-to target for asset=%s centroid=%s",
                asset.get("file_name"),
                c,
            )
            return False
        self._run_js_call("flyTo", center["lon"], center["lat"], 9000)
        return True

    def _layer_options(self, asset: dict, bounds: dict[str, float] | None) -> dict:
        options: dict = {"bounds": bounds, "is_dem": self._is_dem_asset(asset)}
        try:
            tilejson = self.api.get_tilejson(asset["file_path"])
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
            if self._is_valid_lon_lat(w, s) and self._is_valid_lon_lat(e, n):
                tilejson_bounds = {
                    "west": float(w),
                    "south": float(s),
                    "east": float(e),
                    "north": float(n),
                }
                if (
                    self._is_near_global_bounds(tilejson_bounds)
                    and bounds
                    and not self._is_near_global_bounds(bounds)
                ):
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
        """Add layer with event-driven architecture and server-side optimization."""
        tile_url = str(asset.get("tile_url") or "")

        # Event-driven optimization: Let server handle URL normalization
        if options.get("event_driven", False):
            tile_url = self._get_server_optimized_tile_url(asset, tile_url)
        else:
            # Legacy path normalization for non-event-driven calls
            tile_url = self._normalize_tile_url_legacy(tile_url)

        asset["tile_url"] = tile_url

        if not self._is_offline_safe_url(tile_url):
            self.panel.log(
                f"Blocked non-offline tile URL for {asset.get('file_name', 'asset')}"
            )
            self._logger.error("Blocked non-offline tile URL: %s", tile_url)
            return False

        is_dem = bool(options.get("is_dem"))
        from_search_results = bool(str(options.get("layer_key") or "").strip())

        # Event-driven performance optimizations
        if options.get("server_optimized", False):
            self._apply_server_performance_hints(options)

        if is_dem:
            return self._add_dem_layer_event_driven(asset, options, from_search_results)
        else:
            return self._add_imagery_layer_event_driven(
                asset, options, from_search_results
            )

    def _get_server_optimized_tile_url(self, asset: dict, tile_url: str) -> str:
        """Get server-optimized tile URL for terabyte-scale performance."""
        # Server handles all URL optimization and caching strategies
        optimized_url = self._normalize_tile_url_legacy(tile_url)

        # Add server-side optimization parameters for large datasets
        if "?" in optimized_url:
            optimized_url += "&cache_strategy=aggressive&memory_efficient=true"
        else:
            optimized_url += "?cache_strategy=aggressive&memory_efficient=true"

        self._logger.info("Server-optimized tile URL for %s", asset.get("file_name"))
        return optimized_url

    def _find_best_file_version(self, file_path: str) -> str:
        """Find the best version of a file, prioritizing Web Mercator projected and COG versions."""
        from pathlib import Path

        original_path = Path(file_path)
        if not original_path.exists():
            self._logger.debug(f"Original file not found: {file_path}")
            return file_path

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

    def _normalize_tile_url_legacy(self, tile_url: str) -> str:
        """Legacy tile URL normalization for backward compatibility."""
        import platform
        import re
        from urllib.parse import unquote

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

    def _apply_server_performance_hints(self, options: dict) -> None:
        """Apply server-side performance hints for terabyte-scale data."""
        # Configure aggressive caching for large datasets
        options["tile_cache_size"] = "large"
        options["prefetch_strategy"] = "aggressive"
        options["memory_management"] = "optimized"

        self._logger.info("Applied server performance hints for terabyte-scale data")

    def _add_dem_layer_event_driven(
        self, asset: dict, options: dict, from_search_results: bool
    ) -> bool:
        """Add DEM layer using event-driven architecture."""
        if bool(options.get("replace_existing", True)) and not from_search_results:
            self._explicit_imagery_layer_visible = False
        if not from_search_results:
            self._explicit_dem_layer_visible = True

        self.state.active_layer_is_dem = True
        layer_key = str(options.get("layer_key") or "")
        self._active_dem_search_layer_key = layer_key or None

        # Event-driven DEM loading with server optimization
        self._run_js_call(
            "addDemLayerEventDriven", asset["file_name"], asset["tile_url"], options
        )

        self.panel.rgb_view_mode_combo.setCurrentIndex(0)
        self.panel.rgb_view_mode_combo.setEnabled(True)
        self.panel.apply_rgb_view_mode_btn.setEnabled(True)
        self._apply_display_control_mode()
        self._logger.info(
            "Event-driven DEM terrain layer requested name=%s", asset["file_name"]
        )
        return True

    def _add_imagery_layer_event_driven(
        self, asset: dict, options: dict, from_search_results: bool
    ) -> bool:
        """Add imagery layer using event-driven architecture."""
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

        # CRITICAL FIX: Do NOT force scene mode from Python backend
        # JavaScript will automatically switch to 2D for imagery, 3D for DEM
        # Forcing mode here creates conflicts and unnecessary morphing

        self._logger.info(
            "Event-driven layer render request name=%s kind=%s is_dem=%s replace_existing=%s apply_scene_mode=%s",
            asset.get("file_name"),
            asset.get("kind"),
            False,
            replace_existing,
            apply_scene_mode,
        )

        # Removed: Python-side setSceneMode call that conflicts with JavaScript auto-switching
        # JavaScript addTileLayer() will automatically call setSceneModeInternal("2d")
        # JavaScript addDemLayer() will automatically call setSceneModeInternal("3d")

        # Event-driven imagery loading with server optimization
        self._run_js_call(
            "addTileLayerEventDriven",
            asset["file_name"],
            asset["tile_url"],
            asset["kind"],
            options,
        )

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
            self._search_layer_visibility.get(path, False)
            and (not self._is_dem_asset(asset))
            for path, asset in self._search_result_assets_by_path.items()
        )
        if self._explicit_dem_layer_visible:
            dem_visible = True
        if self._explicit_imagery_layer_visible:
            imagery_visible = True

        if self._swipe_comparator_enabled and self._comparator_selected_layer_type in {
            "dem",
            "imagery",
        }:
            dem_visible = self._comparator_selected_layer_type == "dem"
            imagery_visible = self._comparator_selected_layer_type == "imagery"

        for widget in (
            self.panel.brightness_slider,
            self.panel.contrast_slider,
        ):
            widget.setEnabled(imagery_visible)

        # CRITICAL FIX: Determine current scene mode from RGB view mode combo
        current_scene_mode = str(
            self.panel.rgb_view_mode_combo.currentData() or "3d"
        ).lower()
        is_2d_mode = current_scene_mode == "2d"

        # DEM controls: enabled when DEM is visible
        for widget in (
            self.panel.dem_hillshade_slider,
            self.panel.dem_color_mode_combo,
        ):
            widget.setEnabled(dem_visible)

        # Camera controls: pitch slider enabled in ALL 3D modes with any layer
        # Rotation works in both 2D and 3D (heading rotation valid in 2D Cesium)
        any_layer_visible = dem_visible or imagery_visible
        self.panel.pitch_slider.setEnabled(any_layer_visible and not is_2d_mode)
        for widget in (
            self.panel.rotate_left_btn,
            self.panel.rotate_right_btn,
        ):
            widget.setEnabled(any_layer_visible)  # Rotation works in both 2D/3D

        # Visual feedback for disabled pitch slider in 2D mode
        if is_2d_mode and any_layer_visible:
            self.panel.pitch_slider.setStyleSheet("""
                QSlider {
                    color: #888888;
                    background-color: #f0f0f0;
                }
                QSlider::handle:horizontal {
                    background: #cccccc;
                    border: 1px solid #999999;
                }
                QSlider::groove:horizontal {
                    background: #e0e0e0;
                }
            """)
            self.panel.pitch_slider.setToolTip("Pitch control is disabled in 2D mode")
        else:
            # Reset to default style when enabled
            self.panel.pitch_slider.setStyleSheet("")
            self.panel.pitch_slider.setToolTip("Adjust camera pitch angle")

        if self._toolbar_context_callback is not None:
            # The toolbar callback is a bound MainWindow method; during
            # controller initialization the MainWindow.controller attribute
            # may not be set yet. Call defensively to avoid AttributeError in
            # that race. If the callback fails, log and continue — the
            # MainWindow will refresh toolbar state later.
            try:
                if dem_visible and imagery_visible:
                    self._toolbar_context_callback("mixed")
                elif dem_visible:
                    self._toolbar_context_callback("dem")
                elif imagery_visible:
                    self._toolbar_context_callback("imagery")
                else:
                    self._toolbar_context_callback("none")
            except Exception as exc:  # pragma: no cover - defensive
                try:
                    self._logger.debug(
                        "Toolbar context callback deferred: %s", exc
                    )
                except Exception:
                    pass

        if self._swipe_comparator_enabled and not self.can_enable_comparator():
            self._swipe_comparator_enabled = False
            self._comparator_selected_pane = None
            self._comparator_selected_layer_type = None
            self._run_js_call("setComparator", False)
            self.panel.log(
                "Comparator disabled: at least two visible raster layers are required."
            )

    def _is_dem_asset(self, asset: dict) -> bool:
        """Detect if asset is DEM or RGB imagery using robust band count + data type analysis.

        CRITICAL: Single-band imagery (like JP2 aerials) must NOT be detected as DEM.
        DEM detection requires BOTH single-band AND elevation-like data type/range.
        """
        file_path = str(asset.get("file_path") or "")
        if file_path and file_path in self._dem_asset_kind_cache:
            return self._dem_asset_kind_cache[file_path]

        # Step 1: Check explicit kind or filename hints
        kind = str(asset.get("kind", "")).lower()
        file_name = str(asset.get("file_name", "")).lower()

        # Explicit DEM markers
        if kind == "dem" or kind == "elevation":
            if file_path:
                self._dem_asset_kind_cache[file_path] = True
            return True

        # Explicit imagery markers (JP2, RGB, etc.) - NOT DEM
        imagery_extensions = (".jp2", ".jpeg", ".jpg", ".png", ".tif", ".tiff")
        imagery_keywords = ("rgb", "aerial", "ortho", "satellite", "imagery", "photo")

        if any(file_name.endswith(ext) for ext in imagery_extensions):
            # Check if filename contains imagery keywords
            if any(keyword in file_name for keyword in imagery_keywords):
                if file_path:
                    self._dem_asset_kind_cache[file_path] = False
                return False

        # Step 2: Analyze raster metadata (band count + data type)
        try:
            info = self.api.get_cog_info(asset["file_path"])
        except (httpx.HTTPError, KeyError, TypeError):
            if file_path:
                self._dem_asset_kind_cache[file_path] = False
            return False

        try:
            band_count = int(info.get("count", 0) or 0)
            dtype = str(info.get("dtype", "")).lower()

            # Multi-band = RGB imagery (NOT DEM)
            if band_count >= 3:
                if file_path:
                    self._dem_asset_kind_cache[file_path] = False
                return False

            # Single-band: Check data type to distinguish DEM from grayscale imagery
            # DEM typically uses float32/float64 or int16/int32 for elevation values
            # Grayscale imagery typically uses uint8/uint16 for pixel values
            if band_count == 1:
                # Float types = likely DEM (elevation values)
                if "float" in dtype:
                    if file_path:
                        self._dem_asset_kind_cache[file_path] = True
                    return True

                # Signed integer types = likely DEM (elevation can be negative)
                if "int16" in dtype or "int32" in dtype:
                    if file_path:
                        self._dem_asset_kind_cache[file_path] = True
                    return True

                # Unsigned integer types = likely grayscale imagery (NOT DEM)
                if "uint" in dtype:
                    if file_path:
                        self._dem_asset_kind_cache[file_path] = False
                    return False

            # Default: single-band with unknown dtype = assume imagery (safer default)
            if file_path:
                self._dem_asset_kind_cache[file_path] = False
            return False

        except (TypeError, ValueError):
            if file_path:
                self._dem_asset_kind_cache[file_path] = False
            return False

    def _raster_render_query(self, asset: dict) -> dict[str, object]:
        query: dict[str, object] = {}
        file_name = asset.get("file_name", "")
        is_dem = (
            str(asset.get("kind", "")).lower() == "dem"
            or "dem" in str(file_name).lower()
        )

        self._logger.debug(f"Raster render query for {file_name}: is_dem={is_dem}")

        info = {}
        try:
            info = self.api.get_cog_info(asset["file_path"])
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
            # Set nodata=0 to prevent GDAL "INIT_DEST NO_DATA without defined nodata"
            # error on Windows when the file has no nodata value defined.
            if "nodata" not in query:
                query["nodata"] = 0
        else:
            self._logger.debug(
                f"Single-band or DEM for {file_name}: band_count={band_count}, is_dem={is_dem}"
            )

        stats = {}
        try:
            stats = self.api.get_cog_statistics(asset["file_path"])
        except httpx.HTTPError as exc:
            self._logger.warning(
                "Statistics unavailable for %s: %s", asset.get("file_name"), exc
            )

        if is_dem:
            color_mode = str(self.panel.dem_color_mode_combo.currentData() or "gray")
            if color_mode == "slope":
                query["algorithm"] = "slope"
                query["colormap_name"] = "viridis"
                query["rescale"] = "0,90"
                self._logger.debug(f"DEM slope mode for {file_name}: {query}")
                return query

            query["colormap_name"] = color_mode

            # FIX: Provide default elevation rescale if TiTiler stats fail, preventing blank maps.
            low, high = -100.0, 4000.0
            if isinstance(stats, dict) and stats:
                first_band = (
                    stats.get("b1")
                    if isinstance(stats.get("b1"), dict)
                    else next(iter(stats.values()))
                )
                if isinstance(first_band, dict):
                    b_low = first_band.get("min")
                    b_high = first_band.get("max")
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
            # FIX: Apply QGIS-style per-band Cumulative Count Cut (2% - 98%)
            # This fixes both the pitch-black 16-bit rendering and the bluish tint.
            # Passing a list of rescales allows TiTiler to stretch each band independently.
            rescales = []
            valid = True
            for i in range(1, min(3, band_count) + 1):
                stat = stats.get(f"b{i}")
                if not isinstance(stat, dict):
                    valid = False
                    break
                low = stat.get("percentile_2", stat.get("min"))
                high = stat.get("percentile_98", stat.get("max"))
                if low is None or high is None or float(low) >= float(high):
                    valid = False
                    break
                rescales.append(f"{float(low)},{float(high)}")
            
            if valid and len(rescales) == 3:
                query["rescale"] = rescales
                self._logger.debug(
                    f"Applied QGIS-style per-band true color correction: {query}"
                )
            else:
                self._logger.debug(
                    f"Skipped true color correction (missing stats), rendering raw."
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

        low = first_band.get("percentile_2", first_band.get("min"))
        high = first_band.get("percentile_98", first_band.get("max"))
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

    @staticmethod
    def _normalize_path_for_compare(path: str) -> str:
        if not path:
            return ""
        try:
            normalized = str(Path(path).expanduser().resolve(strict=False))
        except Exception:
            normalized = str(path)
        return normalized.replace("\\", "/").casefold()

    def _paths_equivalent(self, path_a: str, path_b: str) -> bool:
        return self._normalize_path_for_compare(
            path_a
        ) == self._normalize_path_for_compare(path_b)

    def on_js_log(self, level: str, message: str) -> None:
        normalized = level.lower().strip()
        if self._layer_loading_active and (
            "Fly-through started" in message
            or "Fly-to bounds" in message
            or "Fly-to lon=" in message
        ):
            self._set_layer_loading(False, "Layer ready")

        if normalized == "debug" and (
            "SCENE_DEBUG" in message
            or "addTileLayer request" in message
            or "addDemLayer request" in message
            or "Imagery provider configured" in message
        ):
            self._logger.info("JS(debug): %s", message)
            return

        if "Tile provider error for" in message:
            self._logger.warning("JS: %s", message)
            return
        if normalized == "debug":
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
        if active:
            self._layer_loading_timeout_timer.start(self._layer_loading_timeout_ms)
        else:
            self._layer_loading_timeout_timer.stop()
        self.panel.set_layer_loading(active, message)

    def _on_layer_loading_timeout(self) -> None:
        if not self._layer_loading_active:
            return
        self._logger.warning(
            "Layer loading timeout after %sms", self._layer_loading_timeout_ms
        )
        self._set_layer_loading(False, "Layer load timeout")
        self.panel.log(
            "Layer load timed out. Check API/TiTiler availability and source raster path."
        )

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

        self.panel.log(
            "Offline guard: API/TiTiler endpoints must be local or private-network addresses."
        )
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
        self.panel.log(
            f"{action} blocked by offline guard. Configure local/private API and TiTiler endpoints."
        )
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
