from __future__ import annotations

import datetime as dt
import json

from qtpy.QtCore import Qt, QObject, Signal as _Signal, QThreadPool

from src_new.clients.desktop_search.measurement_worker import MeasurementWorker
from src_new.clients.desktop_search.measurement_tools import (
    measure_distance,
    compute_fill_volume,
    compute_slope_aspect,
    measure_polygon_area,
    compute_viewshed,
    measure_shadow_height,
)


class MeasurementCoordinator:
    """Encapsulate async measurement execution and result recording."""

    def __init__(self, controller):
        self._controller = controller

    def enqueue_distance_measurement(
        self, lon1: float, lat1: float, lon2: float, lat2: float
    ) -> None:
        c = self._controller
        dem_path = self.selected_dem_path()

        # Distance measurement is pure math — run synchronously, no thread needed
        result = measure_distance(lon1, lat1, lon2, lat2, dem_path=dem_path)
        c._annotation_line_records.append(
            {
                "coords": [(lon1, lat1), (lon2, lat2)],
                "feature_type": "road",
                "length_m": float(result.distance_m),
                "width_m": 0.0,
                "condition": "intact",
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        )
        c._set_project_modified(True)
        d = result
        message = (
            "Distance/Azimuth: "
            f"2D={d.distance_m:.1f} m, az={d.azimuth_fwd_deg:.1f}°"
            + (f", 3D={d.distance_3d_m:.1f} m" if d.distance_3d_m is not None else "")
        )
        c.panel.log(message)
        self.record_measurement_result("Distance/Azimuth", message)

    def submit_measurement_job(self, name: str, task, formatter) -> None:
        c = self._controller

        # Emit progress start via signal (not @Slot method directly)
        if hasattr(c, "bridge") and hasattr(c.bridge, "loadingProgress"):
            c.bridge.loadingProgress.emit(0, f"Computing {name}")

        worker = MeasurementWorker(name=name, task=task)
        # Keep a strong Python reference so the worker and its signals QObject
        # stay alive until on_measurement_job_finished clears it.
        # Without this, Qt's autoDelete destroys the C++ side after run(),
        # leaving a dangling pointer that segfaults on the next pool.start().
        self._active_worker = worker
        worker.signals.finished.connect(
            lambda job_name, result, error, fmt=formatter: (
                self.on_measurement_job_finished(job_name, result, error, fmt)
            ),
            Qt.QueuedConnection,
        )
        c._measurement_pool.start(worker)
        c.panel.log(f"{name} started...")

    def on_measurement_job_finished(
        self, name: str, result: object, error: str, formatter
    ) -> None:
        c = self._controller
        self._active_worker = None  # release worker reference

        # Emit progress complete via signal (not @Slot method directly)
        if hasattr(c, "bridge") and hasattr(c.bridge, "loadingProgress"):
            c.bridge.loadingProgress.emit(100, "Complete")

        if error:
            c.panel.log(f"{name} failed: {error}")
            c._logger.error("Measurement job failed name=%s error=%s", name, error)
            return
        message = formatter(result)
        c.panel.log(message)
        self.record_measurement_result(name, message)

    def record_measurement_result(self, name: str, details: str) -> None:
        c = self._controller
        timestamp = dt.datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {name}: {details}"
        c._measurement_history.append(entry)
        c.panel.add_measurement_result_entry(entry)

    def clear_selected_measurement_result(self) -> None:
        c = self._controller
        row = c.panel.selected_measurement_result_row()
        if row < 0 or row >= len(c._measurement_history):
            return
        c._measurement_history.pop(row)
        c.panel.remove_measurement_result_row(row)

    def clear_all_measurement_results(self) -> None:
        c = self._controller
        c._measurement_history.clear()
        c.panel.clear_measurement_result_entries()

    def selected_dem_path(self) -> str | None:
        c = self._controller
        selected = c._selected_asset()
        if selected and c._is_dem_asset(selected):
            return str(selected.get("file_path") or "") or None
        if c._active_dem_search_layer_key:
            asset = c._search_result_assets_by_path.get(c._active_dem_search_layer_key)
            if isinstance(asset, dict):
                return str(asset.get("file_path") or "") or None
        for path, asset in c._search_result_assets_by_path.items():
            if c._search_layer_visibility.get(path, False) and c._is_dem_asset(asset):
                return str(asset.get("file_path") or "") or None
        return None

    def toolbar_measure_volume(self) -> bool | None:
        """Handle fill volume measurement from toolbar."""
        c = self._controller
        c._logger.info(
            "FillVolume: enter computing=%s active=%s",
            getattr(c, "_fill_volume_computing", False),
            getattr(c, "_fill_volume_active", False),
        )
        # Guard: ignore clicks while analysis is already running
        if getattr(c, "_fill_volume_computing", False):
            c.panel.log("Fill Volume: analysis in progress, please wait")
            return True  # keep button highlighted

        # Toggle off: clear overlays, keep polygon for re-use on next tap
        if getattr(c, "_fill_volume_active", False):
            c._logger.info("FillVolume: toggling off")
            c._fill_volume_active = False
            c._fill_volume_computing = False
            c._volume_mode_enabled = False
            c._set_measurement_cursor_enabled(False)
            c._polygon_drawing_context = "none"
            c._run_js_call("clearFillVolumes")
            c.panel.log("Fill Volume: off (polygon kept — tap again to re-analyse)")
            return False

        c._logger.info("FillVolume: checking DEM path")
        # Need a DEM
        dem_path = c._selected_dem_path()
        if not dem_path:
            c.panel.log("Select or show a DEM layer first.")
            return False

        c._logger.info("FillVolume: getting polygon dem_path=%s", dem_path)
        # Get polygon — use existing drawn polygon, or auto-derive from DEM bounds
        polygon = c._current_polygon_lonlat()
        if not polygon:
            polygon = c._dem_bounds_polygon(dem_path)

        c._logger.info("FillVolume: polygon=%s", "found" if polygon else "none")

        if not polygon:
            # No DEM bounds available — fall back to draw mode
            c._logger.info("FillVolume: no polygon, entering draw mode")
            c._distance_measure_mode_enabled = False
            c._run_js_call("setDistanceMeasureMode", False)
            c._add_point_mode_enabled = False
            c._set_annotation_overlay_visible(False)
            c._shadow_height_mode_enabled = False
            c._viewshed_mode_enabled = False
            c._polygon_area_mode_enabled = False
            c._pan_mode_enabled = False
            c._polygon_drawing_context = "measurement"
            c._volume_mode_enabled = True
            c._fill_volume_active = False
            c.set_search_draw_mode(enabled=True)
            c.panel.log("Fill Volume: draw a polygon on the DEM, then click Finish")
            return True

        # Polygon ready — submit analysis
        c._logger.info(
            "FillVolume: submitting analysis polygon_pts=%d", len(polygon)
        )
        c._fill_volume_computing = True

        # Wire a one-shot relay so the worker thread can safely post progress
        # to the main thread without calling emit() directly across threads
        # (direct cross-thread emit is undefined behaviour in Qt and causes
        # segfaults on repeated invocations).
        # We use a small QObject relay whose signal is connected with
        # Qt.QueuedConnection — Qt then marshals the call onto the main thread.
        class _ProgressRelay(QObject):
            progress = _Signal(int, str)

        relay = _ProgressRelay()
        relay.progress.connect(
            c.bridge.on_loading_progress,
            Qt.ConnectionType.QueuedConnection,
        )

        def task(_relay=relay) -> object:
            # _relay kept alive via default-arg capture for the worker's lifetime
            def progress_cb(pct: float, msg: str) -> None:
                _relay.progress.emit(int(pct), f"Fill Volume: {msg}")

            return compute_fill_volume(polygon, dem_path, progress_callback=progress_cb)

        def _fmt_vol(m3: float) -> str:
            """Format a volume in m³ with appropriate units."""
            if m3 >= 1_000_000_000:
                return f"{m3 / 1_000_000_000:.3f} km³"
            if m3 >= 1_000_000:
                return f"{m3 / 1_000_000:.3f} Mm³"
            return f"{m3:.3f} m³"

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
            c._logger.info(
                "FillVolume: on_done called error=%s result_type=%s",
                error or "none",
                type(result).__name__,
            )
            c._fill_volume_computing = False
            c._active_fill_volume_worker = None  # release worker reference
            c._active_fill_volume_pool = None  # release pool reference
            c.bridge.loadingProgress.emit(100, "Fill Volume: Complete")
            self.on_measurement_job_finished(name, result, error, fmt)
            if error or result is None:
                c._fill_volume_active = False
                return
            from src_new.clients.desktop_search.measurement_tools.models import (
                FillVolumeResult,
            )

            if not isinstance(result, FillVolumeResult) or not result.regions:
                c._run_js_call("clearFillVolumes")
                c._fill_volume_active = False
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
            c._run_js_call("drawFillVolumes", json.dumps(regions_payload))
            c._fill_volume_active = True

        worker = MeasurementWorker(name="Fill Volume", task=task)
        # Keep a strong Python reference so the worker (and its signals QObject)
        # stays alive until on_done fires and clears it.
        c._active_fill_volume_worker = worker
        # Use a dedicated parentless pool per analysis — avoids bus error on macOS
        # caused by QThreadPool(parent=QWidget) thread state corruption across runs.
        pool = QThreadPool()
        pool.setMaxThreadCount(1)
        c._active_fill_volume_pool = pool
        c._logger.info(
            "FillVolume: worker created id=%s pool_active=%s",
            id(worker),
            pool.activeThreadCount(),
        )
        worker.signals.finished.connect(
            lambda job_name, res, err, fmt=formatter: on_done(job_name, res, err, fmt),
            Qt.QueuedConnection,
        )
        c.bridge.loadingProgress.emit(0, "Fill Volume: Starting analysis")
        c._logger.info("FillVolume: calling pool.start")
        pool.start(worker)
        c._logger.info("FillVolume: pool.start returned")
        c.panel.log("Fill Volume: Starting analysis")
        c._volume_mode_enabled = False
        c._polygon_drawing_context = "none"
        c._set_measurement_cursor_enabled(False)
        return True  # keep button highlighted while computing

    def toolbar_measure_slope_aspect(self) -> bool | None:
        """Handle slope & aspect measurement from toolbar."""
        c = self._controller
        # Guard while computing
        if getattr(c, "_slope_aspect_computing", False):
            c.panel.log("Slope & Aspect: analysis in progress, please wait")
            return True

        # Need a DEM
        dem_path = c._selected_dem_path()
        if not dem_path:
            c.panel.log("Select or show a DEM layer first.")
            return False

        # Switch DEM colour mode to slope if not already slope/aspect
        mode = str(c.panel.dem_color_mode_combo.currentData() or "gray")
        if mode not in {"slope", "aspect"}:
            idx = c.panel.dem_color_mode_combo.findData("slope")
            if idx >= 0:
                c.panel.dem_color_mode_combo.setCurrentIndex(idx)
                c._viz.apply_dem_color_mode(log_to_panel=False)

        # No polygon yet — enter draw mode
        polygon = c._current_polygon_lonlat()
        if not polygon:
            c._distance_measure_mode_enabled = False
            c._run_js_call("setDistanceMeasureMode", False)
            c._add_point_mode_enabled = False
            c._set_annotation_overlay_visible(False)
            c._volume_mode_enabled = False
            c._polygon_area_mode_enabled = False
            c._pan_mode_enabled = False
            c._polygon_drawing_context = "measurement"
            c._slope_aspect_mode_enabled = True
            c.set_search_draw_mode(enabled=True)
            c._set_measurement_cursor_enabled(True)
            c.panel.log(
                "Draw a polygon on the map, then click Finish to calculate slope & aspect."
            )
            return True

        # Polygon ready — run async
        c._slope_aspect_computing = True
        c._polygon_drawing_context = "none"
        c._set_measurement_cursor_enabled(False)

        class _Relay(QObject):
            progress = _Signal(int, str)

        relay = _Relay()
        relay.progress.connect(
            c.bridge.on_loading_progress,
            Qt.ConnectionType.QueuedConnection,
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
            c._active_slope_aspect_worker = None
            c._active_slope_aspect_pool = None
            c.bridge.loadingProgress.emit(100, "Slope & Aspect: Complete")
            self.on_measurement_job_finished(name, result, error, fmt)
            callback = getattr(c, "_on_slope_aspect_done", None)
            if callable(callback):
                callback()

        from src_new.clients.desktop_search.measurement_worker import (
            MeasurementWorker,
        )

        worker = MeasurementWorker(name="Slope & Aspect", task=task)
        c._active_slope_aspect_worker = worker
        pool = QThreadPool()
        pool.setMaxThreadCount(1)
        c._active_slope_aspect_pool = pool
        worker.signals.finished.connect(
            lambda job_name, res, err, fmt=formatter: on_done(job_name, res, err, fmt),
            Qt.QueuedConnection,
        )
        c.bridge.loadingProgress.emit(0, "Slope & Aspect: Starting")
        pool.start(worker)
        c.panel.log("Slope & Aspect: Starting analysis")
        return True  # keep button highlighted

    def toolbar_measure_polygon_area(self) -> None:
        """Handle polygon area measurement from toolbar."""
        c = self._controller
        polygon = c._current_polygon_lonlat()
        if not polygon:
            # Disable conflicting modes
            c._distance_measure_mode_enabled = False
            c._run_js_call("setDistanceMeasureMode", False)
            c._add_point_mode_enabled = False
            c._set_annotation_overlay_visible(False)
            c._shadow_height_mode_enabled = False
            c._viewshed_mode_enabled = False
            c._volume_mode_enabled = False
            c._pan_mode_enabled = False
            c._run_js_call("setAnnotationDrawingMode", False)

            # Enable polygon drawing mode for measurement
            c._polygon_drawing_context = "measurement"
            c._polygon_area_mode_enabled = True
            c.set_search_draw_mode(enabled=True)
            c._set_measurement_cursor_enabled(True)
            c.panel.log(
                "Draw a polygon on the map, then click Finish to calculate area."
            )
            return

        def task() -> object:
            dem_path = c._selected_dem_path()
            return measure_polygon_area(polygon, dem_path=dem_path)

        def formatter(result: object) -> str:
            m = result
            compactness = m.compactness_index
            return (
                "Polygon Area: "
                f"planimetric={m.planimetric_area_m2:.2f} m2, perimeter={m.perimeter_m:.2f} m, compactness={compactness:.4f}"
            )

        self.submit_measurement_job("Polygon Area", task, formatter)
        # Clear the measurement mode flag after calculation
        c._polygon_area_mode_enabled = False
        c._polygon_drawing_context = "none"
        c._set_measurement_cursor_enabled(False)

    def toolbar_measure_viewshed(self) -> None:
        """Handle viewshed measurement from toolbar."""
        c = self._controller
        dem_path = c._selected_dem_path()
        if not dem_path:
            c.panel.log("Select or show a DEM layer first.")
            return
        if not c.state.clicked_points:
            # Disable conflicting modes
            c._distance_measure_mode_enabled = False
            c._run_js_call("setDistanceMeasureMode", False)
            c._add_point_mode_enabled = False
            c._set_annotation_overlay_visible(False)
            c._shadow_height_mode_enabled = False
            c._polygon_area_mode_enabled = False
            c._volume_mode_enabled = False
            c._run_js_call("setSearchDrawMode", "none")
            c._polygon_drawing_context = "none"
            c._pan_mode_enabled = False

            # Enable viewshed mode
            c._viewshed_mode_enabled = True
            c._set_measurement_cursor_enabled(True)
            c.panel.log(
                "Click on the map to select observer point for viewshed analysis."
            )
            return
        lon, lat = c.state.clicked_points[-1]

        def task() -> object:
            return compute_viewshed(lon, lat, dem_path, max_radius_m=400.0)

        def formatter(result: object) -> str:
            m = result
            return (
                "Viewshed/LOS: "
                f"visible={m.visible_area_m2:.1f} m2 / {m.total_area_m2:.1f} m2 "
                f"({100.0 * m.visible_fraction:.1f}%), max_dist={m.max_visible_distance_m:.1f} m"
            )

        self.submit_measurement_job("Viewshed / LOS", task, formatter)
        c._viewshed_mode_enabled = False
        c._set_measurement_cursor_enabled(False)

    def toolbar_measure_shadow_height(self) -> None:
        """Handle shadow height measurement from toolbar."""
        c = self._controller
        if len(c.state.clicked_points) < 2:
            c.panel.log(
                "Click object base and shadow tip points before Shadow Height."
            )
            return
        dem_path = c._selected_dem_path()
        (base_lon, base_lat), (tip_lon, tip_lat) = (
            c.state.clicked_points[-2],
            c.state.clicked_points[-1],
        )
        import datetime as dt
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

        self.submit_measurement_job("Shadow Height", task, formatter)
