"""Main window module for the Offline GIS Desktop application.

This module provides the main window UI components including:
- LayerCompositorOverlay: Overlay for adjusting layer opacities
- MapOverlayControls: Controls for scene mode and polygon visibility
- MainWindow: Primary application window with toolbar and web view
"""

from __future__ import annotations

import logging
from pathlib import Path
import time

from qtpy.QtCore import QSize, Qt, QUrl
from qtpy.QtGui import (
    QAction,
    QColor,
    QCursor,
    QGuiApplication,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
)
from qtpy.QtGui import QDesktopServices
from qtpy.QtWebChannel import QWebChannel
from qtpy.QtWebEngineWidgets import QWebEngineSettings, QWebEngineView
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStyle,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from client_desktop.backend.app_mode import DesktopAppMode
from client_desktop.backend.bridge import WebBridge
from client_desktop.backend.control_panel import ControlPanel
from client_desktop.backend.controller import DesktopController
from client_desktop.backend.icon_registry import IconRegistry
from client_desktop.backend.status_bar import GISStatusBar
from client_desktop.backend.titiler_manager import TiTilerManager
from client_desktop.backend.web_page import LoggingWebEnginePage


class LayerCompositorOverlay(QWidget):
    """Overlay widget for adjusting layer opacities in the compositor mode.

    This widget displays sliders for each active layer, allowing users to
    adjust the opacity of individual layers in real-time.
    """

    def __init__(self, parent: QWidget, controller: DesktopController):
        """Initialize the layer compositor overlay.

        Args:
            parent: Parent widget (typically the web view).
            controller: Desktop controller instance for layer management.
        """
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.controller = controller
        self.setObjectName("compositorOverlay")
        self.setStyleSheet(
            """
            QWidget#compositorOverlay {
                background: rgba(248, 250, 252, 0.9);
                border: 1px solid #c9d3df;
                border-radius: 8px;
            }
            QLabel {
                color: #1a2a3a;
                font-size: 12px;
                font-weight: 600;
            }
            """
        )
        self.layout_main = QVBoxLayout(self)
        self.layout_main.setContentsMargins(10, 10, 10, 10)
        self.layout_main.setSpacing(8)

        title = QLabel("Layer Opacities")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout_main.addWidget(title)

        self.sliders_layout = QVBoxLayout()
        self.layout_main.addLayout(self.sliders_layout)

        self.sliders: dict[str, QSlider] = {}
        self.hide()

    def update_layers(self) -> None:
        """Update the overlay with current active layers and their sliders.

        Clears existing sliders and creates new ones for all searched layers.
        Each slider controls the opacity of its corresponding layer.
        """
        layers = self.controller.available_swipe_layer_options()

        # Clear old sliders
        while self.sliders_layout.count():
            item = self.sliders_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
                item.layout().deleteLater()

        self.sliders.clear()

        if not layers:
            no_layers_label = QLabel("No layers found.")
            self.sliders_layout.addWidget(no_layers_label)
            return

        for layer in layers:
            row = QHBoxLayout()
            base_label = str(layer.get("label") or "Layer")
            if not layer.get("visible"):
                base_label += " (hidden)"
            label = QLabel(base_label)
            label.setFixedWidth(120)
            row.addWidget(label)

            slider = QSlider(Qt.Orientation.Horizontal, self)
            slider.setRange(0, 100)
            slider.setValue(100)
            row.addWidget(slider)

            val_label = QLabel("100%")
            val_label.setFixedWidth(40)
            row.addWidget(val_label)

            slider.valueChanged.connect(
                lambda value, value_label=val_label, layer_path=layer["path"]: (
                    self._on_slider_changed(
                        value,
                        value_label,
                        layer_path,
                    )
                )
            )

            self.sliders[layer["path"]] = slider
            self.sliders_layout.addLayout(row)

    def _on_slider_changed(self, value: int, label: QLabel, path: str) -> None:
        """Handle slider value changes.

        Args:
            value: New slider value (0-100).
            label: Label widget to update with percentage.
            path: File path of the layer being adjusted.
        """
        label.setText(f"{value}%")
        self._apply_settings()

    def _apply_settings(self, *args: object) -> None:
        """Apply current slider values to the layer compositor.

        Args:
            *args: Unused arguments from signal connections.
        """
        if not self.isVisible():
            return
        layer_alphas = {
            path: slider.value() / 100.0 for path, slider in self.sliders.items()
        }
        # Only set opacity. Pass enable_swipe=False and empty swipe_paths.
        self.controller.apply_layer_compositor_settings(False, [], layer_alphas)

    def apply_state(self, state_dict: dict) -> None:
        """Apply saved state to the layer compositor overlay.

        Args:
            state_dict: Dictionary containing saved state (currently unused).
        """
        pass


class MapOverlayControls(QWidget):
    """Overlay widget for map display controls.

    Provides controls for:
    - Scene mode (3D Globe vs 2D Map)
    - Search polygon visibility
    - Area of Interest (AOI) statistics display
    """

    def __init__(self, parent: QWidget, controller: DesktopController):
        """Initialize the map overlay controls."""
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.controller = controller
        self._special_mode_active = (
            False  # True when comparator or compositor is active
        )
        self.setObjectName("mapOverlayControls")
        self.setStyleSheet(
            """
            QWidget#mapOverlayControls {
                background: rgba(18, 24, 38, 0.85);
                border: 1px solid rgba(120, 160, 220, 0.28);
                border-radius: 8px;
            }
            QLabel {
                color: #e0e8f4;
                font-size: 11px;
                font-weight: 600;
            }
            QCheckBox {
                color: #e0e8f4;
                font-size: 10px;
            }
            """
        )
        self.layout_main = QVBoxLayout(self)
        self.layout_main.setContentsMargins(10, 10, 10, 10)
        self.layout_main.setSpacing(8)

        # Scene Mode
        self.scene_mode_combo = QComboBox()
        self.scene_mode_combo.addItems(["3D Globe", "2D Map"])
        self.scene_mode_combo.currentTextChanged.connect(self._on_scene_mode_changed)
        self.layout_main.addWidget(self.scene_mode_combo)

        # Basemap Visibility Toggle
        self.basemap_visibility_combo = QComboBox()
        self.basemap_visibility_combo.addItems(
            ["Hide Map", "Show Map"]
        )  # Default to "Hide Map" for faster startup
        self.basemap_visibility_combo.currentTextChanged.connect(
            self._on_basemap_visibility_changed
        )
        self.layout_main.addWidget(self.basemap_visibility_combo)

        # Polygon Visibility (always visible; enabled when polygon exists)
        self.polygon_visibility_checkbox = QCheckBox("Show Search AOI Polygon")
        self.polygon_visibility_checkbox.setChecked(True)
        self.polygon_visibility_checkbox.setEnabled(False)
        self.polygon_visibility_checkbox.toggled.connect(
            self._on_polygon_visibility_toggled
        )
        self.layout_main.addWidget(self.polygon_visibility_checkbox)

        # Hide AOI checkbox in server mode as searching is client-only
        if self.controller.app_mode == DesktopAppMode.SERVER:
            self.polygon_visibility_checkbox.setVisible(False)
        else:
            self.polygon_visibility_checkbox.setVisible(True)

        # AOI Stats
        self.aoi_stats_label = QLabel("Area: 0 m\u00b2 | Vertices: 0")
        self.aoi_stats_label.setWordWrap(True)
        self.aoi_stats_label.setVisible(False)
        self.layout_main.addWidget(self.aoi_stats_label)

        self._last_aoi_vertices = 0
        self._last_aoi_area_text = "0 m\u00b2"

        self.setFixedWidth(200)

        # Connect bridge signals
        self.controller.bridge.aoiStatsUpdated.connect(self.update_aoi_stats)

        self.hide()

    def set_special_mode(self, active: bool) -> None:
        """Call when comparator or compositor mode is activated/deactivated.

        Keeps the AOI checkbox visible and hides stats when needed.
        """
        self._special_mode_active = bool(active)
        self._apply_aoi_visibility()

    def update_position(self) -> None:
        """Update the overlay position to top-right corner of parent widget."""
        parent_widget = self.parentWidget()
        if parent_widget and parent_widget.isVisible():
            # For Tool windows, move() expects global screen coordinates.
            # Map the parent's top-right corner to global space.
            top_right_global = parent_widget.mapToGlobal(parent_widget.rect().topRight())
            
            # Position near the top-right edge with a 10px internal margin
            x_pos = top_right_global.x() - self.width() - 10
            y_pos = top_right_global.y() + 10
            
            self.move(x_pos, y_pos)
            self.raise_()

    def _on_scene_mode_changed(self, text: str) -> None:
        mode = "2d" if "2D" in text else "3d"
        self.controller.web_view.page().runJavaScript(
            f"window.offlineGIS.setSceneMode('{mode}');"
        )

    def _on_basemap_visibility_changed(self, text: str) -> None:
        """Toggle OSM basemap visibility without resetting camera."""
        visible = "Show" in text  # "Show Map" = True, "Hide Map" = False
        self.controller.web_view.page().runJavaScript(
            f"window.offlineGIS.setBasemapVisibility({str(visible).lower()});"
        )

    def _on_polygon_visibility_toggled(self, checked: bool) -> None:
        self.controller.web_view.page().runJavaScript(
            f"window.offlineGIS.setSearchPolygonVisibility({str(checked).lower()});"
        )

    def update_aoi_stats(self, vertices: int, area_text: str) -> None:
        """Update the AOI statistics display."""
        self._last_aoi_vertices = int(vertices)
        self._last_aoi_area_text = str(area_text)
        self._apply_aoi_visibility()

    def _apply_aoi_visibility(self) -> None:
        vertices = self._last_aoi_vertices
        area_text = self._last_aoi_area_text
        self.polygon_visibility_checkbox.setVisible(True)
        self.polygon_visibility_checkbox.setEnabled(vertices >= 3)
        if vertices >= 3 and not self._special_mode_active:
            self.aoi_stats_label.setText(f"Area: {area_text}\nVertices: {vertices}")
            self.aoi_stats_label.setVisible(True)
        else:
            self.aoi_stats_label.setVisible(False)

        self.adjustSize()
        main_win = self.window()
        if hasattr(main_win, "_position_compositor_overlay"):
            main_win._position_compositor_overlay()


class BusyOverlay(QWidget):
    """Semi-transparent overlay with a loading spinner and message."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # Block mouse events while busy
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        
        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.container = QWidget()
        self.container.setFixedSize(280, 120)
        self.container.setObjectName("busyContainer")
        self.container.setStyleSheet("""
            QWidget#busyContainer {
                background: rgba(255, 255, 255, 0.95);
                border: 1px solid #0078d4;
                border-radius: 12px;
            }
            QLabel#busyTitle {
                color: #0078d4;
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#busyMessage {
                color: #444444;
                font-size: 13px;
            }
        """)
        
        self.inner_layout = QVBoxLayout(self.container)
        self.inner_layout.setContentsMargins(20, 20, 20, 20)
        self.inner_layout.setSpacing(10)
        
        self.title = QLabel("ResGIS Engine")
        self.title.setObjectName("busyTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.message = QLabel("Loading data...")
        self.message.setObjectName("busyMessage")
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setWordWrap(True)
        
        # Simple CSS-based pulse animation simulation via QProgressBar
        from qtpy.QtWidgets import QProgressBar
        self.progress = QProgressBar()
        self.progress.setRange(0, 0) # Indeterminate
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.setStyleSheet("""
            QProgressBar {
                background: #f0f0f0;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background: #0078d4;
                border-radius: 2px;
            }
        """)
        
        self.inner_layout.addWidget(self.title)
        self.inner_layout.addWidget(self.progress)
        self.inner_layout.addWidget(self.message)
        
        self.layout.addWidget(self.container)
        self.hide()

    def show_with_message(self, message: str):
        self.message.setText(message)
        self.raise_()
        self.show()


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
        "Fill Volume",
    }
    TOGGLE_ACTIONS: set[str] = {
        "Layer Compositor",
        "Comparator",
        "Distance / Azimuth",
        "Elevation Profile",
        "Fill Volume",
        "Pan",
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
                ("Layer Compositor", "layer_compositor"),
                ("Comparator", "comparator"),
                ("Fly Through", "fly_through"),
            ),
        ),
        (
            "measurement",
            (
                ("Distance / Azimuth", "measure_distance"),
                ("Elevation Profile", "elevation_profile"),
                ("Fill Volume", "volume"),
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
                ("Pan", "pan"),
                ("Zoom In", "zoom_in"),
                ("Zoom Out", "zoom_out"),
                ("Zoom to Extent", "zoom_extent"),
            ),
        ),
        (
            "file",
            (
                ("Data Source Manager", "data_source_manager"),
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
        self._project_name = "Untitled Project"
        self._is_modified = True
        self._update_window_title()

        # Initialize database when in server mode
        if app_mode in (DesktopAppMode.UNIFIED, DesktopAppMode.SERVER):
            try:
                from platform_core.db.session import init_db

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
        self.visualization_tools_switch: QCheckBox | None = None
        self.measurement_tools_switch: QCheckBox | None = None

        if app_mode != DesktopAppMode.SERVER:
            (
                self.main_toolbar,
                self.toolbar_actions,
                self.visualization_actions,
                self.measurement_actions,
                self.action_group_by_label,
                self.visualization_tools_switch,
                self.measurement_tools_switch,
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
        from qtpy.QtWebEngineWidgets import QWebEngineProfile, QWebEngineSettings
        
        # Create a unique profile name based on app mode to isolate caches (e.g. Ingest vs Search)
        # This prevents "Access is denied" errors in the GPUCache directory.
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
        # It sits ONLY under the map column (web_view), not the full window.
        # We achieve this by putting the web_view in its own vertical splitter.
        from client_desktop.backend.elevation_profile_panel import (
            ElevationProfilePanel,
        )

        self.elevation_profile_panel = ElevationProfilePanel(self)
        self.elevation_profile_panel.hide()
        self.elevation_profile_panel.close_requested.connect(
            self._on_elevation_profile_close
        )

        # ── Map column: web_view (top) | profile panel (bottom) ───────────
        self._map_v_splitter = QSplitter(Qt.Orientation.Vertical, self)
        self._map_v_splitter.addWidget(self.web_view)
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
        self.controller.project_metadata_changed.connect(self.set_project_info)
        self._last_search_params = {}

        if app_mode == DesktopAppMode.CLIENT:
            self._create_menu_bar()


        self.compositor_overlay = LayerCompositorOverlay(self.web_view, self.controller)
        self.map_overlay_controls = MapOverlayControls(self.web_view, self.controller)
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
        # Wire fill volume job completion → uncheck toolbar button
        self.controller._on_fill_volume_done = self._on_fill_volume_done

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

        if (
            self.visualization_tools_switch is not None
            and self.measurement_tools_switch is not None
        ):
            self.visualization_tools_switch.toggled.connect(
                self._set_visualization_tools_visible
            )
            self.measurement_tools_switch.toggled.connect(
                self._set_measurement_tools_visible
            )
            self._set_visualization_tools_visible(
                bool(self.visualization_tools_switch.isChecked())
            )
            self._set_measurement_tools_visible(
                bool(self.measurement_tools_switch.isChecked())
            )

        base_path = (
            Path(__file__).resolve().parents[2]
            / "desktop_client"
            / "client_frontend"
            / "web_assets"
            / "index.html"
        )

        if not base_path.exists():
            # Fallback: try legacy path structure
            base_path = (
                Path(__file__).resolve().parents[3]
                / "src"
                / "offline_gis_app"
                / "client_frontend"
                / "web_assets"
                / "index.html"
            )

        # Ensure the cesium/ directory is accessible from the same directory as index.html.
        # The Cesium build files live in desktop/web_assets/cesium/ but index.html is in
        # client_frontend/web_assets/.  We create a symlink (or copy on Windows) so that
        # the relative path ./cesium/Cesium.js resolves correctly for QWebEngineView.
        self._ensure_cesium_assets(base_path.parent)

        html_url = QUrl.fromLocalFile(str(base_path.resolve()))
        html_url.setQuery(f"v={int(time.time())}")
        self.web_view.setUrl(html_url)

    def closeEvent(self, event) -> None:
        """Handle window close to release WebEngine resources properly."""
        if hasattr(self, "web_view") and self.web_view:
            # Detach the page from the view and profile before destruction
            # to prevent "Expect troubles" warnings.
            self.web_view.setPage(None)
            self.web_view.deleteLater()
        
        if hasattr(self, "profile") and self.profile:
            self.profile.deleteLater()
            
        super().closeEvent(event)

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
            if hasattr(self, "compositor_overlay"):
                self.compositor_overlay.hide()

    def _set_measurement_tools_visible(self, visible: bool) -> None:
        """Show or hide measurement tools in the toolbar.

        Args:
            visible: True to show tools, False to hide.
        """
        self._measurement_tools_enabled = bool(visible)
        self._refresh_toolbar_action_state()
        if hasattr(self, "controller") and not visible:
            self.controller.on_toolbar_group_disabled("measurement")

    def _on_toolbar_action_triggered(self, action_label: str, checked: bool) -> None:
        """Handle toolbar action triggers.

        Args:
            action_label: Label of the triggered action.
            checked: Checked state for toggle actions.
        """
    def _on_toolbar_action_triggered(self, action_label: str, checked: bool) -> None:
        """Handle toolbar action triggers by coordinating with the controller and refreshing UI state."""
        action = self.toolbar_actions.get(action_label)
        if action is None:
            return

        # --- Dropdown / Selection Phase ---
        if action_label == "Comparator" and checked:
            self._show_comparator_dropdown()
            # Note: We don't return here yet, we still let the controller/refresh run
        elif action_label == "Layer Compositor" and checked:
            self._show_layer_compositor_overlay()
        elif action_label == "Export":
            self._show_export_dropdown()
            return
        elif action_label == "Add Raster Layer":
            self.controller.add_raster_layers()
            return
        elif action_label == "Add Vector":
            self.controller.add_vector_layers()
            return

        # --- State Sync Phase ---
        # Special case: Layer Compositor toggled OFF
        if action_label == "Layer Compositor" and not checked:
            self.controller.disable_layer_compositor()
            if hasattr(self, "compositor_overlay"):
                self.compositor_overlay.hide()
        else:
            # Delegate all other actions to the controller
            final_state = self.controller.handle_toolbar_action(action_label, checked=checked)
            # Sync the action's checked state if the controller returned a definitive boolean
            if action.isCheckable() and isinstance(final_state, bool):
                action.blockSignals(True)
                action.setChecked(final_state)
                action.blockSignals(False)

        # --- Interaction Exclusivity ---
        # If an interaction tool was just ENABLED, uncheck all OTHER interaction tools.
        interaction_toggles = {
            "Pan",
            "Distance / Azimuth",
            "Elevation Profile",
            "Fill Volume",
            "Add Point",
            "Add Line",
            "Add Polygon",
            "Add Text Label",
        }
        if action_label in interaction_toggles and action.isChecked():
            for other_label in interaction_toggles:
                if other_label == action_label:
                    continue
                if action_label == "Pan" and other_label == "Elevation Profile":
                    continue
                other_action = self.toolbar_actions.get(other_label)
                if other_action and other_action.isCheckable() and other_action.isChecked():
                    other_action.blockSignals(True)
                    other_action.setChecked(False)
                    other_action.blockSignals(False)
                    # Tell controller the other tool is now OFF
                    self.controller.handle_toolbar_action(other_label, False)

        # --- Overlay Management ---
        if hasattr(self, "map_overlay_controls"):
            # Update AOI polygon visibility context
            is_special = any(
                self.toolbar_actions.get(l).isChecked() 
                for l in ["Comparator", "Layer Compositor"] 
                if self.toolbar_actions.get(l)
            )
            self.map_overlay_controls.set_special_mode(is_special)

        # --- Final UI Refresh ---
        # This will handle mutual exclusivity (grey-out) and contextual visibility
        self._refresh_toolbar_action_state()

    def _show_layer_compositor_overlay(self) -> None:
        """Show the layer compositor overlay for adjusting layer opacities."""
        action = self.toolbar_actions.get("Layer Compositor")
        if action is None:
            return

        layers = self.controller.available_swipe_layer_options()
        if not layers:
            self.panel.log("No searched layers available for compositor.")
            action.setChecked(False)
            return

        self.compositor_overlay.update_layers()
        self.compositor_overlay.show()
        self.compositor_overlay.raise_()
        self.compositor_overlay.adjustSize()

        self._position_compositor_overlay()
        action.setChecked(True)

    def _create_menu_bar(self) -> None:
        menu_bar = self.menuBar()
        menu_bar.setNativeMenuBar(False)

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

        edit_menu = menu_bar.addMenu("&Edit")
        undo_action = QAction(IconRegistry.get("undo", size=16), "Undo", self)
        redo_action = QAction(IconRegistry.get("redo", size=16), "Redo", self)
        undo_action.triggered.connect(self.controller.undo_last_action)
        redo_action.triggered.connect(self.controller.redo_last_action)
        edit_menu.addAction(undo_action)
        edit_menu.addAction(redo_action)

        help_menu = menu_bar.addMenu("&Help")
        docs_action = QAction("Documentation", self)
        docs_action.triggered.connect(self._open_help_url)
        help_menu.addAction(docs_action)

    def _open_help_url(self) -> None:
        if not self.HELP_URL:
            self.panel.log("Help URL is not configured yet.")
            return
        QDesktopServices.openUrl(QUrl(self.HELP_URL))

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

    def set_busy_overlay(self, active: bool, message: str = "") -> None:
        """Toggle the modal busy overlay."""
        if active:
            self.busy_overlay.show_with_message(message)
            self.busy_overlay.resize(self.size())
        else:
            self.busy_overlay.hide()

    def moveEvent(self, event: object) -> None:
        """Handle window move event.

        Args:
            event: Move event object.
        """
        super().moveEvent(event)
        self._position_compositor_overlay()
        if hasattr(self, "map_overlay_controls") and self.map_overlay_controls.isVisible():
            self.map_overlay_controls.update_position()

    def resizeEvent(self, event: object) -> None:
        """Handle window resize event.

        Args:
            event: Resize event object.
        """
        super().resizeEvent(event)
        if hasattr(self, "busy_overlay"):
            self.busy_overlay.resize(self.size())
        if hasattr(self, "compositor_overlay") and self.compositor_overlay.isVisible():
            self._position_compositor_overlay()
        if (
            hasattr(self, "map_overlay_controls")
            and self.map_overlay_controls.isVisible()
        ):
            self.map_overlay_controls.update_position()

    def _position_compositor_overlay(self) -> None:
        """Position the compositor overlay in the top-right corner of the web view."""
        if (
            not hasattr(self, "compositor_overlay")
            or not self.compositor_overlay.isVisible()
        ):
            return
        w = self.compositor_overlay.width()
        top_right = self.web_view.mapToGlobal(self.web_view.rect().topRight())
        y_offset = 20
        if (
            hasattr(self, "map_overlay_controls")
            and self.map_overlay_controls.isVisible()
        ):
            y_offset += self.map_overlay_controls.height() + 10
        self.compositor_overlay.move(top_right.x() - w - 20, top_right.y() + y_offset)

    def _show_comparator_dropdown(self) -> None:
        """Show the comparator layer selection dropdown dialog."""
        action = self.toolbar_actions.get("Comparator")
        if action is None:
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

        popup = QDialog(self, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        popup.setObjectName("comparatorDropdown")
        popup.setStyleSheet(
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

        layout = QVBoxLayout(popup)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("Comparator")
        layout.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("Layout"))
        layout_combo = QComboBox(popup)
        layout_combo.addItem("2 panes (side-by-side)", 2)
        layout_combo.addItem("3 panes (2 top + 1 bottom)", 3)
        layout_combo.addItem("4 panes (2 x 2)", 4)
        row.addWidget(layout_combo)
        layout.addLayout(row)

        layer_list = QListWidget(popup)
        layer_list.setMinimumHeight(150)
        for layer in layers:
            item = QListWidgetItem(layer["label"], layer_list)
            item.setData(Qt.ItemDataRole.UserRole, layer["path"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if layer["visible"] else Qt.CheckState.Unchecked
            )
        layout.addWidget(layer_list)

        info_label = QLabel("Select up to 4 layers.")
        layout.addWidget(info_label)

        apply_button = QPushButton("Apply")
        layout.addWidget(apply_button)
        applied = {"done": False}

        def _selected_count() -> int:
            return sum(
                1
                for i in range(layer_list.count())
                if layer_list.item(i).checkState() == Qt.CheckState.Checked
            )

        def _sync_layout_by_selection() -> None:
            selected_count = _selected_count()
            model = layout_combo.model()
            for idx in range(layout_combo.count()):
                pane_count = int(layout_combo.itemData(idx) or 0)
                item = model.item(idx) if hasattr(model, "item") else None
                if item is not None:
                    item.setEnabled(pane_count == selected_count)

            target_index = layout_combo.findData(selected_count)
            if target_index >= 0:
                if layout_combo.currentIndex() != target_index:
                    layout_combo.setCurrentIndex(target_index)
                info_label.setText(
                    f"{selected_count} layer(s) selected. Layout locked to {selected_count} panes."
                )
                apply_button.setEnabled(True)
                return

            info_label.setText("Select at least 2 layers.")
            apply_button.setEnabled(False)

        def enforce_max_selection(changed_item: QListWidgetItem) -> None:
            checked_items = [
                layer_list.item(i)
                for i in range(layer_list.count())
                if layer_list.item(i).checkState() == Qt.CheckState.Checked
            ]
            if len(checked_items) <= 4:
                _sync_layout_by_selection()
                return
            changed_item.setCheckState(Qt.CheckState.Unchecked)
            info_label.setText("Maximum 4 layers are allowed.")
            _sync_layout_by_selection()

        layer_list.itemChanged.connect(enforce_max_selection)
        _sync_layout_by_selection()

        def apply_selection() -> None:
            selected_paths: list[str] = []
            for i in range(layer_list.count()):
                item = layer_list.item(i)
                if item.checkState() != Qt.CheckState.Checked:
                    continue
                selected_paths.append(str(item.data(Qt.ItemDataRole.UserRole) or ""))

            selected_paths = [path for path in selected_paths if path]
            if len(selected_paths) < 2:
                self.panel.log("Select at least two layers for comparator.")
                action.setChecked(False)
                popup.close()
                return

            pane_count = int(layout_combo.currentData())
            if len(selected_paths) != pane_count:
                self.panel.log(
                    f"Select exactly {pane_count} layers for selected layout."
                )
                return

            success = self.controller.apply_comparator_selection(selected_paths)
            if success:
                action.setChecked(True)
                applied["done"] = True
                if hasattr(self, "map_overlay_controls"):
                    self.map_overlay_controls.polygon_visibility_checkbox.setChecked(
                        False
                    )
            else:
                action.setChecked(False)
            self._refresh_toolbar_action_state()
            popup.close()

        apply_button.clicked.connect(apply_selection)

        popup.adjustSize()
        global_pos = anchor.mapToGlobal(anchor.rect().bottomLeft())
        popup.move(global_pos)
        popup.exec()

        if not applied["done"]:
            action.setChecked(False)

    def _show_export_dropdown(self) -> None:
        """Show export options dropdown under the Export toolbar button."""
        from qtpy.QtWidgets import QMenu

        action = self.toolbar_actions.get("Export")
        anchor = self.main_toolbar.widgetForAction(action) if action else None

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #ffffff;
                border: 1px solid #d1d9e6;
                border-radius: 10px;
                padding: 8px;
            }
            QMenu::item {
                padding: 12px 40px 12px 16px;
                font-size: 13px;
                font-weight: 500;
                color: #2d3748;
                border-radius: 6px;
                margin: 2px 0px;
            }
            QMenu::item:selected {
                background: #edf2f7;
                color: #2b6cb0;
            }
            QMenu::icon {
                padding-left: 10px;
            }
        """)
        gpkg_act = menu.addAction(
            IconRegistry.get("export_gpkg", size=16), "Export GeoPackage"
        )
        pdf_act = menu.addAction(
            IconRegistry.get("print_layout", size=16), "Export PDF"
        )

        pos = (
            anchor.mapToGlobal(anchor.rect().bottomLeft())
            if anchor
            else self.cursor().pos()
        )
        chosen = menu.exec(pos)

        if chosen == gpkg_act:
            self.controller.handle_toolbar_action("Export GeoPackage")
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
            viz_exclusives = {"Comparator", "Layer Compositor", "Fly Through"}
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
                "Fill Volume",
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

            # 5. Annotation tool exclusivity (Add Point, Add Line, Add Polygon, Add Text Label)
            # Disable during Comparator and Fly Through modes.
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

    def _on_fill_volume_done(self) -> None:
        """Uncheck the Fill Volume toolbar button when the analysis job finishes."""
        action = self.toolbar_actions.get("Fill Volume")
        if action is not None:
            action.blockSignals(True)
            action.setChecked(False)
            action.blockSignals(False)


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
        from qtpy.QtWidgets import QApplication
        import logging
        logger = logging.getLogger("desktop.main_window")
        
        logger.debug("_on_measure_cursor_changed called: enabled=%s", enabled)
        self._measure_cursor_active = bool(enabled)
        # Always clear any application-level override so toolbar/panel stay normal
        while QApplication.overrideCursor():
            QApplication.restoreOverrideCursor()
            
        if self._measure_cursor_active:
            logger.info("Applying crosshair cursor to web view")
            self._apply_crosshair_to_webview()
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
        QCheckBox,
        QCheckBox,
    ]:
        """Create and configure the main toolbar.

        Returns:
            Tuple containing:
                - QToolBar: The main toolbar widget
                - dict[str, QAction]: Mapping of action labels to QAction objects
                - list[QAction]: List of visualization actions
                - list[QAction]: List of measurement actions
                - dict[str, str]: Mapping of action labels to group names
                - QCheckBox: Visualization tools toggle checkbox
                - QCheckBox: Measurement tools toggle checkbox
        """
        toolbar = QToolBar("Main")
        toolbar.setObjectName("desktopMainToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(QSize(24, 24))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        toolbar.setStyleSheet(
            """
            QToolBar#desktopMainToolbar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #f5f7f9);
                border: none;
                border-bottom: 1px solid #d1d9e6;
                spacing: 6px;
                padding: 6px 10px;
            }
            QToolBar#desktopMainToolbar QToolButton {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 6px;
                padding: 4px;
                margin: 0px 2px;
                min-width: 34px;
                min-height: 34px;
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
            QToolBar#desktopMainToolbar QCheckBox#toolbarModuleToggle {
                spacing: 8px;
                margin-left: 12px;
                margin-right: 6px;
                color: #2c3e50;
                font-size: 11px;
                font-weight: bold;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            QToolBar#desktopMainToolbar QCheckBox#toolbarModuleToggle::indicator {
                width: 16px;
                height: 16px;
                border: 1.5px solid #bdc3c7;
                border-radius: 4px;
            }
            QToolBar#desktopMainToolbar QCheckBox#toolbarModuleToggle::indicator:checked {
                background-color: #0078d4;
                border-color: #0078d4;
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

        spacer = QWidget(self)
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        toolbar.addSeparator()

        visualization_switch = QCheckBox("Show Visualization Tools", self)
        visualization_switch.setObjectName("toolbarModuleToggle")
        visualization_switch.setChecked(True)
        visualization_switch.setToolTip("Show or hide visualization toolbar actions")
        toolbar.addWidget(visualization_switch)

        measurement_switch = QCheckBox("Show Measurement Tools", self)
        measurement_switch.setObjectName("toolbarModuleToggle")
        measurement_switch.setChecked(True)
        measurement_switch.setToolTip("Show or hide measurement toolbar actions")
        toolbar.addWidget(measurement_switch)

        return (
            toolbar,
            actions,
            visualization_actions,
            measurement_actions,
            action_group_by_label,
            visualization_switch,
            measurement_switch,
        )

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
        if self.app_mode == DesktopAppMode.SERVER:
            self.setWindowTitle("ResGIS")
            return

        prefix = "*" if self._is_modified else ""
        project_display = f"{prefix}{self._project_name}"
        
        # Long hyphen: — (U+2014)
        self.setWindowTitle(f"{project_display} — ResGIS")
