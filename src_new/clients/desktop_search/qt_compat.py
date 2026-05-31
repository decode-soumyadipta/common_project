from __future__ import annotations

import os
import sys
from textwrap import dedent


DEFAULT_QT_API = "pyqt5"
_VALID_BACKENDS = {"pyqt5", "pyqt6"}
_BACKEND_ALIASES = {
    "pyqt": "pyqt5",
}


class QtDesktopRuntimeError(RuntimeError):
    """Raised when desktop Qt runtime requirements are not available."""


def _normalize_qt_api(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if not normalized:
        return DEFAULT_QT_API
    return _BACKEND_ALIASES.get(normalized, normalized)


def select_qt_api() -> str:
    """Resolve and persist the Qt backend selection for qtpy."""
    backend = _normalize_qt_api(os.environ.get("QT_API"))
    if backend not in _VALID_BACKENDS:
        allowed = ", ".join(sorted(_VALID_BACKENDS))
        raise QtDesktopRuntimeError(
            f"Unsupported QT_API='{backend}'. Allowed values: {allowed}."
        )
    os.environ["QT_API"] = backend
    return backend


def _clear_qtpy_modules() -> None:
    for module_name in list(sys.modules):
        if module_name == "qtpy" or module_name.startswith("qtpy."):
            del sys.modules[module_name]


def _backend_runtime_available(backend: str) -> bool:
    try:
        if backend == "pyqt5":
            from PyQt5.QtWebEngineWidgets import QWebEngineView  # noqa: F401
            from PyQt5.QtWidgets import QApplication  # noqa: F401

            return True
        if backend == "pyqt6":
            from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
            from PyQt6.QtWidgets import QApplication  # noqa: F401

            return True
        return False
    except Exception:
        return False


def _probe_qtpy_backend(expected_backend: str) -> str:
    _clear_qtpy_modules()
    os.environ["QT_API"] = expected_backend
    from qtpy import API_NAME
    from qtpy.QtWebEngineWidgets import QWebEnginePage as _QWebEnginePage
    from qtpy.QtWebEngineWidgets import QWebEngineSettings as _QWebEngineSettings
    from qtpy.QtWebEngineWidgets import QWebEngineView as _QWebEngineView
    from qtpy.QtWidgets import QApplication as _QApplication

    _ = (_QWebEnginePage, _QWebEngineSettings, _QWebEngineView, _QApplication)

    return (API_NAME or expected_backend).lower()


def ensure_desktop_qt_runtime() -> str:
    """Validate desktop Qt + WebEngine imports before loading GUI modules."""
    selected = select_qt_api()

    if not _backend_runtime_available(selected):
        raise QtDesktopRuntimeError(
            _desktop_runtime_help(
                selected, RuntimeError("Qt runtime not available for selected backend")
            )
        )

    try:
        return _probe_qtpy_backend(selected)
    except Exception as exc:  # pragma: no cover - runtime defensive branch
        raise QtDesktopRuntimeError(_desktop_runtime_help(selected, exc)) from exc


def _desktop_runtime_help(selected: str, exc: Exception) -> str:
    return dedent(
        f"""
        Desktop Qt runtime initialization failed using QT_API={selected!r}.
        Root cause: {exc}

        Recommended fixes:
        1. Recreate/update the project environment from environment.yml.
        2. Verify WebEngine import:
           python -c "from qtpy.QtWebEngineWidgets import QWebEngineView; print('QtWebEngine OK')"
          3. On Windows, install Microsoft Visual C++ Redistributable (x64) if imports still fail.
          4. Install desktop Qt runtime:
              python -m pip install "PyQt5>=5.15,<6.0" "PyQtWebEngine>=5.15,<6.0"

        Then rerun:
          python -m offline_gis_app.cli desktop-client
        """
    ).strip()
