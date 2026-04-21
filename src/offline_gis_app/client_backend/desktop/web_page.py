from __future__ import annotations

import logging

from qtpy.QtWebEngineWidgets import QWebEnginePage


class LoggingWebEnginePage(QWebEnginePage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._logger = logging.getLogger("desktop.web")

    def javaScriptConsoleMessage(self, level, message, line_number, source_id):  # noqa: N802
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            self._logger.error("JS console [%s] %s (line %s, source %s)", level, message, line_number, source_id)
        elif level == QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel:
            self._logger.warning("JS console [%s] %s (line %s, source %s)", level, message, line_number, source_id)
        else:
            self._logger.debug("JS console [%s] %s (line %s, source %s)", level, message, line_number, source_id)
        super().javaScriptConsoleMessage(level, message, line_number, source_id)
