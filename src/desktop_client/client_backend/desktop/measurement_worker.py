from __future__ import annotations

from typing import Callable

from qtpy.QtCore import QObject, QRunnable, Signal


class MeasurementWorkerSignals(QObject):
    finished = Signal(str, object, str)


class MeasurementWorker(QRunnable):
    def __init__(self, name: str, task: Callable[[], object]):
        super().__init__()
        self._name = name
        self._task = task
        self.signals = MeasurementWorkerSignals()
        # Prevent Qt from deleting the C++ object after run() completes.
        # With autoDelete=True (the default) Qt destroys the QRunnable as soon
        # as the thread pool finishes it, which invalidates self.signals while
        # Python still holds a reference — causing a segfault on the next run.
        self.setAutoDelete(False)

    def run(self) -> None:  # type: ignore[override]
        # Initialise a thread-local PROJ database context so that pyproj
        # Transformer calls work correctly inside QThreadPool worker threads.
        try:
            from pyproj import network  # noqa: F401 — side-effect: bootstraps context
            from pyproj.crs import CRS
            CRS("EPSG:4326")  # warm up the thread-local PROJ context
        except Exception:  # pragma: no cover - optional warm-up, never fatal
            pass
        try:
            result = self._task()
            self.signals.finished.emit(self._name, result, "")
        except Exception as exc:  # pragma: no cover - runtime defensive branch
            self.signals.finished.emit(self._name, None, str(exc))
