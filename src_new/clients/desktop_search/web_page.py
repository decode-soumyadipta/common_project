from __future__ import annotations

import logging

from qtpy.QtWebEngineWidgets import QWebEnginePage, QWebEngineProfile


class LoggingWebEnginePage(QWebEnginePage):
    def __init__(self, profile: QWebEngineProfile | None = None, parent=None):
        if profile:
            super().__init__(profile, parent)
        else:
            super().__init__(parent)
        self._logger = logging.getLogger("desktop.web")

    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            self._logger.error(
                "JS console [%s] %s (line %s, source %s)",
                level,
                message,
                line_number,
                source_id,
            )
        elif level == QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel:
            self._logger.warning(
                "JS console [%s] %s (line %s, source %s)",
                level,
                message,
                line_number,
                source_id,
            )
        else:
            self._logger.debug(
                "JS console [%s] %s (line %s, source %s)",
                level,
                message,
                line_number,
                source_id,
            )
        super().javaScriptConsoleMessage(level, message, line_number, source_id)
