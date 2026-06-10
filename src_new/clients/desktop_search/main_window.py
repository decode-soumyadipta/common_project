"""Main window module for the Offline GIS Desktop application.

This module provides the main window UI components.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import cv2
import numpy as np
from qtpy.QtCore import QEventLoop, QRect, QSize, Qt, QTimer, QUrl
from qtpy.QtGui import (
    QAction,
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QIcon,
    QImage,
    QPainter,
    QPen,
)
from qtpy.QtWebChannel import QWebChannel
from qtpy.QtWebEngineWidgets import QWebEngineSettings, QWebEngineView
from qtpy.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStyle,
    QToolBar,
    QVBoxLayout,
)

from src_new.clients.desktop_search.app_mode import DesktopAppMode
from src_new.clients.desktop_search.bridge import WebBridge
from src_new.clients.desktop_search.control_panel import ControlPanel
from src_new.clients.desktop_search.controller import DesktopController
from src_new.clients.desktop_search.icon_registry import IconRegistry
from src_new.clients.desktop_search.status_bar import GISStatusBar
from src_new.clients.desktop_search.titiler_manager import TiTilerManager
from src_new.clients.desktop_search.ui.overlays import (
    BusyOverlay,
    FlyThroughHeightSlider,
    FlyThroughTimelineBar,
    MapOverlayControls,
)
from src_new.clients.desktop_search.web_page import LoggingWebEnginePage

LAYER_COMPOSITOR_LITERAL = "Layer Compositor"
ASSET1_PICK_LITERAL = "Asset 1: (Click on map to pick)"
ASSET2_PICK_LITERAL = "Asset 2: (Click on map to pick)"
LABEL_SUBTEXT_STYLE = "color: #64748b; font-size: 11px; font-weight: normal;"



class VideoExportSettingsDialog(QDialog):
    def __init__(self, parent=None, duration_ms=0):
        super().__init__(parent)
        self.setWindowTitle("Video Export Settings")
        self.setModal(True)
        self.setMinimumWidth(380)
        
        self.duration_sec = float(duration_ms) / 1000.0
        
        # Format duration string
        h = int(self.duration_sec // 3600)
        m = int((self.duration_sec % 3600) // 60)
        s = int(self.duration_sec % 60)
        
        if h > 0:
            self.duration_str = f"{h:02d}:{m:02d}:{s:02d}"
        else:
            self.duration_str = f"{m:02d}:{s:02d}"
            
        self._init_ui()
        self.update_estimates()
        
    def _init_ui(self):
        from qtpy.QtWidgets import QGroupBox, QLabel, QPushButton, QVBoxLayout
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title = QLabel("Export Fly-Through Video")
        title.setObjectName("titleLabel")
        layout.addWidget(title)
        
        # Quality Option
        quality_layout = QHBoxLayout()
        quality_label = QLabel("Video Quality:")
        self.quality_combo = QComboBox()
        self.quality_combo.addItem("High (100% Resolution)", (1.0, 5000000))
        self.quality_combo.addItem("Medium (70% Resolution)", (0.7, 2500000))
        self.quality_combo.addItem("Low (50% Resolution)", (0.5, 1000000))
        quality_layout.addWidget(quality_label)
        quality_layout.addWidget(self.quality_combo)
        layout.addLayout(quality_layout)
        
        # FPS Option
        fps_layout = QHBoxLayout()
        fps_label = QLabel("Frame Rate:")
        self.fps_combo = QComboBox()
        self.fps_combo.addItem("30 FPS (Smooth)", 30.0)
        self.fps_combo.addItem("24 FPS (Standard)", 24.0)
        self.fps_combo.addItem("15 FPS (Fast Export)", 15.0)
        fps_layout.addWidget(fps_label)
        fps_layout.addWidget(self.fps_combo)
        layout.addLayout(fps_layout)
        
        # Estimates GroupBox
        group = QGroupBox("Video Information & Estimates")
        group_layout = QVBoxLayout(group)
        group_layout.setSpacing(8)
        
        self.lbl_len = QLabel()
        self.lbl_size = QLabel()
        self.lbl_time = QLabel()
        
        group_layout.addWidget(self.lbl_len)
        group_layout.addWidget(self.lbl_size)
        group_layout.addWidget(self.lbl_time)
        layout.addWidget(group)
        
        # Connect signals
        self.quality_combo.currentIndexChanged.connect(self.update_estimates)
        self.fps_combo.currentIndexChanged.connect(self.update_estimates)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        
        self.btn_export = QPushButton("Start Export")
        self.btn_export.setObjectName("exportButton")
        self.btn_export.clicked.connect(self.accept)
        
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_export)
        layout.addLayout(btn_layout)
        
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
                color: #1a1a2e;
                border: 1px solid #c5d3e8;
                border-radius: 6px;
            }
            QLabel {
                color: #1e293b;
                font-size: 12px;
            }
            QLabel#titleLabel {
                color: #1a3a6e;
                font-size: 15px;
                font-weight: bold;
                margin-bottom: 4px;
            }
            QComboBox {
                background-color: #f0f4fa;
                color: #1e293b;
                border: 1px solid #b0c0d8;
                border-radius: 4px;
                padding: 5px 8px;
                min-width: 190px;
            }
            QComboBox:hover {
                border-color: #2563eb;
            }
            QComboBox::drop-down {
                border: none;
            }
            QGroupBox {
                border: 1px solid #c5d3e8;
                border-radius: 5px;
                margin-top: 8px;
                padding: 10px;
                background-color: #f5f8fe;
                font-weight: bold;
                color: #1a3a6e;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                color: #1a3a6e;
            }
            QPushButton {
                background-color: #f0f4fa;
                color: #1e293b;
                border: 1px solid #b0c0d8;
                border-radius: 4px;
                padding: 7px 18px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #e2eaf6;
                border-color: #2563eb;
                color: #1a3a6e;
            }
            QPushButton#exportButton {
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 4px;
            }
            QPushButton#exportButton:hover {
                background-color: #1d4ed8;
            }
        """)
        
    def update_estimates(self):
        _scale, bitrate = self.quality_combo.currentData()
        fps = self.fps_combo.currentData()
        
        # Calculate estimates
        total_frames = round(self.duration_sec * fps)
        est_size_mb = (self.duration_sec * bitrate) / (8.0 * 1024.0 * 1024.0)
        est_time_sec = total_frames * 0.08  # ~80ms per frame
        
        self.lbl_len.setText(f"Length:  {self.duration_str}")
        self.lbl_size.setText(f"Estimated File Size:  ~{est_size_mb:.1f} MB")
        
        if est_time_sec >= 60:
            time_str = f"~{int(est_time_sec // 60)}m {int(est_time_sec % 60)}s"
        else:
            time_str = f"~{int(est_time_sec)} seconds"
        self.lbl_time.setText(f"Estimated Generation Time:  {time_str}")
        
    def get_selected_settings(self):
        scale, _ = self.quality_combo.currentData()
        fps = self.fps_combo.currentData()
        return scale, fps


class MainWindow(QMainWindow):
    """Main application window for the Offline GIS Desktop.

    Provides the primary UI including:
    - Toolbar with visualization, measurement, and navigation tools
    - Control panel for data management
    - Web view for Cesium-based 3D/2D map display
    - Status bar with coordinate and camera information
    - Overlay controls for layer management

    Attributes:
        IMAGERY_ONLY_ACTIONS: Actions available only for imagery layers.
        DEM_ONLY_ACTIONS: Actions available only for DEM layers.
        TOGGLE_ACTIONS: Actions that can be toggled on/off.
        TOOLBAR_GROUPS: Organized groups of toolbar actions.
    """

    IMAGERY_ONLY_ACTIONS: set[str] = set()
    DEM_ONLY_ACTIONS: set[str] = {
        "Elevation Profile",
    }
    TOGGLE_ACTIONS: set[str] = {
        "Comparator",
        "Distance / Azimuth",
        "Elevation Profile",
        "Add Point",
        "Add Line",
        "Add Polygon",
        "Add Text Label",
        "Fly Through",
    }
    TOOLBAR_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
        (
            "visualization",
            (
                ("Comparator", "comparator"),
                ("Fly Through", "fly_through"),
            ),
        ),
        (
            "measurement",
            (
                ("Distance / Azimuth", "measure_distance"),
                ("Elevation Profile", "elevation_profile"),
                ("Clear Last", "clear_last"),
            ),
        ),
        (
            "annotation",
            (
                ("Add Point", "annotate_point"),
                ("Add Line", "annotate_line"),
                ("Add Polygon", "annotate_polygon"),
                ("Add Text Label", "annotate_text"),
            ),
        ),
        (
            "navigation",
            (
                ("Zoom In", "zoom_in"),
                ("Zoom Out", "zoom_out"),
                ("Zoom to Extent", "zoom_extent"),
            ),
        ),
        (
            "file",
            (
                ("Add Vector", "open_vector"),
                ("Add Raster Layer", "open_raster"),
                ("Save Project", "save_project"),
                ("Export", "export_gpkg"),
            ),
        ),
    )
    HELP_URL = "https://example.com/docs"

    def __init__(self, app_mode: DesktopAppMode = DesktopAppMode.UNIFIED):
        """Initialize the main window.

        Args:
            app_mode: Application mode (UNIFIED, CLIENT, or SERVER).
        """
        super().__init__()
        self.app_mode = app_mode
        self._project_name = "untitled"
        self._is_modified = False
        self._update_window_title()

        # Apply resGIS logo as the window icon (title-bar corner, taskbar, dock)
        import pathlib as _pathlib
        _logo = _pathlib.Path(__file__).resolve().parent.parent.parent / "assets" / "resGIS_logo.png"
        if _logo.exists():
            self.setWindowIcon(QIcon(str(_logo)))

        # Initialize database when in server mode
        if app_mode in (DesktopAppMode.UNIFIED, DesktopAppMode.SERVER):
            try:
                from src_new.shared.db.session import init_db

                init_db()
                logging.getLogger("desktop").info("Database initialized successfully")
            except Exception as exc:
                logging.getLogger("desktop").error(
                    "Database initialization failed: %s", exc
                )

        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            width = max(1200, int(available.width() * 0.9))
            height = max(760, int(available.height() * 0.9))
            self.resize(min(width, available.width()), min(height, available.height()))
        else:
            self.resize(1400, 860)

        self.main_toolbar: QToolBar | None = None
        self.toolbar_actions: dict[str, QAction] = {}
        self.visualization_actions: list[QAction] = []
        self.measurement_actions: list[QAction] = []
        self.action_group_by_label: dict[str, str] = {}

        if app_mode != DesktopAppMode.SERVER:
            (
                self.main_toolbar,
                self.toolbar_actions,
                self.visualization_actions,
                self.measurement_actions,
                self.action_group_by_label,
            ) = self._create_main_toolbar()
            self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.main_toolbar)

        self._toolbar_layer_context: str = "none"
        self._visualization_tools_enabled: bool = True
        self._measurement_tools_enabled: bool = True

        self.panel = ControlPanel(self, app_mode=app_mode)
        self.panel_scroll = QScrollArea(self)
        self.panel_scroll.setWidgetResizable(True)
        self.panel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.panel_scroll.setWidget(self.panel)
        from qtpy.QtWebEngineWidgets import QWebEngineProfile
        
        # Create a unique profile name based on app mode to isolate caches (e.g. Ingest vs Search) This prevents "Access is denied" errors in the GPUCache directory.
        profile_name = f"OfflineGIS_{self.app_mode.value}"
        self.profile = QWebEngineProfile(profile_name, self)
        
        # Disable disk cache so local JS/CSS changes are always picked up.
        self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
        self.profile.setHttpCacheMaximumSize(0)

        # Set up mode-specific cache paths in temp directory
        import tempfile
        from pathlib import Path
        cache_root = Path(tempfile.gettempdir()) / f"offline_gis_webengine_{self.app_mode.value}"
        cache_root.mkdir(parents=True, exist_ok=True)
        self.profile.setCachePath(str(cache_root))
        self.profile.setPersistentStoragePath(str(cache_root / "storage"))

        self.web_view = QWebEngineView(self)
        self.web_view.setPage(LoggingWebEnginePage(self.profile, self.web_view))
        
        web_settings = self.web_view.settings()
        web_settings.setAttribute(
            QWebEngineSettings.LocalContentCanAccessRemoteUrls, True
        )
        web_settings.setAttribute(
            QWebEngineSettings.LocalContentCanAccessFileUrls, True
        )
        
        self.busy_overlay = BusyOverlay(self)
        self.busy_overlay.hide()

        # ── Elevation profile panel (hidden until first profile) ──────────
        # It sits ONLY under the map column (web_view), not the full window. We achieve this by putting the web_view in its own vertical splitter.
        from src_new.clients.desktop_search.elevation_profile_panel import (
            ElevationProfilePanel,
        )

        self.elevation_profile_panel = ElevationProfilePanel(self)
        self.elevation_profile_panel.hide()
        self.elevation_profile_panel.close_requested.connect(
            self._on_elevation_profile_close
        )

        # ── QStackedWidget canvas_stack for switching between Cesium (web_view) and pyqtgraph (lidar_viewer) ──
        from qtpy.QtWidgets import QStackedWidget

        from src_new.clients.desktop_search.ui.lidar_viewer import LiDARViewerWidget

        self.canvas_stack = QStackedWidget(self)
        self.canvas_stack.addWidget(self.web_view)

        self.lidar_viewer = LiDARViewerWidget(self, controller=None)
        self.canvas_stack.addWidget(self.lidar_viewer)

        # ── Map column: canvas_stack (top) | profile panel (bottom) ───────────
        self._map_v_splitter = QSplitter(Qt.Orientation.Vertical, self)
        self._map_v_splitter.addWidget(self.canvas_stack)
        self._map_v_splitter.addWidget(self.elevation_profile_panel)
        self._map_v_splitter.setCollapsible(0, False)
        self._map_v_splitter.setCollapsible(1, True)

        # ── Horizontal splitter: control panel | map column ───────────────
        self._h_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._h_splitter.addWidget(self.panel_scroll)
        self._h_splitter.addWidget(self._map_v_splitter)
        if app_mode == DesktopAppMode.CLIENT:
            self._h_splitter.setSizes([500, 1100])
        else:
            self._h_splitter.setSizes([420, 1180])

        self.setCentralWidget(self._h_splitter)

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
            toolbar_context_callback=self.set_toolbar_layer_context
            if app_mode != DesktopAppMode.SERVER
            else None,
        )
        self.panel.api_client = self.controller.api
        self.lidar_viewer.controller = self.controller
        self.controller.project_metadata_changed.connect(self.set_project_info)
        self._last_search_params = {}

        if app_mode == DesktopAppMode.CLIENT:
            self._create_menu_bar()


        self.map_overlay_controls = MapOverlayControls(self, self.controller)
        self.fly_through_timeline_bar = FlyThroughTimelineBar(self, self.controller)
        self.fly_through_height_slider = FlyThroughHeightSlider(self, self.controller)
        # Show map overlay controls by default
        self.map_overlay_controls.show()

        # ── QGIS-style status bar ────────────────────────────────────────
        self.gis_status_bar = GISStatusBar(self)
        self.setStatusBar(self.gis_status_bar)
        self.bridge.mouseCoordinates.connect(self.gis_status_bar.on_mouse_coordinates)
        self.bridge.cameraChanged.connect(self.gis_status_bar.on_camera_changed)
        self.bridge.cameraChanged.connect(self.panel.update_camera_info)
        self.bridge.loadingProgress.connect(self.gis_status_bar.on_loading_progress)
        self.bridge.renderBusy.connect(self.gis_status_bar.on_render_busy)
        self.bridge.measureCursorChanged.connect(self._on_measure_cursor_changed)
        self.bridge.profileCursorMoved.connect(self._on_profile_cursor_moved)
        self.bridge.flyThroughPlaybackStateChanged.connect(
            self._on_fly_through_playback_state_changed
        )
        self.bridge.flyThroughPlaybackProgressChanged.connect(
            self._on_fly_through_playback_progress_changed
        )
        self._measure_crosshair_cursor = self._build_crosshair_cursor()
        self._measure_cursor_active = False
        # Event filter to re-apply cursor on every mouse move (QWebEngineView resets it)
        self.web_view.installEventFilter(self)
        vp = self.web_view.focusProxy()
        if vp:
            vp.installEventFilter(self)
        # Wire elevation profile completion → uncheck toolbar button
        self.controller._elevation_profile.on_complete = (
            self._on_elevation_profile_complete
        )
        # Wire coordinator to use the embedded panel
        self.controller._elevation_profile.set_panel(self.elevation_profile_panel)

        self._escape_cancel_action = QAction("Cancel Active Draw", self)
        self._escape_cancel_action.setShortcut("Esc")
        self._escape_cancel_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self._escape_cancel_action.triggered.connect(self._cancel_active_draw)
        self.addAction(self._escape_cancel_action)

        for label, action in self.toolbar_actions.items():
            if action.isCheckable():
                action.toggled.connect(
                    lambda checked, action_label=label: (
                        self._on_toolbar_action_triggered(action_label, checked)
                    )
                )
            else:
                action.triggered.connect(
                    lambda _checked=False, action_label=label: (
                        self._on_toolbar_action_triggered(action_label, False)
                    )
                )

        # Path to web_assets/index.html in the same directory as this file
        base_path = Path(__file__).resolve().parent / "web_assets" / "index.html"

        if not base_path.exists():
            logging.getLogger("desktop").error(
                f"index.html not found at {base_path}"
            )
            raise FileNotFoundError(f"index.html not found at {base_path}")

        logging.getLogger("desktop").info(
            f"Loading CesiumJS from {base_path}"
        )

        html_url = QUrl.fromLocalFile(str(base_path.resolve()))
        html_url.setQuery(f"v={int(time.time())}")
        self.web_view.setUrl(html_url)

    def closeEvent(self, event) -> None:
        """Handle window close to release WebEngine resources properly."""
        if hasattr(self, "web_view") and self.web_view:
            # Detach the page from the view and profile before destruction to prevent "Expect troubles" warnings.
            self.web_view.setPage(None)
            self.web_view.deleteLater()
        
        if hasattr(self, "profile") and self.profile:
            self.profile.deleteLater()
            
        super().closeEvent(event)

    def set_canvas_index(self, index: int) -> None:
        """Switch the central stacked widget view and toggle floating overlays accordingly."""
        if not hasattr(self, "canvas_stack"):
            return
            
        self.canvas_stack.setCurrentIndex(index)
        
        if index == 1:
            # Native 3D viewer active - hide Cesium floating overlay widgets
            if hasattr(self, "map_overlay_controls") and self.map_overlay_controls:
                self.map_overlay_controls.hide()
            if hasattr(self, "fly_through_timeline_bar") and self.fly_through_timeline_bar:
                self.fly_through_timeline_bar.hide()
            if hasattr(self, "fly_through_height_slider") and self.fly_through_height_slider:
                self.fly_through_height_slider.hide()
        else:
            # Cesium active - show/restore the default floating overlays
            if hasattr(self, "controller") and self.controller:
                self.controller._run_js_call("requestSceneRender")
            if hasattr(self, "map_overlay_controls") and self.map_overlay_controls:
                self.map_overlay_controls.show()
                self.map_overlay_controls.update_position()
            if hasattr(self, "fly_through_timeline_bar") and self.fly_through_timeline_bar:
                if getattr(self.fly_through_timeline_bar, "_active", False):
                    self.fly_through_timeline_bar.show()
                    self.fly_through_timeline_bar.update_position()
            if hasattr(self, "fly_through_height_slider") and self.fly_through_height_slider:
                if getattr(self.fly_through_height_slider, "_active", False):
                    self.fly_through_height_slider.show()
                    self.fly_through_height_slider.update_position()

    @staticmethod
    def _ensure_cesium_assets(web_assets_dir: Path) -> None:
        """Ensure cesium/ and basemap/ directories are accessible from the web_assets directory.

        The canonical Cesium build files and offline basemap tiles live in
        desktop/web_assets/cesium/ and desktop/web_assets/basemap/ respectively.
        index.html references ``./cesium/Cesium.js`` and bridge.js references
        ``./basemap/xyz/`` relative to itself, so we need entries next to
        index.html that resolve to the canonical locations.  On macOS / Linux we
        create relative symlinks; on Windows we copy the directory trees.
        """
        import logging
        import os
        import platform
        import shutil

        logger = logging.getLogger("desktop.cesium_assets")
        is_windows = platform.system().lower() == "windows"
        # Canonical assets (cesium, basemap) are in desktop_client/desktop_assets/web_assets/
        desktop_assets_web = (
            web_assets_dir.parent.parent / "desktop_assets" / "web_assets"
        )
        
        # Fallback if the above doesn't exist (e.g. if we are in a different structure)
        if not desktop_assets_web.exists():
             desktop_assets_web = (
                Path(__file__).resolve().parents[3]
                / "src"
                / "desktop_client"
                / "desktop_assets"
                / "web_assets"
            )

        desktop_web_assets = desktop_assets_web # Both are in the same root now

        def _link_dir(
            name: str,
            required_file: str | None = None,
            source_override: Path | None = None,
        ) -> None:
            link_path = web_assets_dir / name
            
            # 1. If it's already there and correct, we're done.
            if link_path.exists():
                if not required_file or (link_path / required_file).exists():
                    logger.debug("%s assets already present at %s", name, link_path)
                    return

            # 2. Otherwise, look for canonical source to link/copy from
            canonical = (
                source_override if source_override else (desktop_web_assets / name)
            )

            if not canonical.exists():
                logger.warning(
                    "Canonical %s directory not found at %s. Skipping.",
                    name,
                    canonical,
                )
                return

            if required_file and not (canonical / required_file).exists():
                logger.warning(
                    "%s not found in %s. Run scripts/setup_cesium_assets.py to download it.",
                    required_file,
                    canonical,
                )
                return

            # Already correct?
            if link_path.exists() or link_path.is_symlink():
                if link_path.is_symlink():
                    resolved = link_path.resolve()
                    if resolved == canonical.resolve():
                        logger.debug("%s symlink already correct", name)
                        return
                    link_path.unlink()
                elif link_path.is_dir():
                    if required_file and (link_path / required_file).exists():
                        logger.debug(
                            "%s directory already present with %s", name, required_file
                        )
                        return
                    if not required_file:
                        logger.debug("%s directory already present", name)
                        return
                    shutil.rmtree(str(link_path))
                else:
                    link_path.unlink()

            if is_windows:
                logger.info("Windows: copying %s assets to %s", name, link_path)
                shutil.copytree(str(canonical), str(link_path))
            else:
                try:
                    rel_path = os.path.relpath(str(canonical), str(link_path.parent))
                    link_path.symlink_to(rel_path)
                    logger.info(
                        "Created %s symlink: %s -> %s", name, link_path, rel_path
                    )
                except OSError:
                    logger.warning("Symlink failed for %s, falling back to copy", name)
                    shutil.copytree(str(canonical), str(link_path))

        _link_dir("cesium", required_file="Cesium.js")
        _link_dir("basemap", source_override=desktop_assets_web / "basemap")

    def _set_visualization_tools_visible(self, visible: bool) -> None:
        """Show or hide visualization tools in the toolbar.

        Args:
            visible: True to show tools, False to hide.
        """
        self._visualization_tools_enabled = bool(visible)
        self._refresh_toolbar_action_state()
        if hasattr(self, "controller") and not visible:
            self.controller.on_toolbar_group_disabled("visualization")
            pass

    def _set_measurement_tools_visible(self, visible: bool) -> None:
        """Show or hide measurement tools in the toolbar.

        Args:
            visible: True to show tools, False to hide.
# TODO: Refactor for cognitive complexity
# TODO: Refactor for cognitive complexity
        """
        self._measurement_tools_enabled = bool(visible)
        self._refresh_toolbar_action_state()
        if hasattr(self, "controller") and not visible:
            self.controller.on_toolbar_group_disabled("measurement")

    def _on_toolbar_action_triggered(self, action_label: str, checked: bool) -> None:
        """Handle toolbar action triggers by coordinating with the controller and refreshing UI state."""
        action = self.toolbar_actions.get(action_label)
        if action is None:
            return

        if self._handle_toolbar_special_actions(action_label, checked):
            return

        # Delegate all other actions to the controller
        final_state = self.controller.handle_toolbar_action(action_label, checked=checked)
        # Sync the action's checked state if the controller returned a definitive boolean
        if action.isCheckable() and isinstance(final_state, bool):
            action.blockSignals(True)
            action.setChecked(final_state)
            action.blockSignals(False)

        self._handle_toolbar_exclusivity(action_label, action)

        # --- Overlay Management ---
        if hasattr(self, "map_overlay_controls"):
            # Update AOI polygon visibility context
            is_special = any(
                self.toolbar_actions.get(label).isChecked() 
                for label in ["Comparator"] 
                if self.toolbar_actions.get(label)
            )
            self.map_overlay_controls.set_special_mode(is_special)

        # --- Final UI Refresh --- This will handle mutual exclusivity (grey-out) and contextual visibility
        self._refresh_toolbar_action_state()

    def _handle_toolbar_special_actions(self, action_label: str, checked: bool) -> bool:
        """Handle special actions like dropdowns or state sync that terminate early."""
        if action_label == "Comparator" and checked:
            self._show_comparator_dropdown()
            return True

        if action_label == "Export":
            self._show_export_dropdown()
            return True
        if action_label == "Add Raster Layer":
            self.controller.add_raster_layers()
            return True
        if action_label == "Add Vector":
            self.controller.add_vector_layers()
            return True

        return False

    def _handle_toolbar_exclusivity(self, action_label: str, action: QAction) -> None:
        """If an interaction tool was just ENABLED, uncheck all OTHER interaction tools."""
        interaction_toggles = {
            "Distance / Azimuth",
            "Elevation Profile",
            "Add Point",
            "Add Line",
            "Add Polygon",
            "Add Text Label",
        }
        if action_label in interaction_toggles and action.isChecked():
            for other_label in interaction_toggles:
                if other_label == action_label:
                    continue
                other_action = self.toolbar_actions.get(other_label)
                if other_action and other_action.isCheckable() and other_action.isChecked():
                    other_action.blockSignals(True)
                    other_action.setChecked(False)
                    other_action.blockSignals(False)
                    # Tell controller the other tool is now OFF
                    self.controller.handle_toolbar_action(other_label, False)



    def _create_menu_bar(self) -> None:
        menu_bar = self.menuBar()
        menu_bar.setNativeMenuBar(False)
        
        # Apply compact Windows/Native style to eliminate the massive blank height gap
        menu_bar.setStyleSheet(
            """
            QMenuBar {
                background-color: #f5f7f9;
                border-bottom: 1px solid #d1d9e6;
                padding: 2px 4px;
                margin: 0px;
            }
            QMenuBar::item {
                background: transparent;
                padding: 4px 8px;
                margin: 0px 2px;
                border-radius: 3px;
                font-size: 12px;
            }
            QMenuBar::item:selected {
                background: rgba(0, 120, 212, 0.1);
            }
            QMenuBar::item:pressed {
                background: rgba(0, 120, 212, 0.15);
            }
            """
        )

        file_menu = menu_bar.addMenu("&File")
        new_action = QAction(IconRegistry.get("new_project", size=16), "New Project", self)
        open_action = QAction(IconRegistry.get("open_project", size=16), "Open...", self)
        save_action = QAction(IconRegistry.get("save_project", size=16), "Save", self)
        save_as_action = QAction(IconRegistry.get("save_project_as", size=16), "Save As...", self)
        exit_action = QAction("Exit", self)

        new_action.triggered.connect(self.controller.new_project)
        open_action.triggered.connect(self.controller.open_project)
        save_action.triggered.connect(self.controller.save_project)
        save_as_action.triggered.connect(self.controller.save_project_as)
        exit_action.triggered.connect(self.close)

        file_menu.addAction(new_action)
        file_menu.addAction(open_action)
        file_menu.addSeparator()
        file_menu.addAction(save_action)
        file_menu.addAction(save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)

        settings_menu = menu_bar.addMenu("&Settings")
        quality_action = QAction("Rendering Quality...", self)
        quality_action.setStatusTip("Adjust map rendering quality for your machine")
        quality_action.triggered.connect(self._open_settings_dialog)
        settings_menu.addAction(quality_action)

        help_menu = menu_bar.addMenu("&Help")
        docs_action = QAction("Documentation", self)
        docs_action.triggered.connect(self._open_help_url)
        help_menu.addAction(docs_action)

    def _open_settings_dialog(self) -> None:
        """Open the Rendering Quality settings dialog."""
        from src_new.clients.desktop_search.ui.dialogs.settings_dialog import (
            SettingsDialog,
        )
        dlg = SettingsDialog(self, self.controller)
        dlg.exec()

    def _open_help_url(self) -> None:
        from src_new.shared.ui_components.help_dialog import HelpDialog
        dialog = HelpDialog(self)
        dialog.exec()

    def showEvent(self, event: object) -> None:
        """Handle window show event.

        Args:
            event: Show event object.
        """
        super().showEvent(event)
        if (
            hasattr(self, "map_overlay_controls")
            and self.map_overlay_controls.isVisible()
        ):
            self.map_overlay_controls.update_position()
        if (
            hasattr(self, "fly_through_timeline_bar")
            and self.fly_through_timeline_bar.isVisible()
        ):
            self.fly_through_timeline_bar.update_position()

    def set_busy_overlay(self, active: bool, message: str = "") -> None:
        """Toggle the modal busy overlay."""
        if active:
            self.busy_overlay.show_with_message(message)
            self.busy_overlay.resize(self.size())
        else:
            self.busy_overlay.hide()

    def set_fly_through_active(self, active: bool) -> None:
        """Show or hide the fly-through timeline bar and height slider."""
        if hasattr(self, "fly_through_timeline_bar"):
            self.fly_through_timeline_bar.set_fly_through_active(active)
            if active:
                self.fly_through_timeline_bar.update_position()
        if hasattr(self, "fly_through_height_slider"):
            self.fly_through_height_slider.set_fly_through_active(active)
            if active:
                self.fly_through_height_slider.update_position()
        if hasattr(self, "map_overlay_controls") and self.map_overlay_controls:
            if active:
                self.map_overlay_controls.scene_mode_combo.setCurrentText("3D Globe")
            self.map_overlay_controls.scene_mode_combo.setEnabled(not active)

    def moveEvent(self, event: object) -> None:
        """Handle window move event.

        Args:
            event: Move event object.
        """
        super().moveEvent(event)

        if hasattr(self, "map_overlay_controls") and self.map_overlay_controls.isVisible():
            self.map_overlay_controls.update_position()
        if (
            hasattr(self, "fly_through_timeline_bar")
            and self.fly_through_timeline_bar.isVisible()
        ):
            self.fly_through_timeline_bar.update_position()
        if (
            hasattr(self, "fly_through_height_slider")
            and self.fly_through_height_slider.isVisible()
        ):
            self.fly_through_height_slider.update_position()

    def resizeEvent(self, event: object) -> None:
        """Handle window resize event.

        Args:
            event: Resize event object.
        """
        super().resizeEvent(event)
        if hasattr(self, "busy_overlay"):
            self.busy_overlay.resize(self.size())

        if (
            hasattr(self, "map_overlay_controls")
            and self.map_overlay_controls.isVisible()
        ):
            self.map_overlay_controls.update_position()
        if (
            hasattr(self, "fly_through_timeline_bar")
            and self.fly_through_timeline_bar.isVisible()
        ):
            self.fly_through_timeline_bar.update_position()
        if (
            hasattr(self, "fly_through_height_slider")
            and self.fly_through_height_slider.isVisible()
        ):
            self.fly_through_height_slider.update_position()

    def _on_fly_through_playback_state_changed(self, state: str) -> None:
        if hasattr(self, "fly_through_timeline_bar"):
            self.fly_through_timeline_bar.set_playback_state(state)
        if str(state).lower() == "ended":
            if hasattr(self, "fly_through_timeline_bar"):
                self.fly_through_timeline_bar.set_fly_through_active(False)
            if hasattr(self, "fly_through_height_slider"):
                self.fly_through_height_slider.set_fly_through_active(False)
            if hasattr(self, "map_overlay_controls") and self.map_overlay_controls:
                self.map_overlay_controls.scene_mode_combo.setEnabled(True)
            self.controller._fly_through_mode_enabled = False
            action = self.toolbar_actions.get("Fly Through")
            if action is not None:
                previous = action.blockSignals(True)
                action.setChecked(False)
                action.blockSignals(previous)
            # Recompute toolbar enabled/disabled state now that fly-through is over. Without this refresh, annotation tools can remain greyed out until another toolbar action forces a state sync.
            self._refresh_toolbar_action_state()

    def _on_fly_through_playback_progress_changed(self, progress: float) -> None:
        if hasattr(self, "fly_through_timeline_bar"):
            self.fly_through_timeline_bar.set_progress(progress)
# TODO: Refactor for cognitive complexity

# TODO: Refactor for cognitive complexity


    def _show_comparator_dropdown(self) -> None:
        """Show the comparator layer selection dropdown dialog."""
        action = self.toolbar_actions.get("Comparator")
        if action is None:
            return

        if hasattr(self, "_comparator_popup") and self._comparator_popup and self._comparator_popup.isVisible():
            self._comparator_popup.close()
            action.setChecked(False)
            return

        layers = self.controller.available_comparator_layer_options()
        if len(layers) < 2:
            self.panel.log("Comparator needs at least two layers in current region.")
            action.setChecked(False)
            return

        anchor = self.main_toolbar.widgetForAction(action)
        if anchor is None:
            action.setChecked(False)
            return

        self._comparator_popup = QDialog(self, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self._comparator_popup.setObjectName("comparatorDropdown")
        self._comparator_popup.setStyleSheet(
            """
            QDialog#comparatorDropdown {
                background: #f8fafc;
                border: 1px solid #c9d3df;
                border-radius: 8px;
            }
            QLabel {
                color: #1a2a3a;
                font-size: 12px;
                font-weight: 600;
            }
            QListWidget {
                background: #ffffff;
                border: 1px solid #d7dfe9;
                border-radius: 6px;
            }
            QPushButton {
                background: #1f6fd2;
                color: white;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #185fb7;
            }
            """
        )

        layout = QVBoxLayout(self._comparator_popup)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Header with title and native close cross sign button
        header_layout = QHBoxLayout()
        title = QLabel("Comparator")
        close_btn = QPushButton("×")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #5a6a7e;
                font-size: 18px;
                font-weight: bold;
                border: none;
                padding: 0;
            }
            QPushButton:hover {
                color: #e44040;
            }
        """)
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(close_btn)
        layout.addLayout(header_layout)

        # Separator line
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        # Interactive Map Picker Section (on top)
        picker_section = QFrame()
        picker_section.setObjectName("pickerSection")
        picker_section.setStyleSheet("""
            QFrame#pickerSection {
                background: #f1f5f9;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                padding: 8px;
            }
        """)
        picker_layout = QVBoxLayout(picker_section)
        picker_layout.setContentsMargins(6, 6, 6, 6)
        picker_layout.setSpacing(6)

        pick_btn = QPushButton("Pick Assets from Map")
        pick_btn.setCheckable(True)
        pick_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                border: 1px solid #c9d3df;
                border-radius: 4px;
                padding: 6px;
                font-size: 11px;
                font-weight: bold;
                color: #1f6fd2;
            }
            QPushButton:hover {
                background-color: #f8fafc;
            }
            QPushButton:checked {
                background-color: #ffb300;
                color: #1a2a3a;
                border: 1px solid #ff9100;
            }
        """)
        picker_layout.addWidget(pick_btn)

        # Display picked asset names
        self._comparator_popup.label_asset1 = QLabel(ASSET1_PICK_LITERAL)
        self._comparator_popup.label_asset1.setStyleSheet(LABEL_SUBTEXT_STYLE)
        self._comparator_popup.label_asset2 = QLabel(ASSET2_PICK_LITERAL)
        self._comparator_popup.label_asset2.setStyleSheet(LABEL_SUBTEXT_STYLE)
        picker_layout.addWidget(self._comparator_popup.label_asset1)
        picker_layout.addWidget(self._comparator_popup.label_asset2)

        layout.addWidget(picker_section)

        # List Section Label
        list_label = QLabel("Or select manually from list:")
        list_label.setStyleSheet("color: #475569; font-size: 11px; font-weight: normal;")
        layout.addWidget(list_label)

        # List Widget
        layer_list = QListWidget(self._comparator_popup)
        layer_list.setMinimumHeight(150)
        checked_count = 0
        for layer in layers:
            item = QListWidgetItem(layer["label"], layer_list)
            item.setData(Qt.ItemDataRole.UserRole, layer["path"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            
            # Limit default checked items to at most 2.
            should_check = False
            if layer["visible"] and checked_count < 2:
                should_check = True
                checked_count += 1
            
            item.setCheckState(
                Qt.CheckState.Checked if should_check else Qt.CheckState.Unchecked
            )
        layout.addWidget(layer_list)

        info_label = QLabel("Select exactly 2 layers.")
        layout.addWidget(info_label)

        apply_button = QPushButton("Apply")
        layout.addWidget(apply_button)
        applied = {"done": False}

        # Store elements on the popup instance for map picking lookup
        self._comparator_popup.pick_btn = pick_btn
        self._comparator_popup.layer_list = layer_list
        self._comparator_popup.apply_button = apply_button
        self._comparator_popup.info_label = info_label
        
        # Initialize picked_assets list based on initial checks
        initial_checked = []
        for i in range(layer_list.count()):
            item = layer_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                initial_checked.append(str(item.data(Qt.ItemDataRole.UserRole) or ""))
        self._comparator_popup.picked_assets = initial_checked

        close_btn.clicked.connect(self._comparator_popup.close)

        pick_btn.toggled.connect(
            lambda checked: self._on_comparator_picker_toggled(checked, layer_list, info_label, apply_button)
        )

        layer_list.itemChanged.connect(
            lambda changed_item: self._enforce_comparator_max_selection(changed_item, layer_list, info_label, apply_button)
        )
        
        # Populate initial check names
        self._enforce_comparator_max_selection(None, layer_list, info_label, apply_button)
        self._sync_comparator_layout(info_label, apply_button)

        apply_button.clicked.connect(
            lambda: self._apply_comparator_selection(action, applied, anchor)
        )

        def on_finished(result: int) -> None:
            if not applied["done"]:
                action.setChecked(False)
            self.controller._comparator_picker_active = False
            self.controller._set_measurement_cursor_enabled(False)
            self._refresh_toolbar_action_state()

        self._comparator_popup.finished.connect(on_finished)

        self._comparator_popup.adjustSize()
        global_pos = anchor.mapToGlobal(anchor.rect().bottomLeft())
        self._comparator_popup.move(global_pos)
        self._comparator_popup.show()

    def _sync_comparator_layout(self, info_label: QLabel, apply_button: QPushButton) -> None:
        selected_count = len(self._comparator_popup.picked_assets)
        if selected_count == 2:
            info_label.setText("Exactly 2 layers selected.")
            apply_button.setEnabled(True)
        else:
            info_label.setText(f"Select exactly 2 layers (selected: {selected_count}).")
            apply_button.setEnabled(False)

    def _on_comparator_picker_toggled(self, checked: bool, layer_list: QListWidget, info_label: QLabel, apply_button: QPushButton) -> None:
        self.controller._comparator_picker_active = checked
        self.controller._set_measurement_cursor_enabled(checked)
        if checked:
            # Clear existing picks to start fresh on map pick action
            self._comparator_popup.picked_assets = []
            self._comparator_popup.label_asset1.setText(ASSET1_PICK_LITERAL)
            self._comparator_popup.label_asset1.setStyleSheet(LABEL_SUBTEXT_STYLE)
            self._comparator_popup.label_asset2.setText(ASSET2_PICK_LITERAL)
            self._comparator_popup.label_asset2.setStyleSheet(LABEL_SUBTEXT_STYLE)
            
            # Uncheck all items in the list widget as we're starting a new map pick sequence
            layer_list.blockSignals(True)
            for i in range(layer_list.count()):
                layer_list.item(i).setCheckState(Qt.CheckState.Unchecked)
            layer_list.blockSignals(False)
            
            self._sync_comparator_layout(info_label, apply_button)
            self.panel.log("Comparator Picker: Click on any 2 assets on the map.")

    def _enforce_comparator_max_selection(self, changed_item: QListWidgetItem | None, layer_list: QListWidget, info_label: QLabel, apply_button: QPushButton) -> None:
        checked_items = []
        for i in range(layer_list.count()):
            item = layer_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                checked_items.append(str(item.data(Qt.ItemDataRole.UserRole) or ""))
        
        if len(checked_items) > 2 and changed_item is not None:
            layer_list.blockSignals(True)
            changed_item.setCheckState(Qt.CheckState.Unchecked)
            layer_list.blockSignals(False)
            info_label.setText("Maximum 2 layers are allowed.")
            return

        self._comparator_popup.picked_assets = checked_items
        
        # Real-time populate the names in the section below the pick button
        names = []
        for path in checked_items:
            asset = self.controller._search_result_assets_by_path.get(path)
            name = str(asset.get("file_name") or Path(path).name if asset else Path(path).name)
            names.append(name)
            
        if len(names) >= 1:
            self._comparator_popup.label_asset1.setText(f"Asset 1: {names[0]}")
            self._comparator_popup.label_asset1.setStyleSheet("color: #1f6fd2; font-size: 11px; font-weight: bold;")
        else:
            self._comparator_popup.label_asset1.setText(ASSET1_PICK_LITERAL)
            self._comparator_popup.label_asset1.setStyleSheet(LABEL_SUBTEXT_STYLE)
            
        if len(names) >= 2:
            self._comparator_popup.label_asset2.setText(f"Asset 2: {names[1]}")
            self._comparator_popup.label_asset2.setStyleSheet("color: #1f6fd2; font-size: 11px; font-weight: bold;")
        else:
            self._comparator_popup.label_asset2.setText(ASSET2_PICK_LITERAL)
            self._comparator_popup.label_asset2.setStyleSheet(LABEL_SUBTEXT_STYLE)
            
        self._sync_comparator_layout(info_label, apply_button)

    def _apply_comparator_selection(self, action: QAction, applied: dict, anchor) -> None:
        selected_paths = list(self._comparator_popup.picked_assets)
        if len(selected_paths) != 2:
            self.panel.log("Select exactly 2 layers for comparator.")
            action.setChecked(False)
            self._comparator_popup.close()
            return

        success = self.controller.apply_comparator_selection(selected_paths)
        if success:
            action.setChecked(True)
            applied["done"] = True
        else:
            action.setChecked(False)
        self._refresh_toolbar_action_state()
        self._comparator_popup.close()

        def on_finished(result: int) -> None:
            if not applied["done"]:
                action.setChecked(False)
            self.controller._comparator_picker_active = False
            self.controller._set_measurement_cursor_enabled(False)
            self._refresh_toolbar_action_state()

        self._comparator_popup.finished.connect(on_finished)

        self._comparator_popup.adjustSize()
        global_pos = anchor.mapToGlobal(anchor.rect().bottomLeft())
        self._comparator_popup.move(global_pos)
        self._comparator_popup.show()

    def _show_export_dropdown(self) -> None:
        """Show export options dropdown under the Export toolbar button."""

        action = self.toolbar_actions.get("Export")
        anchor = self.main_toolbar.widgetForAction(action) if action else None

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #ffffff;
                border: 1px solid #999999;
                padding: 2px;
            }
            QMenu::item {
                padding: 4px 16px;
                font-size: 12px;
                font-weight: normal;
                color: #000000;
            }
            QMenu::item:selected {
                background: #3399ff;
                color: #ffffff;
            }
        """)
        geotiff_act = menu.addAction("Export Asset")
        pdf_act = menu.addAction("Export PDF")

        pos = (
            anchor.mapToGlobal(anchor.rect().bottomLeft())
            if anchor
            else self.cursor().pos()
        )
        chosen = menu.exec(pos)

        if chosen == geotiff_act:
            self.controller.handle_toolbar_action("Export Asset")
        elif chosen == pdf_act:
            self.controller.handle_toolbar_action("Export PDF")

    def set_toolbar_layer_context(self, context: str) -> None:
        """Set the current layer context for toolbar action filtering.

        Args:
            context: Layer context ("none", "imagery", "dem", or "mixed").
        """
        normalized = str(context or "none").lower()
        if normalized not in {"none", "imagery", "dem", "mixed"}:
            normalized = "none"
        self._toolbar_layer_context = normalized
        self._refresh_toolbar_action_state()

    def _refresh_toolbar_action_state(self) -> None:
        """Refresh toolbar action visibility and enabled state based on current context."""
        for label, action in self.toolbar_actions.items():
            group = self.action_group_by_label.get(label, "")
            if group == "visualization" and not self._visualization_tools_enabled:
                action.setVisible(False)
                if action.isCheckable():
                    action.setChecked(False)
                continue
            if group == "measurement" and not self._measurement_tools_enabled:
                action.setVisible(False)
                if action.isCheckable():
                    action.setChecked(False)
                continue

            # Contextual filtering only applies to visualization and measurement actions.
            if group in {"visualization", "measurement"}:
                if (
                    self._toolbar_layer_context == "imagery"
                    and label in self.DEM_ONLY_ACTIONS
                ):
                    action.setVisible(False)
                    if action.isCheckable():
                        action.setChecked(False)
                    continue
                if (
                    self._toolbar_layer_context == "dem"
                    and label in self.IMAGERY_ONLY_ACTIONS
                ):
                    action.setVisible(False)
                    if action.isCheckable():
                        action.setChecked(False)
                    continue

            action.setVisible(True)

            # --- Enablement Logic ---
            is_enabled = True

            # 1. Measurement tools need at least one layer
            if group == "measurement" and self._toolbar_layer_context == "none":
                is_enabled = False

            # 2. Visualization exclusivity (Comparator, Layer Compositor, Fly Through)
            viz_exclusives = {"Comparator", "Fly Through"}
            active_viz_tool = None
            for viz_tool in viz_exclusives:
                other_action = self.toolbar_actions.get(viz_tool)
                if other_action and other_action.isChecked():
                    active_viz_tool = viz_tool
                    break

            if label in viz_exclusives:
                if active_viz_tool and active_viz_tool != label:
                    is_enabled = False

            normal_view_blockers = {
                "Distance / Azimuth",
                "Elevation Profile",
                "Add Point",
                "Add Line",
                "Add Polygon",
                "Add Text Label",
            }
            normal_view_blocked = any(
                self.toolbar_actions.get(blocker).isChecked()
                for blocker in normal_view_blockers
                if self.toolbar_actions.get(blocker)
            )
            if label in {"Comparator", "Fly Through"} and normal_view_blocked:
                is_enabled = False

            # 5. Annotation tool exclusivity (Add Point, Add Line, Add Polygon, Add Text Label) Disable during Comparator and Fly Through modes.
            annotation_tools = {
                "Add Point",
                "Add Line",
                "Add Polygon",
                "Add Text Label",
            }
            if label in annotation_tools:
                if active_viz_tool in {"Comparator", "Fly Through"}:
                    is_enabled = False

            # 6. Global group disable
            if group == "visualization" and not self._visualization_tools_enabled:
                is_enabled = False
            if group == "measurement" and not self._measurement_tools_enabled:
                is_enabled = False

            # 3. Comparator specific check
            if label == "Comparator" and is_enabled and hasattr(self, "controller"):
                if not self.controller.can_attempt_enable_comparator():
                    is_enabled = False

            action.setEnabled(is_enabled)
            
            # Auto-uncheck if disabled
            if not is_enabled and action.isCheckable() and action.isChecked():
                action.blockSignals(True)
                action.setChecked(False)
                action.blockSignals(False)
                if hasattr(self, "controller"):
                    self.controller.handle_toolbar_action(label, False)

    def _on_elevation_profile_close(self) -> None:
        """Hide the profile panel, clear globe markers, uncheck toolbar button."""
        self.elevation_profile_panel.hide()
        # Restore splitter to full map view
        total = self._map_v_splitter.height()
        self._map_v_splitter.setSizes([total, 0])
        # Clear all profile markers from the globe
        self.controller._run_js_call("clearProfileLine")
        action = self.toolbar_actions.get("Elevation Profile")
        if action is not None:
            action.setChecked(False)
        # Also cancel active mode if still running
        if self.controller._elevation_profile.active:
            self.controller._elevation_profile.deactivate()

    def _on_elevation_profile_complete(self) -> None:
        """Uncheck the Elevation Profile toolbar button when profile finishes."""
        action = self.toolbar_actions.get("Elevation Profile")
        if action is not None:
            action.setChecked(False)

    def _on_profile_cursor_moved(self, frac: float) -> None:
        """Forward cursor fraction to the profile panel for live crosshair update."""
        if self.elevation_profile_panel.isVisible():
            self.elevation_profile_panel.set_cursor_fraction(frac)

    def _build_crosshair_cursor(self) -> QCursor:
        """Return the standard Windows system crosshair cursor for maximum precision."""
        from qtpy.QtCore import Qt
        return QCursor(Qt.CursorShape.CrossCursor)

    def _on_measure_cursor_changed(self, enabled: bool) -> None:
        """Set or restore the crosshair cursor on the map web view only."""
        import logging
        import sys

        from qtpy.QtWidgets import QApplication
        logger = logging.getLogger("desktop.main_window")

        enabled = bool(enabled)
        if self._measure_cursor_active == enabled:
            return

        logger.debug("_on_measure_cursor_changed called: enabled=%s", enabled)
        self._measure_cursor_active = enabled
        # Always clear any application-level override so toolbar/panel stay normal
        while QApplication.overrideCursor():
            QApplication.restoreOverrideCursor()
            
        if self._measure_cursor_active:
            logger.info("Applying crosshair cursor to web view")
            self._apply_crosshair_to_webview()
            if sys.platform == "darwin":
                QApplication.setOverrideCursor(self._measure_crosshair_cursor)
        else:
            logger.info("Removing crosshair cursor from web view")
            self.web_view.unsetCursor()
            vp = self.web_view.focusProxy() or self.web_view.childAt(1, 1)
            if vp:
                vp.unsetCursor()

    def _apply_crosshair_to_webview(self) -> None:
        """Set crosshair cursor on the web view widget and its viewport child."""
        import logging
        logger = logging.getLogger("desktop.main_window")
        
        if getattr(self, "_applying_cursor", False):
            logger.debug("Already applying cursor, skipping")
            return
        self._applying_cursor = True
        try:
            logger.debug("Setting crosshair cursor on web_view")
            self.web_view.setCursor(self._measure_crosshair_cursor)
            vp = self.web_view.focusProxy() or self.web_view.childAt(1, 1)
            if vp:
                logger.debug("Setting crosshair cursor on viewport: %s", vp)
                vp.setCursor(self._measure_crosshair_cursor)
            else:
                logger.warning("No viewport found for cursor setting")
        finally:
            self._applying_cursor = False

    def eventFilter(self, obj: object, event: object) -> bool:
        """Re-apply crosshair when mouse enters or moves over the web view."""
        from qtpy.QtCore import QEvent

        if self._measure_cursor_active and not getattr(self, "_applying_cursor", False):
            if hasattr(event, "type"):
                et = event.type()
                if et in (QEvent.Type.MouseMove, QEvent.Type.Enter):
                    # Only re-apply if the event is from the web view or its viewport
                    if obj is self.web_view or obj is self.web_view.focusProxy():
                        self._apply_crosshair_to_webview()
        return super().eventFilter(obj, event)

    def _cancel_active_draw(self) -> None:
        if hasattr(self, "controller") and self.controller:
            cancelled = self.controller.cancel_active_draw()
            if cancelled:
                logging.getLogger("desktop").info("Escape cancelled active draw")

    def _toolbar_icon(self, tool_name: str, fallback: QStyle.StandardPixmap) -> QIcon:
        """Get icon for toolbar action.

        Args:
            tool_name: Name of the tool.
            fallback: Fallback standard pixmap if custom icon not found.

        Returns:
            QIcon for the toolbar action.
        """
        icon = IconRegistry.get(tool_name, size=24)
        if icon.isNull():
            return self.style().standardIcon(fallback)
        return icon

    def _create_main_toolbar(
        self,
    ) -> tuple[
        QToolBar,
        dict[str, QAction],
        list[QAction],
        list[QAction],
        dict[str, str],
    ]:
        """Create and configure the main toolbar.

        Returns:
            Tuple containing:
                - QToolBar: The main toolbar widget
                - dict[str, QAction]: Mapping of action labels to QAction objects
                - list[QAction]: List of visualization actions
                - list[QAction]: List of measurement actions
                - dict[str, str]: Mapping of action labels to group names
        """
        toolbar = QToolBar("Main")
        toolbar.setObjectName("desktopMainToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(QSize(18, 18))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        toolbar.setStyleSheet(
            """
            QToolBar#desktopMainToolbar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #f5f7f9);
                border: none;
                border-bottom: 1px solid #d1d9e6;
                spacing: 4px;
                padding: 4px 8px;
            }
            QToolBar#desktopMainToolbar QToolButton {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 3px;
                margin: 0px 1px;
                min-width: 26px;
                min-height: 26px;
            }
            QToolBar#desktopMainToolbar QToolButton:hover {
                background: rgba(0, 120, 212, 0.1);
                border: 1px solid rgba(0, 120, 212, 0.2);
            }
            QToolBar#desktopMainToolbar QToolButton:pressed {
                background: rgba(0, 120, 212, 0.2);
            }
            QToolBar#desktopMainToolbar QToolButton:checked {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #fff3d6, stop:1 #ffe4a3);
                border: 1px solid #ffb300;
            }
            QToolBar#desktopMainToolbar QToolButton:checked:hover {
                background: #ffebbc;
                border: 1px solid #ffa000;
            }
            QToolBar#desktopMainToolbar QToolButton:disabled {
                opacity: 0.5;
                background: transparent;
                border: none;
            }
            """
        )

        fallback_map = {
            "visualization": QStyle.StandardPixmap.SP_FileDialogDetailedView,
            "measurement": QStyle.StandardPixmap.SP_DesktopIcon,
            "annotation": QStyle.StandardPixmap.SP_DialogApplyButton,
            "navigation": QStyle.StandardPixmap.SP_ArrowRight,
            "file": QStyle.StandardPixmap.SP_DriveHDIcon,
        }

        actions: dict[str, QAction] = {}
        visualization_actions: list[QAction] = []
        measurement_actions: list[QAction] = []
        action_group_by_label: dict[str, str] = {}

        for group_index, (group_name, entries) in enumerate(self.TOOLBAR_GROUPS):
            for label, tool_name in entries:
                icon = self._toolbar_icon(
                    tool_name,
                    fallback_map.get(group_name, QStyle.StandardPixmap.SP_FileIcon),
                )
                action = QAction(icon, label, self)
                action.setToolTip(label)
                action.setCheckable(label in self.TOGGLE_ACTIONS)
                toolbar.addAction(action)
                actions[label] = action
                action_group_by_label[label] = group_name
                if group_name == "visualization":
                    visualization_actions.append(action)
                if group_name == "measurement":
                    measurement_actions.append(action)
            if group_index < len(self.TOOLBAR_GROUPS) - 1:
                toolbar.addSeparator()

        # ── Right-aligned resGIS logo ─────────────────────────────────────────
        # Push everything that follows to the far right using an expanding spacer.
        import pathlib as _pathlib

        from qtpy.QtWidgets import QSizePolicy
        from qtpy.QtWidgets import QWidget as _QWidget
        _spacer = _QWidget()
        _spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(_spacer)

        # Light blue shaded box (goto container)
        _goto_container = QFrame()
        _goto_container.setObjectName("gotoContainer")
        _goto_container.setStyleSheet("""
            #gotoContainer {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #eef6ff, stop:1 #d9eaff);
                border: 1px solid #b3d1ff;
                border-radius: 6px;
                padding: 0px 2px;
            }
            QLineEdit {
                background-color: #ffffff;
                border: 1px solid #b3d1ff;
                border-radius: 4px;
                padding: 0px 2px;
                color: #2b2b2b;
                font-size: 11px;
                font-weight: 500;
            }
            QLineEdit:focus {
                border: 1px solid #3399ff;
            }
            QPushButton {
                background-color: #3399ff;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 10px;
                font-weight: bold;
                min-width: 20px;
                max-width: 20px;
                min-height: 20px;
                max-height: 20px;
            }
            QPushButton:hover {
                background-color: #1a8cff;
            }
            QPushButton:pressed {
                background-color: #0073e6;
            }
        """)

        _goto_layout = QHBoxLayout(_goto_container)
        _goto_layout.setContentsMargins(1, 0, 1, 0)
        _goto_layout.setSpacing(2)

        self.goto_lat_input = QLineEdit()
        self.goto_lat_input.setPlaceholderText("Lat")
        self.goto_lat_input.setFixedWidth(65)
        self.goto_lat_input.setToolTip("Latitude (e.g. 28.6139)")

        self.goto_lon_input = QLineEdit()
        self.goto_lon_input.setPlaceholderText("Long")
        self.goto_lon_input.setFixedWidth(65)
        self.goto_lon_input.setToolTip("Longitude (e.g. 77.2090)")

        _goto_btn = QPushButton("Go")
        _goto_btn.setToolTip("Go to Coordinates")
        _goto_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _goto_btn.clicked.connect(self._on_goto_coordinates_clicked)

        _goto_layout.addWidget(self.goto_lon_input)
        _goto_layout.addWidget(self.goto_lat_input)
        _goto_layout.addWidget(_goto_btn)

        toolbar.addWidget(_goto_container)

        _logo_path = _pathlib.Path(__file__).resolve().parent.parent.parent / "assets" / "resGIS_logo.png"
        if _logo_path.exists():
            from qtpy.QtGui import QPixmap
            _logo_label = QLabel()
            _pix = QPixmap(str(_logo_path))
            
            # Tight zoom crop of the active logo area, giving extra breathing room on the right to prevent clipping the 'S'
            from qtpy.QtCore import QRect
            _pix = _pix.copy(QRect(128, 349, 800, 287))
            
            # Scale to a slightly taller height (34 px) for prominent zoom display
            _pix = _pix.scaledToHeight(34, Qt.TransformationMode.SmoothTransformation)
            _logo_label.setPixmap(_pix)
            _logo_label.setFixedSize(_pix.size())
            _logo_label.setToolTip("resGIS \u2014 developed by NTRO, Gov. of India")
            _logo_label.setStyleSheet("margin-left: 4px;")
            toolbar.addWidget(_logo_label)
            
            # Robust native spacer to shift the logo leftwards without triggering Qt's stylesheet margin layout bugs
            _right_margin_spacer = _QWidget()
            _right_margin_spacer.setFixedWidth(50)
            toolbar.addWidget(_right_margin_spacer)

        return (
            toolbar,
            actions,
            visualization_actions,
            measurement_actions,
            action_group_by_label,
        )

    def _on_goto_coordinates_clicked(self) -> None:
        """Handle the go-to coordinates navigation."""
        lat_text = self.goto_lat_input.text().strip()
        lon_text = self.goto_lon_input.text().strip()

        if not lat_text or not lon_text:
            QMessageBox.warning(
                self,
                "Invalid Coordinates",
                "Please enter both Latitude and Longitude values."
            )
            return

        try:
            lat = float(lat_text)
            lon = float(lon_text)
        except ValueError:
            QMessageBox.warning(
                self,
                "Invalid Coordinates",
                "Latitude and Longitude must be valid numerical values."
            )
            return

        if not (-90.0 <= lat <= 90.0):
            QMessageBox.warning(
                self,
                "Invalid Coordinates",
                "Latitude must be between -90.0 and 90.0 degrees."
            )
            return

        if not (-180.0 <= lon <= 180.0):
            QMessageBox.warning(
                self,
                "Invalid Coordinates",
                "Longitude must be between -180.0 and 180.0 degrees."
            )
            return

        # Trigger the smooth flight and animated drop marker in JS
        self.controller._run_js_call("dropGoToMarker", lon, lat)

    @staticmethod
    def _window_title_for_mode(app_mode: DesktopAppMode) -> str:
        """Get window title based on application mode.

        Args:
            app_mode: Application mode.

        Returns:
            Window title string.
        """
        if app_mode == DesktopAppMode.SERVER:
            return "Offline GIS Server Desktop"
        if app_mode == DesktopAppMode.CLIENT:
            return "Offline GIS Client Desktop"
        return "Offline 3D GIS Desktop"

    def set_project_info(self, name: str | None = None, modified: bool | None = None) -> None:
        """Update the project name and modification status."""
        if name is not None:
            self._project_name = name
        if modified is not None:
            self._is_modified = modified
        self._update_window_title()

    def _update_window_title(self) -> None:
        """Refresh the window title based on current project state."""
        suffix = "*" if self._is_modified else ""
        project_display = f"{self._project_name}{suffix}"
        self.setWindowTitle(f"{project_display} - resGIS (developed by NTRO, Gov. of India)")

    def run_js_sync(self, script: str):
        """Execute JavaScript synchronously using a nested event loop."""
        loop = QEventLoop()
        result = None
        
        def callback(val):
            nonlocal result
            result = val
            loop.quit()
            
        self.web_view.page().runJavaScript(script, callback)
        loop.exec()
        return result

    def export_fly_through_video(self) -> None:
        """Export the fly-through animation as an MP4 video with customizable parameters."""
        # Halts current playback
        self.controller._run_js_call("pauseFlyThroughPlaybackOnly")
        if hasattr(self, "fly_through_timeline_bar"):
            self.fly_through_timeline_bar.set_playback_state("idle")

        # Get total duration in MS
        duration_ms = self.run_js_sync("window.offlineGIS && window.offlineGIS.getFlyThroughDuration ? window.offlineGIS.getFlyThroughDuration() : 0")
        if not duration_ms or duration_ms <= 0:
            QMessageBox.warning(
                self,
                "Export Error",
                "No valid fly-through path available. Please draw at least 2 points first.",
            )
            return

        # Show Settings Selection Dialog
        dialog = VideoExportSettingsDialog(self, duration_ms)
        if not dialog.exec():
            # Cancel clicked on settings dialog
            self.controller._run_js_call("setFlyThroughPlaybackProgress", 0.0)
            return

        scale_factor, fps = dialog.get_selected_settings()

        # Prompt for output file
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Fly-Through Video",
            "flythrough.mp4",
            "MP4 Video (*.mp4)",
        )
        if not file_path:
            self.controller._run_js_call("setFlyThroughPlaybackProgress", 0.0)
            return

        duration_sec = float(duration_ms) / 1000.0
        total_frames = round(duration_sec * fps)
        if total_frames <= 0:
            total_frames = 1

        # Show progress dialog
        progress = QProgressDialog("Exporting fly-through video...", "Cancel", 0, total_frames, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumWidth(300)
        progress.setValue(0)
        progress.show()

        # Load resGIS logo if exists
        logo_path = Path(__file__).resolve().parent.parent.parent / "assets" / "resGIS_logo.png"
        logo_image = None
        if logo_path.exists():
            logo_image = QImage(str(logo_path))
            if not logo_image.isNull():
                # Zoom crop of the active logo area, giving extra breathing room on the right
                logo_image = logo_image.copy(QRect(128, 349, 800, 287))
                logo_image = logo_image.scaledToHeight(28, Qt.TransformationMode.SmoothTransformation)

        writer = None
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        
        loop = QEventLoop()
        
        # Hide overlay panels temporarily during frame grabbing
        if hasattr(self, "fly_through_timeline_bar"):
            self.fly_through_timeline_bar.hide()
        if hasattr(self, "fly_through_height_slider"):
            self.fly_through_height_slider.hide()
        if hasattr(self, "map_overlay_controls"):
            self.map_overlay_controls.hide()

        try:
            for i in range(total_frames):
                if progress.wasCanceled():
                    break

                progress_ratio = float(i) / float(max(1, total_frames - 1))

                # Update camera position and return coords in one run
                script = f"""
                (function() {{
                    window.offlineGIS.setFlyThroughPlaybackProgress({progress_ratio});
                    return window.offlineGIS.getFlyThroughCoordsAtProgress({progress_ratio});
                }})()
                """
                coords = self.run_js_sync(script)

                # Wait for render (60ms) to ensure WebGL canvas is updated
                QTimer.singleShot(60, loop.quit)
                loop.exec()

                # Grab the frame from web view
                pixmap = self.web_view.grab()
                image = pixmap.toImage()

                # Draw overlays on the full-resolution grab first
                painter = QPainter(image)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

                # 1. Draw logo in top-right corner
                if logo_image and not logo_image.isNull():
                    painter.save()
                    painter.setOpacity(0.65)
                    logo_x = image.width() - logo_image.width() - 20
                    logo_y = 20
                    painter.drawImage(logo_x, logo_y, logo_image)
                    painter.restore()
                else:
                    painter.save()
                    font = QFont("Helvetica Neue", 12, QFont.Weight.Bold)
                    painter.setFont(font)
                    painter.setBrush(QColor(0, 229, 255, 180))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(image.width() - 85, 24, 6, 6)
                    painter.setPen(QColor(255, 255, 255, 160))
                    painter.drawText(image.width() - 75, 30, "RSGIS")
                    painter.restore()

                # 2. Draw coordinates legend box at the bottom-center
                if coords:
                    lat = coords.get("lat", 0.0)
                    lon = coords.get("lon", 0.0)
                    height = coords.get("height", 0.0)

                    box_width = 360
                    box_height = 32
                    box_x = (image.width() - box_width) // 2
                    box_y = image.height() - box_height - 20

                    painter.save()
                    painter.setBrush(QColor(14, 22, 38, 195))
                    painter.setPen(QPen(QColor(255, 255, 255, 60), 1))
                    painter.drawRoundedRect(box_x, box_y, box_width, box_height, 6, 6)

                    font = QFont("Consolas", 10, QFont.Weight.Bold)
                    font.setStyleHint(QFont.StyleHint.Monospace)
                    painter.setFont(font)
                    painter.setPen(QColor(230, 240, 255, 230))

                    info_text = f"LAT: {lat:10.6f}\u00b0  LON: {lon:10.6f}\u00b0  ALT: {height:4.0f}m"
                    painter.drawText(QRect(box_x, box_y, box_width, box_height), Qt.AlignmentFlag.AlignCenter | Qt.TextSingleLine, info_text)
                    painter.restore()

                painter.end()

                # Scale the complete image (including overlays) according to settings
                if scale_factor < 1.0:
                    new_w = int(image.width() * scale_factor)
                    new_h = int(image.height() * scale_factor)
                    image = image.scaled(new_w, new_h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)

                # Convert to RGBA8888 (no row/scanline padding issues) and map to BGR for OpenCV
                image = image.convertToFormat(QImage.Format.Format_RGBA8888)
                width = image.width()
                height = image.height()

                ptr = image.bits()
                ptr.setsize(height * width * 4)
                arr = np.frombuffer(ptr, np.uint8).reshape((height, width, 4))

                bgr_arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)

                if writer is None:
                    writer = cv2.VideoWriter(file_path, fourcc, fps, (width, height))

                writer.write(bgr_arr)

                progress.setValue(i + 1)
                QApplication.processEvents()

        except Exception as ex:
            QMessageBox.critical(
                self,
                "Export Error",
                f"An error occurred during video export: {ex!s}",
            )
        finally:
            if writer is not None:
                writer.release()
            progress.close()

            # Restore overlays
            if hasattr(self, "fly_through_timeline_bar"):
                self.fly_through_timeline_bar.show()
                self.fly_through_timeline_bar.update_position()
            if hasattr(self, "fly_through_height_slider"):
                self.fly_through_height_slider.show()
                self.fly_through_height_slider.update_position()
            if hasattr(self, "map_overlay_controls"):
                self.map_overlay_controls.show()
                self.map_overlay_controls.update_position()

            self.controller._run_js_call("setFlyThroughPlaybackProgress", 0.0)
