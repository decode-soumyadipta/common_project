from __future__ import annotations

import datetime as dt
import json
import logging
import math
from pathlib import Path
from typing import Callable

import httpx
from qtpy.QtCore import QObject, QThreadPool, QTimer, Signal
from qtpy.QtWebEngineWidgets import QWebEngineView

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
    RenderingCoordinator,
    DisplaySettingsCoordinator,
    UtilityCoordinator,
    SignalCoordinator,
    EventCoordinator,
)
from src_new.clients.desktop_search.coordinators.elevation_profile_coordinator import (
    ElevationProfileCoordinator,
)
from src_new.clients.desktop_search.control_panel import ControlPanel
from src_new.clients.desktop_search.performance_service import (
    DesktopPerformanceService,
)
from src_new.clients.desktop_search.state import DesktopState


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
        self.bridge.controller = self
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
        self._undo_stack: list[dict] = []
        self._redo_stack: list[dict] = []
        self._undo_redo_in_progress = False
        self._last_state_snapshot: dict | None = None
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
        self._comparator_visibility_snapshot: dict[str, bool] | None = None
        self._distance_measure_mode_enabled = False
        self._add_point_mode_enabled = False
        self._add_line_mode_enabled = False
        self._add_text_mode_enabled = False
        self._annotation_line_start: tuple[float, float] | None = None
        self._shadow_height_mode_enabled = False
        self._pan_mode_enabled = True
        self._polygon_area_mode_enabled = False
        self._polygon_draw_mode_enabled = False
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
        self._last_camera_state: dict | None = None

        # CRITICAL FIX: Layer visibility and rendering state management
        self._visibility_sync_in_progress = False  # Prevent concurrent visibility syncs
        self._visibility_toggle_debounce: dict[str, float] = {}  # Track last toggle time per path
        self._event_driven_sync_in_progress = False  # Prevent concurrent event-driven syncs
        self._standard_sync_in_progress = False  # Prevent concurrent standard syncs

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
        self._comparator_coordinator = self._comparator
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
        self._rendering = RenderingCoordinator(self)
        self._display_settings = DisplaySettingsCoordinator(self)
        self._utility = UtilityCoordinator(self)
        self._signal = SignalCoordinator(self)
        self._event = EventCoordinator(self)
        self._logger.info("Controller initialized mode=%s", self.app_mode.value)
        self._signal.connect_all_signals()
        self._apply_display_control_mode()
        self._last_state_snapshot = self.build_project_payload()
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

    def set_search_draw_mode(self, mode: str | bool | None = None) -> None:
        self._search.set_search_draw_mode(mode)

    def finish_search_polygon(self) -> None:
        self._search.finish_search_polygon()

    def clear_search_geometry(self) -> None:
        self._search.clear_search_geometry()

    def _set_annotation_overlay_visible(self, visible: bool) -> None:
        self._run_js_call("setAnnotationVisibility", bool(visible))

    def _set_search_aoi_visible(self, visible: bool) -> None:
        checked = bool(visible)
        self._logger.debug(
            "_set_search_aoi_visible checked=%s checkbox_checked=%s",
            checked,
            bool(self.panel.search_aoi_visible_check.isChecked()) if hasattr(self.panel, "search_aoi_visible_check") else None,
        )
        if hasattr(self.panel, "search_aoi_visible_check"):
            check_box = self.panel.search_aoi_visible_check
            if check_box.isChecked() != checked:
                check_box.blockSignals(True)
                check_box.setChecked(checked)
                check_box.blockSignals(False)
        self._logger.debug("_set_search_aoi_visible -> calling JS setSearchOverlayVisible(%s)", checked)
        self._run_js_call("setSearchOverlayVisible", checked)
        self._refresh_search_result_markers()

    def _refresh_search_result_markers(self) -> None:
        marker_payloads = []
        for asset in self._search_result_assets_by_path.values():
            payload = self._search_result_marker_payload(asset)
            if payload:
                marker_payloads.append(payload)
        self._logger.info(
            "_refresh_search_result_markers asset_count=%d payload_count=%d",
            len(self._search_result_assets_by_path),
            len(marker_payloads),
        )
        if marker_payloads:
            self._logger.info(
                "_refresh_search_result_markers sample_payload=%s",
                marker_payloads[0],
            )
        self._run_js_call("setSearchResultMarkers", marker_payloads)

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

    def on_comparator_pane_state(self, payload_json: str) -> None:
        self._comparator.on_comparator_pane_state(payload_json)

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
        """Undo the last visual or annotation project action."""
        if not self._undo_stack:
            self.panel.log("Nothing to undo.")
            return

        self._undo_redo_in_progress = True
        try:
            previous_state = self._undo_stack.pop()

            # Push current state to redo stack
            current_state = self.build_project_payload()
            self._redo_stack.append(current_state)

            # Apply the popped state
            self.apply_project_payload(previous_state)
            self._last_state_snapshot = previous_state

            self.panel.log("Undo successful.")
        except Exception as e:
            self._logger.error("Failed to undo last action: %s", e)
            self.panel.log(f"Undo failed: {e}")
        finally:
            self._undo_redo_in_progress = False

    def redo_last_action(self) -> None:
        """Redo the last undone project action."""
        if not self._redo_stack:
            self.panel.log("Nothing to redo.")
            return

        self._undo_redo_in_progress = True
        try:
            next_state = self._redo_stack.pop()

            # Push current state to undo stack
            current_state = self.build_project_payload()
            self._undo_stack.append(current_state)

            # Apply the popped state
            self.apply_project_payload(next_state)
            self._last_state_snapshot = next_state

            self.panel.log("Redo successful.")
        except Exception as e:
            self._logger.error("Failed to redo last action: %s", e)
            self.panel.log(f"Redo failed: {e}")
        finally:
            self._undo_redo_in_progress = False

    def build_project_payload(self) -> dict:
        return self._project_io.build_project_payload()

    def apply_project_payload(self, payload: dict, source_path: Path | None = None) -> None:
        """Apply project payload to restore project state."""
        self._project_io.apply_project_payload(payload, source_path)

    def _set_project_modified(self, modified: bool = True) -> None:
        """Update modification state and notify UI."""
        self._is_project_modified = modified

        if modified and not self._undo_redo_in_progress:
            try:
                # Capture baseline if missing
                if self._last_state_snapshot is None:
                    self._last_state_snapshot = self.build_project_payload()
                else:
                    current = self.build_project_payload()
                    import json
                    # Only push if states are different
                    if json.dumps(current, sort_keys=True) != json.dumps(self._last_state_snapshot, sort_keys=True):
                        self._undo_stack.append(self._last_state_snapshot)
                        if len(self._undo_stack) > 50:
                            self._undo_stack.pop(0)
                        self._last_state_snapshot = current
                        # Clear redo stack on new action
                        self._redo_stack.clear()
            except Exception as e:
                self._logger.warning("Failed to capture undo state snapshot: %s", e)

        name = self._project_path.stem if self._project_path else "untitled"
        self.project_metadata_changed.emit(name, modified)


    def _clear_project_state(self) -> None:
        self._project_io.clear_project_state()

    def _restore_annotations_on_map(self) -> None:
        self._annotation.restore_annotations_on_map()

    def _annotation_line_polygon_geojson(self) -> dict | None:
        return self._annotation._annotation_line_polygon_geojson()

    def _create_raster_asset_from_path(self, file_path: str) -> dict | None:
        return self._asset.create_raster_asset_from_path(file_path)

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
        self._display_settings.on_stretch_mode_changed(_index)

    def _on_dem_stretch_mode_changed(self, _index: int) -> None:
        self._display_settings.on_dem_stretch_mode_changed(_index)

    def _on_dem_slider_changed(self, _value: int) -> None:
        self._viz.on_dem_slider_changed(_value)

    def _on_dem_color_mode_changed(self, _index: int) -> None:
        self._viz.apply_dem_color_mode(log_to_panel=True)

    def apply_visual_settings(self, log_to_panel: bool = True) -> None:
        self._viz.apply_visual_settings(log_to_panel=log_to_panel)

    def _apply_imagery_stretch_mode(self, log_to_panel: bool = True) -> None:
        self._display_settings.apply_imagery_stretch_mode(log_to_panel=log_to_panel)

    def _apply_dem_stretch_mode(self, log_to_panel: bool = True) -> None:
        self._display_settings.apply_dem_stretch_mode(log_to_panel=log_to_panel)

    def _refresh_raster_layers_for_stretch(self, layer_kind: str | None = None) -> int:
        return self._display_settings.refresh_raster_layers_for_stretch(layer_kind=layer_kind)

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
            from qtpy.QtCore import QTimer
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
        self._event.on_map_click(lon, lat)

    def on_measurement(self, meters: float) -> None:
        self._event.on_measurement(meters)
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
        from src_new.clients.desktop_search.coordinators.utility_coordinator import UtilityCoordinator
        return UtilityCoordinator.line_length_m(coords)

    def apply_raster_stretch(self, layer_key: str, stretch_type: str, method: str, **params) -> None:
        """Apply raster stretching to imagery or DEM layers."""
        self._display_settings.apply_raster_stretch(layer_key, stretch_type, method, **params)

    def update_raster_stretch_params(self, layer_key: str, **params) -> None:
        """Update stretch parameters for real-time adjustment."""
        self._display_settings.update_raster_stretch_params(layer_key, **params)

    def remove_raster_stretch(self, layer_key: str) -> None:
        """Remove stretching from a layer."""
        self._display_settings.remove_raster_stretch(layer_key)

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
        # Legacy method - functionality moved to ElevationProfileCoordinator
        self._elevation_profile.activate()

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

    def available_layer_opacity_options(
        self, kind: str | None = None
    ) -> list[dict[str, object]]:
        options: list[dict[str, object]] = []
        normalized_kind = str(kind or "").strip().lower() or None
        for path, asset in self._search_result_assets_by_path.items():
            if not isinstance(asset, dict):
                continue
            is_dem = self._is_dem_asset(asset)
            asset_kind = "dem" if is_dem else "imagery"
            if normalized_kind and asset_kind != normalized_kind:
                continue
            label = str(asset.get("file_name") or Path(path).name or "Layer")
            if asset_kind:
                label = f"{label} [{asset_kind.upper()}]"
            options.append(
                {
                    "path": path,
                    "label": label,
                    "visible": bool(self._search_layer_visibility.get(path, False)),
                    "kind": asset_kind,
                }
            )
        return options

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

        bounds = self._asset_bounds(asset)
        if bounds:
            self._run_js_call(
                "instantFocusBounds",
                bounds.get("west"),
                bounds.get("south"),
                bounds.get("east"),
                bounds.get("north"),
            )
            self.panel.log(f"Focused on: {asset.get('file_name', 'asset')}")

    def _set_fly_through_overlay_active(self, active: bool) -> None:
        window = self.panel.window()
        if hasattr(window, "set_fly_through_active"):
            window.set_fly_through_active(active)

    def _set_fly_through_speed(self, value: float) -> None:
        self._run_js_call("setFlyThroughSpeed", float(value))

    def _seek_fly_through_progress(self, value: float) -> None:
        self._run_js_call("setFlyThroughPlaybackProgress", float(value))

    def _set_fly_through_pitch(self, value: float) -> None:
        self._run_js_call("setFlyThroughPitch", float(value))

    def _set_fly_through_height(self, value: float) -> None:
        self._run_js_call("setFlyThroughHeight", float(value))

    def _toggle_fly_through_playback(self) -> None:
        self._run_js_call("toggleFlyThroughPlayback")

    def _end_fly_through(self) -> None:
        self._run_js_call("endFlyThrough")
        self._toolbar_fly_through(enabled=False)

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
            self._set_fly_through_overlay_active(True)
            self._set_measurement_cursor_enabled(True)
            self.panel.log(
                "Fly Through mode enabled. Click to draw a path, Right-Click to finish, or use Stop Fly Through."
            )
        else:
            self._run_js_call("stopFlyThrough")
            self._run_js_call("setFlyThroughMode", False)
            self._set_fly_through_overlay_active(False)
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
            self._shadow_height_mode_enabled = False
        self._pan_mode_enabled = not self._distance_measure_mode_enabled
        self._last_distance_measurement_signature = None
        if self._distance_measure_mode_enabled:
            # Disable pan mode in JS so clicks reach the distance tool handler
            self._run_js_call("setPanMode", False)
            self._run_js_call("setSearchDrawMode", "none")
            self._logger.debug(
                "Distance mode enabled without hiding annotation overlay; preserving existing drawings"
            )
        self._run_js_call("setDistanceMeasureMode", self._distance_measure_mode_enabled)
        if not self._distance_measure_mode_enabled:
            self.panel.log("Distance tool disabled.")
            self._logger.info("Distance measure mode disabled")
            return False
        self.state.clicked_points.clear()
        self._run_js_call("clearMeasurementPreviewEntities")
        self.panel.log(
            "Distance tool enabled. Click first point, move cursor to preview, click second point to measure. "
            "Right-click to stop drawing."
        )
        self._logger.info("Distance measure mode enabled")
        return True

    def cancel_active_draw(self) -> bool:
        """Cancel only the current in-progress draw without deleting committed drawings."""
        cancelled = bool(
            self._add_line_mode_enabled
            or self._annotation_line_start is not None
            or self._distance_measure_mode_enabled
            or self._polygon_draw_mode_enabled
            or self._shadow_height_mode_enabled
            or self._fly_through_mode_enabled
        )
        if cancelled:
            self.state.clicked_points.clear()
        self._run_js_call("cancelActiveDraw")
        if self._annotation_line_start is not None:
            self._annotation_line_start = None
        if not cancelled and self._shadow_height_mode_enabled:
            self._shadow_height_mode_enabled = False
            self.panel.log("Shadow Height tool cancelled.")
            self._logger.info("Cancelled active shadow height tool")
            cancelled = True
        return cancelled

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
        self._measure.toolbar_measure_polygon_area()

    def _dem_bounds_polygon(self, dem_path: str) -> list[tuple[float, float]] | None:
        """Return a bounding-box polygon for the active DEM asset, or None."""
        return self._utility.dem_bounds_polygon(dem_path)

    def _toolbar_measure_slope_aspect(self) -> bool | None:
        """Handle slope & aspect measurement from toolbar."""
        return self._measure.toolbar_measure_slope_aspect()

    def _toolbar_measure_viewshed(self) -> None:
        self._measure.toolbar_measure_viewshed()

    def _toolbar_measure_shadow_height(self) -> None:
        self._measure.toolbar_measure_shadow_height()

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
            if not self._polygon_draw_active():
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
        self._set_fly_through_overlay_active(False)
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
            if not self._polygon_draw_active():
                self._set_measurement_cursor_enabled(False)
            self.panel.log("Add Line tool disabled.")
            return False

        self._distance_measure_mode_enabled = False
        self._shadow_height_mode_enabled = False
        self._pan_mode_enabled = False
        self._fly_through_mode_enabled = False
        self._add_point_mode_enabled = False
        self._add_text_mode_enabled = False
        self._polygon_draw_mode_enabled = False
        self._annotation_line_start = None
        self._run_js_call("setDistanceMeasureMode", False)
        self._run_js_call("setPanMode", False)
        self._run_js_call("setFlyThroughMode", False)
        self._set_fly_through_overlay_active(False)
        self._run_js_call("setSearchDrawMode", "none")
        self._run_js_call("setAnnotationDrawingMode", True)

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
            if not self._polygon_draw_active():
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
        self._set_fly_through_overlay_active(False)
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

    def _polygon_draw_active(self) -> bool:
        return bool(self._polygon_draw_mode_enabled)

    def _toolbar_add_polygon_annotation(self, enabled: bool | None = None) -> bool:
        return self._annotation.toolbar_add_polygon_annotation(enabled)

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
        # Fallback to utility coordinator which can calculate centroid from asset["bounds"]
        u_centroid = self._utility.asset_centroid(asset)
        if u_centroid:
            return u_centroid

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
        # Fallback to utility coordinator which can extract bounds from asset["bounds"]
        u_bounds = self._utility.asset_bounds(asset)
        if u_bounds:
            return u_bounds

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

    def _search_result_marker_payload(self, asset: dict) -> dict[str, object] | None:
        centroid = self._asset_centroid(asset)
        if not centroid:
            bounds = self._utility.asset_bounds(asset)
            if bounds:
                centroid = {
                    "lon": (float(bounds["west"]) + float(bounds["east"])) / 2.0,
                    "lat": (float(bounds["south"]) + float(bounds["north"])) / 2.0,
                }
                self._logger.info(
                    "_search_result_marker_payload using bounds fallback file=%s",
                    asset.get("file_name"),
                )
        if not centroid:
            return None
        lon = centroid.get("lon")
        lat = centroid.get("lat")
        if not self._is_valid_lon_lat(lon, lat):
            return None
        file_name = str(asset.get("file_name") or asset.get("file_path") or "Tile")
        file_path = str(asset.get("file_path") or "").replace("\\", "/")
        payload = {
            "lon": float(lon),
            "lat": float(lat),
            "text": file_name,
            "file_name": file_name,
            "file_path": file_path,
            "displayed": bool(self._search_layer_visibility.get(file_path, False)),
        }
        return payload


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
        return self._rendering.layer_options(asset, bounds)

    def _add_layer(self, asset: dict, options: dict) -> bool:
        return self._rendering.add_layer(asset, options)

    def _get_server_optimized_tile_url(self, asset: dict, tile_url: str) -> str:
        return self._rendering.get_server_optimized_tile_url(asset, tile_url)

    def _find_best_file_version(self, file_path: str) -> str:
        return self._rendering.find_best_file_version(file_path)

    def _normalize_tile_url_legacy(self, tile_url: str) -> str:
        return self._rendering.normalize_tile_url_legacy(tile_url)

    def _apply_server_performance_hints(self, options: dict) -> None:
        self._rendering.apply_server_performance_hints(options)

    def _add_dem_layer_event_driven(
        self, asset: dict, options: dict, from_search_results: bool
    ) -> bool:
        return self._rendering.add_dem_layer_event_driven(asset, options, from_search_results)

    def _add_imagery_layer_event_driven(
        self, asset: dict, options: dict, from_search_results: bool
    ) -> bool:
        return self._rendering.add_imagery_layer_event_driven(asset, options, from_search_results)

    def _apply_display_control_mode(self) -> None:
        """Apply display control mode based on visible layers."""
        self._display_settings.apply_display_control_mode()

    def _is_dem_asset(self, asset: dict) -> bool:
        """Detect if asset is DEM or RGB imagery using robust band count + data type analysis."""
        return self._utility.is_dem_asset(asset)

    def _raster_render_query(self, asset: dict) -> dict[str, object]:
        return self._rendering.raster_render_query(asset)

    @staticmethod
    def _is_valid_lon_lat(lon, lat) -> bool:
        return UtilityCoordinator.is_valid_lon_lat(lon, lat)

    @staticmethod
    def _is_near_global_bounds(bounds: dict[str, float] | None) -> bool:
        return UtilityCoordinator.is_near_global_bounds(bounds)

    @staticmethod
    def _normalize_path_for_compare(path: str) -> str:
        return UtilityCoordinator.normalize_path_for_compare(path)

    def _paths_equivalent(self, path_a: str, path_b: str) -> bool:
        return self._utility.paths_equivalent(path_a, path_b)

    def _asset_path_accessible_locally(self, asset: dict) -> bool:
        return self._utility.asset_path_accessible_locally(asset)

    def _validate_offline_endpoints(self) -> bool:
        return self._utility.validate_offline_endpoints()

    def _require_offline_endpoints(self, action: str) -> bool:
        return self._utility.require_offline_endpoints(action)

    @staticmethod
    def _is_offline_safe_url(url: str) -> bool:
        return UtilityCoordinator.is_offline_safe_url(url)

    def _set_layer_loading(self, active: bool, message: str) -> None:
        self._utility.set_layer_loading(active, message)

    def _on_layer_loading_timeout(self) -> None:
        self._utility.on_layer_loading_timeout()

    def on_js_log(self, level: str, message: str) -> None:
        self._event.on_js_log(level, message)

