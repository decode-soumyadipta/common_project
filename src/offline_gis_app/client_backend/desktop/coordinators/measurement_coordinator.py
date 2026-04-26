from __future__ import annotations

import datetime as dt

from qtpy.QtCore import Qt

from offline_gis_app.client_backend.desktop.measurement_worker import MeasurementWorker
from offline_gis_app.client_backend.measurement_tools import measure_distance


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
        if hasattr(c, 'bridge') and hasattr(c.bridge, 'loadingProgress'):
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
        if hasattr(c, 'bridge') and hasattr(c.bridge, 'loadingProgress'):
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
