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

    def run(self) -> None:  # type: ignore[override]
        try:
            result = self._task()
            self.signals.finished.emit(self._name, result, "")
        except Exception as exc:  # pragma: no cover - runtime defensive branch
            self.signals.finished.emit(self._name, None, str(exc))
