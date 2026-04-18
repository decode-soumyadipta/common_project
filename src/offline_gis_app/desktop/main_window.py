from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow, QScrollArea, QSplitter

from offline_gis_app.desktop.app_mode import DesktopAppMode
from offline_gis_app.desktop.bridge import WebBridge
from offline_gis_app.desktop.control_panel import ControlPanel
from offline_gis_app.desktop.controller import DesktopController
from offline_gis_app.desktop.titiler_manager import TiTilerManager
from offline_gis_app.desktop.web_page import LoggingWebEnginePage


class MainWindow(QMainWindow):
    def __init__(self, app_mode: DesktopAppMode = DesktopAppMode.UNIFIED):
        super().__init__()
        self.app_mode = app_mode
        self.setWindowTitle(self._window_title_for_mode(app_mode))

        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            width = max(1200, int(available.width() * 0.9))
            height = max(760, int(available.height() * 0.9))
            self.resize(min(width, available.width()), min(height, available.height()))
        else:
            self.resize(1400, 860)

        self.panel = ControlPanel(self, app_mode=app_mode)
        self.panel_scroll = QScrollArea(self)
        self.panel_scroll.setWidgetResizable(True)
        self.panel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.panel_scroll.setWidget(self.panel)
        self.web_view = QWebEngineView(self)
        self.web_view.setPage(LoggingWebEnginePage(self.web_view))
        web_settings = self.web_view.settings()
        web_settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        web_settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        splitter = QSplitter(self)
        splitter.addWidget(self.panel_scroll)
        splitter.addWidget(self.web_view)
        splitter.setSizes([420, 1180])
        self.setCentralWidget(splitter)

        self.bridge = WebBridge()
        self.titiler_manager = TiTilerManager()
        self.channel = QWebChannel(self.web_view.page())
        self.channel.registerObject("bridge", self.bridge)
        self.web_view.page().setWebChannel(self.channel)
        self.controller = DesktopController(
            panel=self.panel,
            web_view=self.web_view,
            bridge=self.bridge,
            titiler_manager=self.titiler_manager,
            app_mode=app_mode,
        )

        html_path = Path(__file__).parent / "web_assets" / "index.html"
        self.web_view.setUrl(QUrl.fromLocalFile(str(html_path.resolve())))

    @staticmethod
    def _window_title_for_mode(app_mode: DesktopAppMode) -> str:
        if app_mode == DesktopAppMode.SERVER:
            return "Offline GIS Server Desktop"
        if app_mode == DesktopAppMode.CLIENT:
            return "Offline GIS Client Desktop"
        return "Offline 3D GIS Desktop"
