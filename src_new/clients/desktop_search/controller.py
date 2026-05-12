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
from qtpy.QtCore import QObject, QSignalBlocker, QThreadPool, QTimer, Qt, Signal
from qtpy.QtWebEngineWidgets import QWebEngineView
from qtpy.QtWidgets import QFileDialog

from src_new.clients.desktop_search.api_client import DesktopApiClient
from src_new.clients.desktop_search.api_server_manager import ApiServerManager
from src_new.clients.desktop_search.app_mode import DesktopAppMode
from src_new.clients.desktop_search.bridge import WebBridge
from src_new.clients.desktop_search.titiler_manager import TiTilerManager
from src_new.clients.desktop_search.coordinators import (
    ComparatorCoordinator,
    MeasurementCoordinator,
    ProjectIoCoordinator,
    ToolbarActionCoordinator,
    SearchCoordinator,
    VisualizationCoordinator,
    ExportCoordinator,
    LayerCoordinator,
    AssetCoordinator,
    AnnotationCoordinator,
    CameraCoordinator,
    SearchResultsCoordinator,
    SyncFocusCoordinator,
    IngestCoordinator,
    AssetLoadingCoordinator,
)
from src_new.clients.desktop_search.coordinators.elevation_profile_coordinator import (
    ElevationProfileCoordinator,
)
from src_new.clients.desktop_search.control_panel import ControlPanel
from src_new.clients.desktop_search.performance_service import (
    DesktopPerformanceService,
)
from src_new.clients.desktop_search.state import DesktopState
from src_new.clients.desktop_search.measurement_tools import (
    compute_fill_volume,
    compute_slope_aspect,
    compute_viewshed,
    compute_volume,
    measure_polygon_area,
    measure_shadow_height,
)
from src_new.services.ingestion.gdal_pipelines.metadata_extractor import (
    MetadataExtractorError,
    extract_metadata,
)
from src_new.clients.desktop_search.tile_url_builder import build_xyz_url


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


class DesktopController(QObject):
    """Coordinates desktop UI actions, API calls, and Cesium bridge commands."""

    project_metadata_changed = Signal(str, bool)

    def __init__(
        self,
        panel: ControlPanel,
        web_view: QWebEngineView,
        bridge: WebBridge,
        api_client: DesktopApiClient | None = None,
        titiler_manager: TiTilerManager | None = None,
        api_server_manager: ApiServerManager | None = None,
        app_mode: DesktopAppMode = DesktopAppMode.UNIFIED,
        toolbar_context_callback: Callable[[str], None] | None = None,
    ):
        super().__init__()
        self.panel = panel
        self.web_view = web_view
        self.bridge = bridge
        self.app_mode = app_mode
        self.api = api_client or DesktopApiClient()
        self.api_server = api_server_manager or ApiServerManager(
            base_url=self.api.base_url
        )
        self.titiler = titiler_manager or TiTilerManager()
        self.performance = DesktopPerformanceService()
        self.state = DesktopState()
        self._logger = logging.getLogger("client_desktop.controller")
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
        self._add_line_mode_enabled = False
        self._add_text_mode_enabled = False
        self._annotation_line_start: tuple[float, float] | None = None
        self._shadow_height_mode_enabled = False
        self._pan_mode_enabled = True
        self._polygon_area_mode_enabled = False
        self._volume_mode_enabled = False
        self._viewshed_mode_enabled = False
        self._fly_through_mode_enabled = False
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
        self._annotation_icon_records: list[dict[str, object]] = []  # Icon + text annotations
        self._annotation_text_records: list[dict[str, object]] = []  # Text-only labels
        
        # Raster stretching state
        self._raster_stretch_settings: dict[str, dict[str, object]] = {}  # {layer_key: {type, method, params}}
        self._user_added_assets: dict[str, dict[str, object]] = {}
        self._vector_layers: dict[str, dict[str, object]] = {}
        self._project_path: Path | None = None
        self._is_project_modified = False


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
        self._layer = LayerCoordinator(self)
        self._asset = AssetCoordinator(self)
        self._annotation = AnnotationCoordinator(self)
        self._camera = CameraCoordinator(self)
        self._search_results = SearchResultsCoordinator(self)
        self._sync_focus = SyncFocusCoordinator(self)
        self._ingest = IngestCoordinator(self)
        self._asset_loading = AssetLoadingCoordinator(self)
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
        self.panel.stretch_mode_combo.currentIndexChanged.connect(
            self._on_stretch_mode_changed
        )
        if hasattr(self.panel, "dem_stretch_mode_combo"):
            self.panel.dem_stretch_mode_combo.currentIndexChanged.connect(
                self._on_dem_stretch_mode_changed
            )
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
        self.panel.asset_focus_requested.connect(self._toolbar_zoom_to_asset)
        self.panel.vector_layer_visibility_toggled.connect(
            self.set_vector_layer_visibility
        )
        self.panel.vector_layer_delete_requested.connect(self.remove_vector_layer)
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
        self.panel.search_layer_delete_requested.connect(self.remove_search_layer)

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
        self._asset.preview_selected_uploaded_asset()

    def _flyto_asset_bounds(self, asset: dict, kind: str) -> None:
        self._camera.flyto_asset_bounds(asset, kind)


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
        # Set cursor via JavaScript (for Cesium canvas cursor)
        self._logger.debug("_set_measurement_cursor_enabled called: enabled=%s", enabled)
        self._run_js_call("setMeasurementCursor", bool(enabled))
        # CRITICAL FIX: Emit signal to update Qt widget cursor (for Windows cursor display)
        # The MainWindow listens to this signal and updates the web view cursor
        if hasattr(self, "bridge") and self.bridge:
            self._logger.debug("Emitting measureCursorChanged signal: enabled=%s", enabled)
            self.bridge.measureCursorChanged.emit(bool(enabled))
        else:
            self._logger.warning("Bridge not available, cannot emit measureCursorChanged signal")

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
        self._search_results.apply_search_results(assets, label)

    def _apply_search_results_event_driven(
        self, assets: list[dict], label: str
    ) -> None:
        """Apply search results with event-driven optimization for terabyte-scale performance."""
        self._search_results.apply_search_results_event_driven(assets, label)

    def _sync_search_visibility_layers_event_driven(self) -> None:
        """Synchronize search visibility layers with event-driven optimization."""
        self._sync_focus.sync_search_visibility_layers_event_driven()

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
        return self._sync_focus.load_asset_layer_event_driven(
            asset,
            replace_existing=replace_existing,
            layer_key=layer_key,
            auto_fly_to=auto_fly_to,
            apply_scene_mode=apply_scene_mode,
            show_loading=show_loading,
        )

    def toggle_search_result_visibility(self, file_path: str, visible: bool) -> None:
        self._layer.toggle_search_result_visibility(file_path, visible)

    def _sync_search_visibility_layers(self) -> None:
        """Sync layer visibility between UI and globe with debug logging - optimized to only update changed layers."""
        self._sync_focus.sync_search_visibility_layers()

    def _focus_visible_search_assets(self, *, force: bool) -> None:
        """Legacy focus function - delegates to enhanced version."""
        self._sync_focus.focus_visible_search_assets(force=force)

    def _focus_visible_search_assets_with_enhanced_behavior(
        self, *, force: bool, is_first_search: bool, asset_count: int
    ) -> None:
        """Enhanced focus function with improved multi-asset handling and first-search auto-flyto."""
        self._sync_focus.focus_visible_search_assets_with_enhanced_behavior(
            force=force, is_first_search=is_first_search, asset_count=asset_count
        )

    def reorder_search_result_layers(self, reordered_layers: list[dict]) -> None:
        self._layer.reorder_search_result_layers(reordered_layers)

    def _reorder_layers_event_driven(self, reordered_assets: list[dict]) -> None:
        """Reorder layers using event-driven approach for optimal performance."""
        self._sync_focus.reorder_layers_event_driven(reordered_assets)

    def _reorder_layers_standard(self, reordered_assets: list[dict]) -> None:
        """Reorder layers using standard approach."""
        self._sync_focus.reorder_layers_standard(reordered_assets)

    def _update_coordinate_inputs_from_polygon(self, payload: dict) -> None:
        """Update coordinate inputs from polygon payload."""
        self._sync_focus.update_coordinate_inputs_from_polygon(payload)

    def browse_files(self) -> None:
        self._asset.browse_files()

    def add_raster_layers(self) -> None:
        self._layer.add_raster_layers()

    def add_vector_layers(self) -> None:
        self._layer.add_vector_layers()

    def remove_search_layer(self, file_path: str) -> None:
        self._layer.remove_search_layer(file_path)

    def set_vector_layer_visibility(self, layer_key: str, visible: bool) -> None:
        self._layer.set_vector_layer_visibility(layer_key, visible)

    def remove_vector_layer(self, layer_key: str) -> None:
        self._layer.remove_vector_layer(layer_key)

    def new_project(self) -> None:
        self._clear_project_state()
        self._project_path = None
        self._set_project_modified(False)
        self.panel.log("New project ready.")

    def open_project(self) -> None:
        self._project_io.open_project()

    def save_project(self) -> None:
        self._project_io.save_project()

    def save_project_as(self) -> None:
        self._project_io.save_project_as()

    def undo_last_action(self) -> None:
        self.panel.log("Undo is not available yet.")

    def redo_last_action(self) -> None:
        self.panel.log("Redo is not available yet.")

    def build_project_payload(self) -> dict:
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        order_registry = getattr(self.panel, "_layer_order_registry", {}) or {}

        raster_layers: list[dict[str, object]] = []
        for path, asset in self._search_result_assets_by_path.items():
            normalized_path = str(path or "").replace("\\", "/")
            if not normalized_path:
                continue
            entry = order_registry.get(normalized_path, {})
            raster_layers.append(
                {
                    "file_path": normalized_path,
                    "file_name": asset.get("file_name"),
                    "kind": asset.get("kind"),
                    "crs": asset.get("crs"),
                    "bounds_wkt": asset.get("bounds_wkt"),
                    "tile_url": asset.get("tile_url"),
                    "resolution_x": asset.get("resolution_x"),
                    "resolution_y": asset.get("resolution_y"),
                    "width": asset.get("width"),
                    "height": asset.get("height"),
                    "created_at": asset.get("created_at"),
                    "is_visible": bool(
                        self._search_layer_visibility.get(normalized_path, True)
                    ),
                    "order": entry.get("order", 0),
                    "source": "user"
                    if normalized_path in self._user_added_assets
                    else "search",
                }
            )

        vector_layers = [dict(layer) for layer in self._vector_layers.values()]

        layer_order = [
            path
            for path, entry in sorted(
                order_registry.items(), key=lambda item: item[1].get("order", 0)
            )
        ]

        return {
            "version": 1,
            "saved_at": now,
            "selected_asset_path": (
                self.state.selected_asset.get("file_path")
                if isinstance(self.state.selected_asset, dict)
                else None
            ),
            "clicked_points": list(self.state.clicked_points),
            "search": {
                "geometry_type": self.state.search_geometry_type,
                "geometry_payload": self.state.search_geometry_payload,
                "visibility": dict(self._search_layer_visibility),
                "layer_order": layer_order,
                "active_dem": self._active_dem_search_layer_key,
            },
            "annotations": {
                "points": list(self._annotation_records),
                "lines": list(self._annotation_line_records),
                "polygons": list(self._annotation_polygon_records),
                "icons": list(self._annotation_icon_records),
                "text_labels": list(self._annotation_text_records),
            },
            "raster_stretch": dict(self._raster_stretch_settings),
            "layers": {
                "rasters": raster_layers,
                "vectors": vector_layers,
            },
        }

    def apply_project_payload(self, payload: dict, source_path: Path | None = None) -> None:
        self._clear_project_state()
        if source_path:
            self._project_path = source_path

        search_payload = payload.get("search") if isinstance(payload, dict) else {}
        if not isinstance(search_payload, dict):
            search_payload = {}
        geometry_type = search_payload.get("geometry_type")
        geometry_payload = search_payload.get("geometry_payload")
        self.state.search_geometry_type = geometry_type
        self.state.search_geometry_payload = geometry_payload
        if geometry_type == "polygon" and isinstance(geometry_payload, dict):
            points = geometry_payload.get("points", [])
            if isinstance(points, list):
                self._run_js_call("loadSearchPolygon", points)
                self._update_coordinate_inputs_from_polygon({"points": points})

        annotations = payload.get("annotations") if isinstance(payload, dict) else {}
        if isinstance(annotations, dict):
            self._annotation_records = list(annotations.get("points") or [])
            self._annotation_line_records = list(annotations.get("lines") or [])
            self._annotation_polygon_records = list(annotations.get("polygons") or [])
            self._annotation_icon_records = list(annotations.get("icons") or [])
            self._annotation_text_records = list(annotations.get("text_labels") or [])
        else:
            self._annotation_records = []
            self._annotation_line_records = []
            self._annotation_polygon_records = []
            self._annotation_icon_records = []
            self._annotation_text_records = []

        # Load raster stretch settings
        raster_stretch = payload.get("raster_stretch") if isinstance(payload, dict) else {}
        if isinstance(raster_stretch, dict):
            self._raster_stretch_settings = dict(raster_stretch)
        else:
            self._raster_stretch_settings = {}

        layers_payload = payload.get("layers") if isinstance(payload, dict) else {}
        raster_layers = []
        if isinstance(layers_payload, dict):
            raster_layers = layers_payload.get("rasters") or []
        if not isinstance(raster_layers, list):
            raster_layers = []

        self._search_result_assets_by_path = {}
        self._search_layer_visibility = {}
        self._loaded_search_layer_keys = set()
        self._last_synced_visibility = {}
        self._user_added_assets = {}

        order_registry = {}
        for entry in raster_layers:
            if not isinstance(entry, dict):
                continue
            file_path = str(entry.get("file_path") or "").replace("\\", "/")
            if not file_path:
                continue
            file_name = str(entry.get("file_name") or Path(file_path).name)
            tile_url = entry.get("tile_url") or build_xyz_url(file_path)
            asset = {
                "file_path": file_path,
                "file_name": file_name,
                "kind": entry.get("kind") or "unknown",
                "crs": entry.get("crs") or "-",
                "bounds_wkt": entry.get("bounds_wkt") or "",
                "tile_url": tile_url,
                "resolution_x": entry.get("resolution_x"),
                "resolution_y": entry.get("resolution_y"),
                "width": entry.get("width"),
                "height": entry.get("height"),
                "created_at": entry.get("created_at"),
            }
            self._search_result_assets_by_path[file_path] = asset
            self._search_layer_visibility[file_path] = bool(
                entry.get("is_visible", True)
            )
            if str(entry.get("source") or "") == "user":
                self._user_added_assets[file_path] = asset
            order_registry[file_path] = {
                "file_name": file_name,
                "kind": str(asset.get("kind") or "-"),
                "crs": str(asset.get("crs") or "-"),
                "created_at": str(entry.get("created_at") or "-"),
                "is_visible": bool(entry.get("is_visible", True)),
                "order": int(entry.get("order", 0)),
            }

        self.panel._layer_order_registry = order_registry
        self._active_dem_search_layer_key = search_payload.get("active_dem")
        if (
            self._active_dem_search_layer_key
            and self._active_dem_search_layer_key not in self._search_result_assets_by_path
        ):
            self._active_dem_search_layer_key = None

        self._sync_search_visibility_layers()

        layer_order = search_payload.get("layer_order")
        if isinstance(layer_order, list) and layer_order:
            ordered_keys = [
                str(p).replace("\\", "/")
                for p in layer_order
                if str(p or "").strip()
            ]
            if ordered_keys:
                self._run_js_call("enforceLayerDisplayOrder", ordered_keys)

        self.panel.update_search_results(
            list(self._search_result_assets_by_path.values()),
            self._search_layer_visibility,
        )

        vectors = []
        if isinstance(layers_payload, dict):
            vectors = layers_payload.get("vectors") or []
        if not isinstance(vectors, list):
            vectors = []

        self._vector_layers = {}
        self._run_js_call("clearVectorLayers")
        for entry in vectors:
            if not isinstance(entry, dict):
                continue
            layer_key = str(entry.get("layer_key") or "").strip()
            label = str(entry.get("label") or "Vector")
            geojson = entry.get("geojson")
            if not layer_key or not isinstance(geojson, dict):
                continue
            self._run_js_call("addVectorLayer", layer_key, label, geojson, {})
            is_visible = bool(entry.get("is_visible", True))
            if not is_visible:
                self._run_js_call("setVectorLayerVisibility", layer_key, False)
            self._vector_layers[layer_key] = dict(entry)
            self._vector_layers[layer_key]["is_visible"] = is_visible

        self._restore_annotations_on_map()
        self._refresh_vector_layers_ui()

        selected_path = payload.get("selected_asset_path")
        if isinstance(selected_path, str) and selected_path:
            selected_asset = self._search_result_assets_by_path.get(
                selected_path.replace("\\", "/")
            )
            if selected_asset:
                self.state.selected_asset = selected_asset

        self.state.clicked_points = list(payload.get("clicked_points") or [])

        self.panel.log("Project loaded.")
        self._set_project_modified(False)

    def _set_project_modified(self, modified: bool = True) -> None:
        """Update modification state and notify UI."""
        self._is_project_modified = modified
        name = self._project_path.stem if self._project_path else "Untitled Project"
        self.project_metadata_changed.emit(name, modified)


    def _clear_project_state(self) -> None:
        self._run_js_call("clearAllLayers")
        self._run_js_call("clearVectorLayers")
        self._run_js_call("clearSearchGeometry")
        self._run_js_call("clearAnnotations")
        self._run_js_call("resetDefaultView")

        self._search_result_assets_by_path = {}
        self._search_layer_visibility = {}
        self._loaded_search_layer_keys = set()
        self._last_synced_visibility = {}
        self._active_dem_search_layer_key = None
        self._explicit_imagery_layer_visible = False
        self._explicit_dem_layer_visible = False
        self._user_added_assets = {}
        self._vector_layers = {}
        self._annotation_records = []
        self._annotation_line_records = []
        self._annotation_polygon_records = []
        self._annotation_icon_records = []
        self._annotation_text_records = []
        self._raster_stretch_settings = {}
        self.state.selected_asset = None
        self.state.clicked_points = []
        self.state.search_geometry_type = None
        self.state.search_geometry_payload = None
        self.panel.assets_combo.clear()
        if hasattr(self.panel, "_layer_order_registry"):
            self.panel._layer_order_registry = {}
        self.panel.update_search_results([], {})
        self.panel.update_vector_layers([])
        self.clear_all_measurement_results()
        self._apply_display_control_mode()

    def _restore_annotations_on_map(self) -> None:
        self._run_js_call("clearAnnotations")
        for item in self._annotation_records:
            try:
                lon = float(item.get("lon") or 0.0)
                lat = float(item.get("lat") or 0.0)
                text = str(item.get("text") or self._default_annotation_text)
            except (TypeError, ValueError):
                continue
            self._run_js_call("addAnnotation", text, lon, lat)

        # Restore icon annotations
        for item in self._annotation_icon_records:
            try:
                lon = float(item.get("lon") or 0.0)
                lat = float(item.get("lat") or 0.0)
                icon = str(item.get("icon") or "marker")
                text = str(item.get("text") or "")
            except (TypeError, ValueError):
                continue
            self._run_js_call("addIconAnnotation", lon, lat, icon, text)

        # Restore text labels
        for item in self._annotation_text_records:
            try:
                lon = float(item.get("lon") or 0.0)
                lat = float(item.get("lat") or 0.0)
                text = str(item.get("text") or "Label")
            except (TypeError, ValueError):
                continue
            self._run_js_call("addTextLabel", lon, lat, text)

        for item in self._annotation_line_records:
            coords = item.get("coords", [])
            if coords:
                self._run_js_call(
                    "addLineAnnotation",
                    coords,
                    str(item.get("label") or "Line"),
                )

        for item in self._annotation_polygon_records:
            coords = item.get("coords", [])
            if coords:
                # Convert list of tuples/lists or list of dicts to dict format expected by JS
                js_points = []
                for c in coords:
                    if isinstance(c, (list, tuple)) and len(c) >= 2:
                        js_points.append({"lon": float(c[0]), "lat": float(c[1])})
                    elif isinstance(c, dict) and "lon" in c and "lat" in c:
                        js_points.append({"lon": float(c["lon"]), "lat": float(c["lat"])})
                
                if js_points:
                    self._run_js_call("restoreAnnotationPolygon", js_points)

        # Restore raster stretch settings
        for layer_key, settings in self._raster_stretch_settings.items():
            stretch_type = settings.get("type")
            method = settings.get("method")
            params = settings.get("params", {})
            if stretch_type and method:
                self._run_js_call("applyRasterStretch", layer_key, stretch_type, method, params)

        annotation_geojson = self._annotation_line_polygon_geojson()
        if annotation_geojson:
            layer_key = self._make_unique_vector_key("vector:annotations")
            self._run_js_call("addVectorLayer", layer_key, "Annotations", annotation_geojson, {})
            self._vector_layers[layer_key] = {
                "layer_key": layer_key,
                "label": "Annotations",
                "file_path": None,
                "source": "annotations",
                "geojson": annotation_geojson,
                "is_visible": True,
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }

    def _annotation_line_polygon_geojson(self) -> dict | None:
        features = []
        for item in self._annotation_line_records:
            coords = item.get("coords", [])
            if coords:
                features.append(
                    {
                        "type": "Feature",
                        "geometry": {"type": "LineString", "coordinates": coords},
                        "properties": {
                            "feature_type": item.get("feature_type", "line"),
                            "label": item.get("label", ""),
                            "length_m": item.get("length_m", 0.0),
                            "width_m": item.get("width_m", 0.0),
                            "condition": item.get("condition", "intact"),
                        },
                    }
                )
        for item in self._annotation_polygon_records:
            coords = item.get("coords", [])
            if coords:
                ring = list(coords)
                if ring and ring[0] != ring[-1]:
                    ring.append(ring[0])
                features.append(
                    {
                        "type": "Feature",
                        "geometry": {"type": "Polygon", "coordinates": [ring]},
                        "properties": {
                            "feature_type": item.get("feature_type", "polygon"),
                            "area_m2": item.get("area_m2", 0.0),
                            "condition": item.get("condition", "intact"),
                        },
                    }
                )
        if not features:
            return None
        return {"type": "FeatureCollection", "features": features}

    def _create_raster_asset_from_path(self, file_path: str) -> dict | None:
        path = Path(str(file_path)).expanduser()
        if not path.exists():
            self.panel.log(f"Raster not found: {path}")
            return None
        if self.api.api_ready():
            try:
                asset = self.api.register_raster(str(path))
                if isinstance(asset, dict):
                    if "tile_url" not in asset:
                        asset["tile_url"] = build_xyz_url(str(path))
                    return asset
            except Exception as exc:
                self.panel.log(f"Raster registration failed: {path.name}. {exc}")
                self._logger.warning("Raster registration failed: %s", exc)
        try:
            metadata = extract_metadata(path)
        except MetadataExtractorError as exc:
            self.panel.log(f"Metadata extraction failed: {path.name}. {exc}")
            self._logger.warning("Metadata extraction failed: %s", exc)
            return None
        except Exception as exc:
            self.panel.log(f"Metadata extraction error: {path.name}. {exc}")
            self._logger.warning("Metadata extraction error: %s", exc)
            return None

        bounds_wkt = metadata.bounds.to_wkt_polygon()
        return {
            "file_path": str(metadata.file_path),
            "file_name": metadata.file_name,
            "kind": metadata.kind.value,
            "crs": metadata.crs or "-",
            "bounds_wkt": bounds_wkt,
            "resolution_x": metadata.resolution_x,
            "resolution_y": metadata.resolution_y,
            "width": metadata.width,
            "height": metadata.height,
            "tile_url": build_xyz_url(str(metadata.file_path)),
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }

    def _read_vector_geojson(self, path: Path) -> dict | None:
        suffix = path.suffix.lower()
        if suffix in {".geojson", ".json"}:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                self.panel.log(f"Failed to read {path.name}: {exc}")
                return None
            if isinstance(payload, dict) and payload.get("type"):
                return payload
            if isinstance(payload, list):
                return {"type": "FeatureCollection", "features": payload}
            self.panel.log(f"Unsupported GeoJSON structure: {path.name}")
            return None

        try:
            import fiona
        except Exception:
            self.panel.log(
                f"Vector support for {path.suffix} requires Fiona. Install geo extras."
            )
            return None

        try:
            features = []
            with fiona.open(path) as src:
                for feature in src:
                    features.append(feature)
            return {"type": "FeatureCollection", "features": features}
        except Exception as exc:
            self.panel.log(f"Failed to read vector {path.name}: {exc}")
            return None

    def _make_unique_vector_key(self, base: str) -> str:
        key = str(base or "vector")
        if key not in self._vector_layers:
            return key
        suffix = 1
        while f"{key}:{suffix}" in self._vector_layers:
            suffix += 1
        return f"{key}:{suffix}"

    def _refresh_vector_layers_ui(self) -> None:
        self.panel.update_vector_layers(list(self._vector_layers.values()))

    def clear_file_selection(self) -> None:
        self._asset.clear_file_selection()

    def enqueue_selected_files(self) -> None:
        self._asset.enqueue_selected_files()

    def _start_ingest_monitoring(self, job_id: str) -> None:
        """Start monitoring an ingestion job by setting up the polling timer."""
        self._ingest.start_ingest_monitoring(job_id)

    def delete_asset(self, asset_data: dict) -> None:
        """Delete an asset."""
        self._asset.delete_asset(asset_data)

    def refresh_assets(self) -> None:
        """Refresh the assets list."""
        self._asset.refresh_assets()

    def _select_asset_in_combo(self, file_path: str) -> bool:
        """Select an asset in the combo box by file path."""
        return self._ingest.select_asset_in_combo(file_path)

    def _poll_active_ingest_job(self) -> None:
        """Poll the active ingestion job for progress updates."""
        self._ingest.poll_active_ingest_job()

    def stop_ingest_polling(self) -> None:
        """Manually stop ingest job polling."""
        self._ingest.stop_ingest_polling()

    def _update_ingest_progress_ui(self, job: dict, *, emit_detail: bool) -> None:
        """Update the UI with ingestion progress information."""
        self._ingest.update_ingest_progress_ui(job, emit_detail=emit_detail)

    @staticmethod
    def _default_step_for_status(status: str) -> str:
        """Get default step message for a given status."""
        return IngestCoordinator.default_step_for_status(status)

    @staticmethod
    def _format_elapsed(elapsed_seconds: float | int | None) -> str:
        """Format elapsed time in HH:MM:SS or MM:SS format."""
        return IngestCoordinator.format_elapsed(elapsed_seconds)

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
        self._layer.add_selected_layer()

    def _load_asset_layer(
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
        return self._asset_loading.load_asset_layer(
            asset,
            replace_existing=replace_existing,
            layer_key=layer_key,
            auto_fly_to=auto_fly_to,
            apply_scene_mode=apply_scene_mode,
            show_loading=show_loading,
            skip_cog=skip_cog,
        )

    def _fly_through_asset(self, asset: dict) -> bool:
        return self._asset_loading.fly_through_asset(asset)

    def _try_visualize_ingested_asset(self) -> None:
        self._asset_loading.try_visualize_ingested_asset()

    def _request_server_processed_assets(self, source_path: str) -> list[dict]:
        return self._asset_loading._request_server_processed_assets(source_path)

    def _get_server_processed_folder_assets(
        self, assets: list[dict], source_path_obj: Path
    ) -> list[dict]:
        return self._asset_loading._get_server_processed_folder_assets(
            assets, source_path_obj
        )

    def _get_server_sorted_recent_assets(
        self, assets: list[dict], limit: int = 5
    ) -> list[dict]:
        return self._asset_loading._get_server_sorted_recent_assets(assets, limit)

    def _find_server_processed_asset(
        self, assets: list[dict], source_path: str
    ) -> dict | None:
        return self._asset_loading._find_server_processed_asset(assets, source_path)

    def _load_assets_event_driven(self, assets_to_load: list[dict]) -> None:
        self._asset_loading._load_assets_event_driven(assets_to_load)

    def _load_single_asset_event_driven(self, match: dict) -> None:
        self._asset_loading._load_single_asset_event_driven(match)

    def _get_server_optimized_layer_options(self, asset: dict) -> dict:
        return self._asset_loading._get_server_optimized_layer_options(asset)

    def _add_layer_event_driven(self, asset: dict, options: dict) -> bool:
        return self._asset_loading._add_layer_event_driven(asset, options)

    def _fly_through_asset_event_driven(self, asset: dict) -> bool:
        return self._asset_loading._fly_through_asset_event_driven(asset)

    def apply_rgb_view_mode(self) -> None:
        self._viz.apply_rgb_view_mode()

    def _on_visual_slider_changed(self, _value: int) -> None:
        self._viz.on_visual_slider_changed(_value)

    def _on_stretch_mode_changed(self, _index: int) -> None:
        self._apply_imagery_stretch_mode(log_to_panel=True)

    def _on_dem_stretch_mode_changed(self, _index: int) -> None:
        self._apply_dem_stretch_mode(log_to_panel=True)

    def _on_dem_slider_changed(self, _value: int) -> None:
        self._viz.on_dem_slider_changed(_value)

    def _on_dem_color_mode_changed(self, _index: int) -> None:
        self._viz.apply_dem_color_mode(log_to_panel=True)

    def apply_visual_settings(self, log_to_panel: bool = True) -> None:
        self._viz.apply_visual_settings(log_to_panel=log_to_panel)

    def _apply_imagery_stretch_mode(self, log_to_panel: bool = True) -> None:
        refreshed = self._refresh_raster_layers_for_stretch(layer_kind="imagery")
        mode_label = self.panel.stretch_mode_combo.currentText()
        if not log_to_panel:
            return
        if refreshed > 0:
            self.panel.log(
                f"Imagery stretch applied: {mode_label} ({refreshed} layer(s) refreshed)"
            )
            self._logger.info(
                "Imagery stretch applied mode=%s refreshed=%s", mode_label, refreshed
            )
            return
        self.panel.log(f"Imagery stretch set: {mode_label}")
        self._logger.info(
            "Imagery stretch set mode=%s (no active raster layers)", mode_label
        )

    def _apply_dem_stretch_mode(self, log_to_panel: bool = True) -> None:
        if not hasattr(self.panel, "dem_stretch_mode_combo"):
            return
        refreshed = self._refresh_raster_layers_for_stretch(layer_kind="dem")
        mode_label = self.panel.dem_stretch_mode_combo.currentText()
        if not log_to_panel:
            return
        if refreshed > 0:
            self.panel.log(
                f"DEM stretch applied: {mode_label} ({refreshed} layer(s) refreshed)"
            )
            self._logger.info(
                "DEM stretch applied mode=%s refreshed=%s", mode_label, refreshed
            )
            return
        self.panel.log(f"DEM stretch set: {mode_label}")
        self._logger.info("DEM stretch set mode=%s (no active raster layers)", mode_label)

    def _refresh_raster_layers_for_stretch(self, layer_kind: str | None = None) -> int:
        refreshed = 0
        seen_paths: set[str] = set()

        for path, asset in self._search_result_assets_by_path.items():
            if not self._search_layer_visibility.get(path, False):
                continue
            if not isinstance(asset, dict):
                continue
            if layer_kind == "dem" and not self._is_dem_asset(asset):
                continue
            if layer_kind == "imagery" and self._is_dem_asset(asset):
                continue
            asset_path = str(asset.get("file_path") or "")
            if asset_path and asset_path in seen_paths:
                continue
            loaded = self._load_asset_layer_event_driven(
                asset,
                replace_existing=True,
                layer_key=path,
                auto_fly_to=False,
                apply_scene_mode=False,
                show_loading=False,
            )
            if loaded:
                refreshed += 1
            if asset_path:
                seen_paths.add(asset_path)

        if self._explicit_imagery_layer_visible or self._explicit_dem_layer_visible:
            asset = self.state.selected_asset
            if isinstance(asset, dict):
                asset_path = str(asset.get("file_path") or "")
                if asset_path and asset_path in seen_paths:
                    return refreshed
                is_dem = self._is_dem_asset(asset)
                if layer_kind == "dem" and not is_dem:
                    return refreshed
                if layer_kind == "imagery" and is_dem:
                    return refreshed
                if (self._explicit_dem_layer_visible and is_dem) or (
                    self._explicit_imagery_layer_visible and not is_dem
                ):
                    loaded = self._load_asset_layer_event_driven(
                        asset,
                        replace_existing=True,
                        layer_key=None,
                        auto_fly_to=False,
                        apply_scene_mode=False,
                        show_loading=False,
                    )
                    if loaded:
                        refreshed += 1
        return refreshed

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

        if self._add_text_mode_enabled:
            self._add_text_label_at(lon, lat, "Label")
            return

        if self._add_line_mode_enabled:
            if self._annotation_line_start is None:
                self._annotation_line_start = (lon, lat)
                self._run_js_call("setLineDrawStart", lon, lat)
                self.panel.log("Line start set. Click the end point to finish.")
                return
            start_lon, start_lat = self._annotation_line_start
            self._annotation_line_start = None
            self._add_line_annotation_between((start_lon, start_lat), (lon, lat))
            self._run_js_call("clearLineDrawPreview")
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
        self._set_project_modified(True)

        self._logger.info("Annotation added lon=%.5f lat=%.5f text=%s", lon, lat, text)

    def _add_icon_annotation_at(self, lon: float, lat: float, icon_name: str, text: str) -> None:
        """Add icon-based annotation with text label."""
        self._run_js_call("addIconAnnotation", lon, lat, icon_name, text)
        self._annotation_icon_records.append(
            {
                "type": "icon",
                "lon": lon,
                "lat": lat,
                "icon": icon_name,
                "text": text,
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        )
        self.panel.log(f"Icon annotation '{icon_name}' added at {lon:.5f}, {lat:.5f}")
        self._set_project_modified(True)
        self._logger.info("Icon annotation added lon=%.5f lat=%.5f icon=%s text=%s", lon, lat, icon_name, text)

    def _add_text_label_at(self, lon: float, lat: float, text: str) -> None:
        """Add text-only label (editable, larger font, white color)."""
        self._run_js_call("addTextLabel", lon, lat, text)
        self._annotation_text_records.append(
            {
                "type": "text",
                "lon": lon,
                "lat": lat,
                "text": text,
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        )
        self.panel.log(f"Text label added at {lon:.5f}, {lat:.5f}")
        self._set_project_modified(True)
        self._logger.info("Text label added lon=%.5f lat=%.5f text=%s", lon, lat, text)

    def _add_line_annotation_between(
        self, start: tuple[float, float], end: tuple[float, float]
    ) -> None:
        coords = [[float(start[0]), float(start[1])], [float(end[0]), float(end[1])]]
        line_label = f"Line {len(self._annotation_line_records) + 1}"
        length_m = self._line_length_m(coords)
        self._run_js_call("addLineAnnotation", coords, line_label)
        self._annotation_line_records.append(
            {
                "coords": coords,
                "label": line_label,
                "feature_type": "line",
                "length_m": length_m,
                "width_m": 0.0,
                "condition": "intact",
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        )
        self.panel.log(f"Line annotation added ({length_m:.1f} m)")
        self._set_project_modified(True)

    @staticmethod
    def _line_length_m(coords: list[list[float]]) -> float:
        if len(coords) < 2:
            return 0.0
        try:
            from pyproj import Geod

            geod = Geod(ellps="WGS84")
            total = 0.0
            for idx in range(len(coords) - 1):
                lon1, lat1 = coords[idx]
                lon2, lat2 = coords[idx + 1]
                _, _, dist = geod.inv(lon1, lat1, lon2, lat2)
                total += float(dist)
            return total
        except Exception:
            total = 0.0
            radius_m = 6371008.8
            for idx in range(len(coords) - 1):
                lon1, lat1 = coords[idx]
                lon2, lat2 = coords[idx + 1]
                lon1_r = math.radians(lon1)
                lat1_r = math.radians(lat1)
                lon2_r = math.radians(lon2)
                lat2_r = math.radians(lat2)
                dlon = lon2_r - lon1_r
                dlat = lat2_r - lat1_r
                a = (
                    math.sin(dlat / 2.0) ** 2
                    + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2.0) ** 2
                )
                c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
                total += radius_m * c
            return total

    def apply_raster_stretch(self, layer_key: str, stretch_type: str, method: str, **params) -> None:
        """
        Apply raster stretching to imagery or DEM layers.
        
        Args:
            layer_key: Unique identifier for the layer
            stretch_type: 'imagery' or 'dem'
            method: 'min_max', 'std_dev', 'linear', 'histogram_eq'
            params: Additional parameters (e.g., k for std_dev, percentile for percentile_clip)
        """
        self._raster_stretch_settings[layer_key] = {
            "type": stretch_type,
            "method": method,
            "params": params,
            "applied_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        
        # Apply stretch via JavaScript bridge with real-time sync
        self._run_js_call("applyRasterStretch", layer_key, stretch_type, method, params)
        self.panel.log(f"Applied {method} stretch to {stretch_type} layer: {layer_key}")
        self._logger.info("Raster stretch applied: layer=%s type=%s method=%s params=%s", 
                         layer_key, stretch_type, method, params)

    def update_raster_stretch_params(self, layer_key: str, **params) -> None:
        """Update stretch parameters for real-time adjustment (e.g., slider changes)."""
        if layer_key not in self._raster_stretch_settings:
            self._logger.warning("Cannot update stretch params for unknown layer: %s", layer_key)
            return
        
        settings = self._raster_stretch_settings[layer_key]
        settings["params"].update(params)
        
        # Real-time update via JavaScript
        self._run_js_call("updateRasterStretchParams", layer_key, params)
        self._logger.debug("Updated stretch params for layer %s: %s", layer_key, params)

    def remove_raster_stretch(self, layer_key: str) -> None:
        """Remove stretching from a layer (reset to original)."""
        if layer_key in self._raster_stretch_settings:
            del self._raster_stretch_settings[layer_key]
        
        self._run_js_call("removeRasterStretch", layer_key)
        self.panel.log(f"Removed stretch from layer: {layer_key}")
        self._logger.info("Raster stretch removed from layer: %s", layer_key)

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
            self._add_line_mode_enabled = False
            self._add_text_mode_enabled = False
            self._annotation_line_start = None
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

    def _toolbar_zoom_to_asset(self, file_path: str) -> None:
        """Zoom/Focus on a specific asset instantly."""
        asset = self._search_result_assets_by_path.get(file_path)
        if not asset:
            return

        bounds = asset.get("bounds")
        if bounds:
            self._run_js_call(
                "instantFocusBounds",
                bounds.get("west"),
                bounds.get("south"),
                bounds.get("east"),
                bounds.get("north"),
            )
            self.panel.log(f"Focused on: {asset.get('file_name', 'asset')}")

    def _toolbar_fly_through(self, enabled: bool | None = None) -> bool:
        """Toggle fly-through path drawing mode."""
        next_state = (
            (not self._fly_through_mode_enabled) if enabled is None else bool(enabled)
        )
        self._fly_through_mode_enabled = next_state
        if next_state:
            # Disable other visualization modes in JS
            self._run_js_call("setComparatorMode", False)
            self._run_js_call("setFlyThroughMode", True)
            self._set_measurement_cursor_enabled(True)
            self.panel.log(
                "Fly Through mode enabled. Click to draw a path, Right-Click to finish."
            )
        else:
            self._run_js_call("stopFlyThrough")
            self._run_js_call("setFlyThroughMode", False)
            self._set_measurement_cursor_enabled(False)
            self.panel.log("Fly Through mode disabled.")
        return next_state

    def _toolbar_measure_distance(self, enabled: bool | None = None) -> bool:
        self._distance_measure_mode_enabled = (
            (not self._distance_measure_mode_enabled)
            if enabled is None
            else bool(enabled)
        )
        if self._distance_measure_mode_enabled:
            self._add_point_mode_enabled = False
            self._add_line_mode_enabled = False
            self._add_text_mode_enabled = False
            self._annotation_line_start = None
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
            if self._add_line_mode_enabled:
                self._add_line_mode_enabled = False
                self._annotation_line_start = None
                self._set_annotation_overlay_visible(False)
            if self._add_text_mode_enabled:
                self._add_text_mode_enabled = False
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
            from src_new.clients.desktop_search.measurement_tools.models import (
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
            from src_new.clients.desktop_search.measurement_tools.models import (
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
        from src_new.clients.desktop_search.measurement_worker import (
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
        from src_new.clients.desktop_search.measurement_worker import (
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
        self._add_line_mode_enabled = False
        self._add_text_mode_enabled = False
        self._annotation_line_start = None
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
        self._logger.debug("_toolbar_toggle_add_point_mode called: enabled=%s", enabled)
        next_state = (
            (not self._add_point_mode_enabled) if enabled is None else bool(enabled)
        )
        self._add_point_mode_enabled = next_state
        self._logger.debug("Add Point mode next_state=%s", next_state)
        if not next_state:
            # Don't hide placed annotations — they are persistent data
            self._set_measurement_cursor_enabled(False)
            self._run_js_call("setAnnotationDrawingMode", False)
            self.panel.log("Add Point tool disabled.")
            return False

        # Disable conflicting modes (exclusivity enforced per user request)
        self._distance_measure_mode_enabled = False
        self._shadow_height_mode_enabled = False
        self._pan_mode_enabled = False
        self._fly_through_mode_enabled = False  # Strict exclusivity
        self._add_line_mode_enabled = False
        self._add_text_mode_enabled = False
        self._annotation_line_start = None
        self._add_point_mode_enabled = True # Current mode
        self._run_js_call("setDistanceMeasureMode", False)
        self._run_js_call("setPanMode", False)
        self._run_js_call("setFlyThroughMode", False) # Sync JS state
        self._run_js_call("setSearchDrawMode", "none") # Disable Polygon Draw
        self._run_js_call("setAnnotationDrawingMode", True)
        
        self._logger.info("Add Point mode enabled, setting measurement cursor")
        self._set_measurement_cursor_enabled(True)
        self._set_annotation_overlay_visible(True)
        self.panel.log("Add Point enabled. Click map to place annotation points.")
        return True

    def _toolbar_toggle_add_line_mode(self, enabled: bool | None = None) -> bool:
        self._logger.debug("_toolbar_toggle_add_line_mode called: enabled=%s", enabled)
        next_state = (
            (not self._add_line_mode_enabled) if enabled is None else bool(enabled)
        )
        self._add_line_mode_enabled = next_state
        self._logger.debug("Add Line mode next_state=%s", next_state)
        if not next_state:
            self._annotation_line_start = None
            self._run_js_call("setLineDrawMode", False)
            self._run_js_call("clearLineDrawPreview")
            self._set_measurement_cursor_enabled(False)
            self.panel.log("Add Line tool disabled.")
            return False

        self._distance_measure_mode_enabled = False
        self._shadow_height_mode_enabled = False
        self._pan_mode_enabled = False
        self._fly_through_mode_enabled = False
        self._add_point_mode_enabled = False
        self._add_text_mode_enabled = False
        self._annotation_line_start = None
        self._run_js_call("setDistanceMeasureMode", False)
        self._run_js_call("setPanMode", False)
        self._run_js_call("setFlyThroughMode", False)
        self._run_js_call("setSearchDrawMode", "none")

        self._logger.info("Add Line mode enabled, setting measurement cursor")
        self._set_measurement_cursor_enabled(True)
        self._set_annotation_overlay_visible(True)
        self._run_js_call("setLineDrawMode", True)
        self.panel.log("Add Line enabled. Click start, then end point.")
        return True

    def _toolbar_toggle_add_text_mode(self, enabled: bool | None = None) -> bool:
        next_state = (
            (not self._add_text_mode_enabled) if enabled is None else bool(enabled)
        )
        self._add_text_mode_enabled = next_state
        if not next_state:
            self._set_measurement_cursor_enabled(False)
            self._run_js_call("setAnnotationDrawingMode", False)
            self.panel.log("Add Text Label tool disabled.")
            return False

        self._distance_measure_mode_enabled = False
        self._shadow_height_mode_enabled = False
        self._pan_mode_enabled = False
        self._fly_through_mode_enabled = False
        self._add_point_mode_enabled = False
        self._add_line_mode_enabled = False
        self._annotation_line_start = None
        self._run_js_call("setDistanceMeasureMode", False)
        self._run_js_call("setPanMode", False)
        self._run_js_call("setFlyThroughMode", False)
        self._run_js_call("setSearchDrawMode", "none")
        self._run_js_call("setAnnotationDrawingMode", True)

        self._set_measurement_cursor_enabled(True)
        self._set_annotation_overlay_visible(True)
        self.panel.log("Add Text Label enabled. Click map to place label.")
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
        self._add_line_mode_enabled = False
        self._add_text_mode_enabled = False
        self._annotation_line_start = None
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
            self._add_line_mode_enabled = False
            self._add_text_mode_enabled = False
            self._annotation_line_start = None
            self._fly_through_mode_enabled = False # Strict exclusivity
            self._set_annotation_overlay_visible(True)
            self._run_js_call("setAnnotationDrawingMode", True)
            self._shadow_height_mode_enabled = False
            self._pan_mode_enabled = False
            self._run_js_call("setDistanceMeasureMode", False)
            self._run_js_call("setPanMode", False)
            self._run_js_call("setFlyThroughMode", False) # Sync JS state
            
            self.set_search_draw_mode()
            self._set_measurement_cursor_enabled(True)
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
        self._set_project_modified(True)
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
        from src_new.shared.utils.geometry import parse_bounds_wkt_polygon

        bounds = parse_bounds_wkt_polygon(bounds_wkt)
        lon, lat = bounds.centroid()
        if not self._is_valid_lon_lat(lon, lat):
            return None
        return {"lon": lon, "lat": lat}

    def _asset_bounds(self, asset: dict) -> dict[str, float] | None:
        bounds_wkt = asset.get("bounds_wkt")
        if not bounds_wkt:
            return None
        from src_new.shared.utils.geometry import parse_bounds_wkt_polygon

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
        """Adjust the tile URL for server-side delivery if needed."""
        # Find the best version of the file (prioritize Web Mercator projected files)
        from pathlib import Path
        from urllib.parse import quote
        original_file_path = asset.get("file_path")
        if original_file_path:
            best_file_path = self._find_best_file_version(original_file_path)
            if best_file_path != original_file_path:
                self._logger.info(f"Optimizing tile URL for {asset.get('file_name')}: using {Path(best_file_path).name}")
                # Re-build the XYZ URL for the optimized file
                if "/cog/tiles/" in tile_url:
                    base_url = tile_url.split("?url=")[0]
                    tile_url = f"{base_url}?url={quote(best_file_path)}"

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
        # Even if the original file is missing (e.g. it was replaced by a COG version during ingestion),
        # we should still look for candidates based on its name.
        if not original_path.exists():
            self._logger.debug(f"Original file not found, searching for versions: {file_path}")

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
            self.panel.stretch_mode_combo,
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
            getattr(self.panel, "dem_stretch_mode_combo", None),
        ):
            if widget is not None:
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

        # Explicit DEM markers (dem, dtm, elevation)
        if any(marker in file_name for marker in ("dem", "dtm", "elevation")) or kind in ("dem", "elevation"):
            if file_path:
                self._dem_asset_kind_cache[file_path] = True
            return True

        # Explicit imagery markers (JP2, RGB, etc.) - NOT DEM
        imagery_extensions = (".jp2", ".j2k", ".jpeg", ".jpg", ".png", ".tif", ".tiff")
        imagery_keywords = ("rgb", "aerial", "ortho", "satellite", "imagery", "photo", "aot", "tci", "wvp", "scl")

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
            str(asset.get("kind", "")).lower() in ("dem", "elevation")
            or any(marker in str(file_name).lower() for marker in ("dem", "dtm", "elevation"))
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

        stretch_mode = "linear"
        if is_dem and hasattr(self.panel, "dem_stretch_mode_combo"):
            stretch_mode = str(
                self.panel.dem_stretch_mode_combo.currentData() or "linear"
            )
        elif hasattr(self.panel, "stretch_mode_combo"):
            stretch_mode = str(self.panel.stretch_mode_combo.currentData() or "linear")
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
            color_mode = str(self.panel.dem_color_mode_combo.currentData() or "gray")
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
            # FIX: Apply QGIS-style per-band Cumulative Count Cut (2% - 98%)
            # This fixes both the pitch-black 16-bit rendering and the bluish tint.
            # Passing a list of rescales allows TiTiler to stretch each band independently.
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
                    self._logger.debug(
                        f"Applied shared RGB stretch: {query}"
                    )
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
                self._logger.debug(
                    f"Applied per-band true color correction: {query}"
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
        msg_lower = message.lower()
        if self._layer_loading_active and (
            "fly-through started" in msg_lower
            or "fly-to bounds" in msg_lower
            or "fly-to lon=" in msg_lower
            or "fly-to: complete" in msg_lower
            or "flight started" in msg_lower
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
        from qtpy.QtWidgets import QApplication
        QApplication.processEvents()

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
