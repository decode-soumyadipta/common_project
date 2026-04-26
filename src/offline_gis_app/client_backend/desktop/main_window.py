"""Main window module for the Offline GIS Desktop application.

This module provides the main window UI components including:
- LayerCompositorOverlay: Overlay for adjusting layer opacities
- MapOverlayControls: Controls for scene mode and polygon visibility
- MainWindow: Primary application window with toolbar and web view
"""
from __future__ import annotations

from pathlib import Path
import time

from qtpy.QtCore import QSize, Qt, QUrl
from qtpy.QtGui import QAction, QColor, QCursor, QGuiApplication, QIcon, QPainter, QPen, QPixmap
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

from offline_gis_app.client_backend.desktop.app_mode import DesktopAppMode
from offline_gis_app.client_backend.desktop.bridge import WebBridge
from offline_gis_app.client_backend.desktop.control_panel import ControlPanel
from offline_gis_app.client_backend.desktop.controller import DesktopController
from offline_gis_app.client_backend.desktop.icon_registry import IconRegistry
from offline_gis_app.client_backend.desktop.status_bar import GISStatusBar
from offline_gis_app.client_backend.desktop.titiler_manager import TiTilerManager
from offline_gis_app.client_backend.desktop.web_page import LoggingWebEnginePage


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
        
        Clears existing sliders and creates new ones for all visible layers.
        Each slider controls the opacity of its corresponding layer.
        """
        layers = self.controller.available_swipe_layer_options()
        active_layers = [layer for layer in layers if layer.get("visible")]

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

        if not active_layers:
            no_layers_label = QLabel("No active layers.")
            self.sliders_layout.addWidget(no_layers_label)
            return

        for layer in active_layers:
            row = QHBoxLayout()
            label = QLabel(layer["label"])
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
        self._special_mode_active = False  # True when comparator or compositor is active
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
                font-size: 11px;
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

        # Polygon Visibility (hidden by default, shown only when polygon exists)
        self.polygon_visibility_checkbox = QCheckBox("Show Search AOI Polygon")
        self.polygon_visibility_checkbox.setChecked(True)
        self.polygon_visibility_checkbox.setVisible(False)  # Hidden until polygon exists
        self.polygon_visibility_checkbox.toggled.connect(
            self._on_polygon_visibility_toggled
        )
        self.layout_main.addWidget(self.polygon_visibility_checkbox)

        # AOI Stats
        self.aoi_stats_label = QLabel("Area: 0 m\u00b2 | Vertices: 0")
        self.aoi_stats_label.setWordWrap(True)
        self.aoi_stats_label.setVisible(False)
        self.layout_main.addWidget(self.aoi_stats_label)

        self.setFixedWidth(200)

        # Connect bridge signals
        self.controller.bridge.aoiStatsUpdated.connect(self.update_aoi_stats)

        self.hide()

    def set_special_mode(self, active: bool) -> None:
        """Call when comparator or compositor mode is activated/deactivated.
        
        Hides the AOI polygon checkbox in special modes.
        """
        self._special_mode_active = bool(active)
        # Force a visibility refresh
        if self._special_mode_active:
            self.polygon_visibility_checkbox.setVisible(False)
            self.aoi_stats_label.setVisible(False)
            self.adjustSize()

    def update_position(self) -> None:
        """Update the overlay position to top-right corner of parent widget."""
        parent_widget = self.parentWidget()
        if parent_widget and parent_widget.isVisible():
            parent_rect = parent_widget.rect()
            top_right = parent_widget.mapToGlobal(parent_rect.topRight())
            x_pos = top_right.x() - self.width() - 20
            y_pos = top_right.y() + 20
            if x_pos < 0:
                x_pos = 10
            if y_pos < 0:
                y_pos = 10
            self.move(x_pos, y_pos)

    def _on_scene_mode_changed(self, text: str) -> None:
        mode = "2d" if "2D" in text else "3d"
        self.controller.web_view.page().runJavaScript(
            f"window.offlineGIS.setSceneMode('{mode}');"
        )

    def _on_polygon_visibility_toggled(self, checked: bool) -> None:
        self.controller.web_view.page().runJavaScript(
            f"window.offlineGIS.setSearchPolygonVisibility({str(checked).lower()});"
        )

    def update_aoi_stats(self, vertices: int, area_text: str) -> None:
        """Update the AOI statistics display."""
        if vertices >= 3 and not self._special_mode_active:
            self.polygon_visibility_checkbox.setVisible(True)
            self.aoi_stats_label.setText(f"Area: {area_text}\nVertices: {vertices}")
            self.aoi_stats_label.setVisible(True)
        else:
            self.polygon_visibility_checkbox.setVisible(False)
            self.aoi_stats_label.setVisible(False)
        
        self.adjustSize()
        main_win = self.window()
        if hasattr(main_win, "_position_compositor_overlay"):
            main_win._position_compositor_overlay()


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
        "Slope & Aspect",
    }
    TOGGLE_ACTIONS: set[str] = {
        "Layer Compositor",
        "Comparator",
        "Distance / Azimuth",
        "Elevation Profile",
        "Fill Volume",
        "Slope & Aspect",
        "Pan",
        "Add Point",
        "Add Polygon",
    }
    TOOLBAR_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
        (
            "visualization",
            (
                ("Layer Compositor", "layer_compositor"),
                ("Comparator", "comparator"),
            ),
        ),
        (
            "measurement",
            (
                ("Distance / Azimuth", "measure_distance"),
                ("Elevation Profile", "elevation_profile"),
                ("Fill Volume", "volume"),
                ("Slope & Aspect", "slope_aspect"),
                ("Clear Last", "clear_last"),
                ("Clear All", "clear_all"),
            ),
        ),
        (
            "annotation",
            (
                ("Add Point", "annotate_point"),
                ("Add Polygon", "annotate_polygon"),
                ("Save Annotations", "save_annotations"),
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
                ("Add Vector", "open_vector"),
                ("Add Raster Layer", "open_raster"),
                ("Save Project", "save_project"),
                ("Export", "export_gpkg"),
            ),
        ),
    )

    def __init__(self, app_mode: DesktopAppMode = DesktopAppMode.UNIFIED):
        """Initialize the main window.
        
        Args:
            app_mode: Application mode (UNIFIED, CLIENT, or SERVER).
        """
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
        self.web_view = QWebEngineView(self)
        self.web_view.setPage(LoggingWebEnginePage(self.web_view))
        web_settings = self.web_view.settings()
        web_settings.setAttribute(
            QWebEngineSettings.LocalContentCanAccessRemoteUrls, True
        )
        web_settings.setAttribute(
            QWebEngineSettings.LocalContentCanAccessFileUrls, True
        )
        # Disable disk cache so local JS/CSS changes are always picked up.
        # For a local file:// app there is no benefit to caching — it only
        # causes stale bridge.js to be served after code updates.
        try:
            from qtpy.QtWebEngineWidgets import QWebEngineProfile
            profile = self.web_view.page().profile()
            profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
        except Exception:
            pass

        # ── Elevation profile panel (hidden until first profile) ──────────
        # It sits ONLY under the map column (web_view), not the full window.
        # We achieve this by putting the web_view in its own vertical splitter.
        from offline_gis_app.client_backend.desktop.elevation_profile_panel import (
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

        self.compositor_overlay = LayerCompositorOverlay(self.web_view, self.controller)
        self.map_overlay_controls = MapOverlayControls(self.web_view, self.controller)
        # Show map overlay controls by default
        self.map_overlay_controls.show()

        # ── QGIS-style status bar ────────────────────────────────────────
        self.gis_status_bar = GISStatusBar(self)
        self.setStatusBar(self.gis_status_bar)
        self.bridge.mouseCoordinates.connect(self.gis_status_bar.on_mouse_coordinates)
        self.bridge.cameraChanged.connect(self.gis_status_bar.on_camera_changed)
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
        self.controller._elevation_profile.on_complete = self._on_elevation_profile_complete
        # Wire coordinator to use the embedded panel
        self.controller._elevation_profile.set_panel(self.elevation_profile_panel)
        # Wire fill volume job completion → uncheck toolbar button
        self.controller._on_fill_volume_done = self._on_fill_volume_done
        # Wire slope/aspect completion → uncheck toolbar button
        self.controller._on_slope_aspect_done = self._on_slope_aspect_done

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
            / "client_frontend"
            / "web_assets"
            / "index.html"
        )

        if not base_path.exists():
            # Fallback: try alternative path structure
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
        desktop_web_assets = web_assets_dir.parent.parent / "desktop" / "web_assets"

        def _link_dir(name: str, required_file: str | None = None) -> None:
            link_path = web_assets_dir / name
            canonical = desktop_web_assets / name

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
        _link_dir("basemap")

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
        if action_label == "Comparator":
            action = self.toolbar_actions.get(action_label)
            if action is None:
                return
            if checked:
                self._show_comparator_dropdown()
                # Disable Layer Compositor while Comparator is active
                compositor_action = self.toolbar_actions.get("Layer Compositor")
                if compositor_action is not None:
                    compositor_action.setEnabled(False)
                    compositor_action.setChecked(False)
                    if hasattr(self, "compositor_overlay"):
                        self.compositor_overlay.hide()
                # Hide AOI checkbox in comparator mode
                if hasattr(self, "map_overlay_controls"):
                    self.map_overlay_controls.set_special_mode(True)
                return
            # Comparator toggled OFF — disable it and re-enable compositor
            final_state = self.controller.handle_toolbar_action(
                action_label, checked=checked
            )
            if isinstance(final_state, bool):
                action.setChecked(final_state)
            # Always re-enable Layer Compositor when Comparator is off
            compositor_action = self.toolbar_actions.get("Layer Compositor")
            if compositor_action is not None:
                compositor_action.setEnabled(True)
            # Restore AOI checkbox visibility
            if hasattr(self, "map_overlay_controls"):
                self.map_overlay_controls.set_special_mode(False)
            return

        if action_label == "Layer Compositor":
            action = self.toolbar_actions.get(action_label)
            if action is None:
                return
            if checked:
                self._show_layer_compositor_overlay()
                # Disable Comparator while Layer Compositor is active
                comparator_action = self.toolbar_actions.get("Comparator")
                if comparator_action is not None:
                    comparator_action.setEnabled(False)
                    comparator_action.setChecked(False)
                    # Also tell controller to disable comparator if it was on
                    self.controller.handle_toolbar_action("Comparator", checked=False)
                # Hide AOI checkbox in compositor mode
                if hasattr(self, "map_overlay_controls"):
                    self.map_overlay_controls.set_special_mode(True)
                return
            # Layer Compositor toggled OFF — re-enable comparator
            self.controller.disable_layer_compositor()
            if hasattr(self, "compositor_overlay"):
                self.compositor_overlay.hide()
            action.setChecked(False)
            # Always re-enable Comparator when Layer Compositor is off
            comparator_action = self.toolbar_actions.get("Comparator")
            if comparator_action is not None:
                comparator_action.setEnabled(True)
            # Restore AOI checkbox visibility
            if hasattr(self, "map_overlay_controls"):
                self.map_overlay_controls.set_special_mode(False)
            return

        if action_label == "Export":
            self._show_export_dropdown()
            return

        if action_label in ("Add Vector", "Add Raster Layer"):
            self.controller.browse_path()
            return

        final_state = self.controller.handle_toolbar_action(
            action_label, checked=checked
        )
        action = self.toolbar_actions.get(action_label)
        if action is None or not action.isCheckable():
            return
        if isinstance(final_state, bool):
            action.blockSignals(True)
            action.setChecked(final_state)
            action.blockSignals(False)

        interaction_toggles = {
            "Pan",
            "Distance / Azimuth",
            "Elevation Profile",
            "Fill Volume",
            "Slope & Aspect",
            "Add Point",
            "Add Polygon",
        }
        if action_label in interaction_toggles and bool(final_state):
            for other_label in interaction_toggles:
                if other_label == action_label:
                    continue
                other_action = self.toolbar_actions.get(other_label)
                if (
                    other_action is not None
                    and other_action.isCheckable()
                    and other_action.isChecked()
                ):
                    other_action.setChecked(False)

    def _show_layer_compositor_overlay(self) -> None:
        """Show the layer compositor overlay for adjusting layer opacities."""
        action = self.toolbar_actions.get("Layer Compositor")
        if action is None:
            return

        layers = self.controller.available_swipe_layer_options()
        active_layers = [layer for layer in layers if layer.get("visible")]
        if not active_layers:
            self.panel.log("No active layers available for compositor.")
            action.setChecked(False)
            return

        self.compositor_overlay.update_layers()
        self.compositor_overlay.show()
        self.compositor_overlay.raise_()
        self.compositor_overlay.adjustSize()

        self._position_compositor_overlay()
        action.setChecked(True)

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

    def moveEvent(self, event: object) -> None:
        """Handle window move event.
        
        Args:
            event: Move event object.
        """
        super().moveEvent(event)
        self._position_compositor_overlay()

    def resizeEvent(self, event: object) -> None:
        """Handle window resize event.
        
        Args:
            event: Resize event object.
        """
        super().resizeEvent(event)
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
                background: #f8fafc;
                border: 1px solid #c9d3df;
                border-radius: 6px;
                padding: 4px 0px;
            }
            QMenu::item {
                padding: 7px 20px;
                font-size: 12px;
                color: #1a2a3a;
            }
            QMenu::item:selected {
                background: #e3edf8;
                color: #1f6fd2;
            }
        """)
        gpkg_act = menu.addAction(
            IconRegistry.get("export_gpkg", size=16), "Export GeoPackage"
        )
        pdf_act = menu.addAction(
            IconRegistry.get("print_layout", size=16), "Export PDF"
        )
        tiff_act = menu.addAction(
            IconRegistry.get("export_geotiff", size=16), "Export as GeoTIFF"
        )

        pos = anchor.mapToGlobal(anchor.rect().bottomLeft()) if anchor else self.cursor().pos()
        chosen = menu.exec(pos)

        if chosen == gpkg_act:
            self.controller.handle_toolbar_action("Export GeoPackage")
        elif chosen == pdf_act:
            self.panel.log("Export PDF: not yet implemented.")
        elif chosen == tiff_act:
            self.panel.log("Export GeoTIFF: not yet implemented.")

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

            if (
                group == "measurement"
                and self._toolbar_layer_context == "none"
            ):
                action.setEnabled(False)
                if action.isCheckable():
                    action.setChecked(False)
            else:
                action.setEnabled(True)

            if label == "Comparator" and hasattr(self, "controller"):
                comparator_available = self.controller.can_attempt_enable_comparator()
                if not comparator_available:
                    action.setEnabled(False)
                    if action.isCheckable():
                        action.setChecked(False)

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

    def _on_slope_aspect_done(self) -> None:
        """Uncheck the Slope & Aspect toolbar button when the analysis job finishes."""
        action = self.toolbar_actions.get("Slope & Aspect")
        if action is not None:
            action.blockSignals(True)
            action.setChecked(False)
            action.blockSignals(False)

    def _on_profile_cursor_moved(self, frac: float) -> None:
        """Forward cursor fraction to the profile panel for live crosshair update."""
        if self.elevation_profile_panel.isVisible():
            self.elevation_profile_panel.set_cursor_fraction(frac)

    def _build_crosshair_cursor(self) -> QCursor:
        """Build a precise black crosshair QCursor using QPainter."""
        from qtpy.QtGui import QPen
        size = 20          # smaller = more precise feel
        hot = size // 2    # hotspot at centre
        px = QPixmap(size, size)
        px.fill(QColor(0, 0, 0, 0))  # transparent background

        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # White halo for visibility on dark backgrounds
        halo_pen = QPen(QColor(255, 255, 255, 200), 2.5)
        p.setPen(halo_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        radius = 4
        p.drawEllipse(hot - radius, hot - radius, radius * 2, radius * 2)
        gap = radius + 1
        arm = 5
        p.drawLine(hot, hot - gap - arm, hot, hot - gap)
        p.drawLine(hot, hot + gap,       hot, hot + gap + arm)
        p.drawLine(hot - gap - arm, hot, hot - gap, hot)
        p.drawLine(hot + gap,       hot, hot + gap + arm, hot)

        # Black foreground on top
        black_pen = QPen(QColor(0, 0, 0, 255), 1.2)
        p.setPen(black_pen)
        p.drawEllipse(hot - radius, hot - radius, radius * 2, radius * 2)
        p.drawLine(hot, hot - gap - arm, hot, hot - gap)
        p.drawLine(hot, hot + gap,       hot, hot + gap + arm)
        p.drawLine(hot - gap - arm, hot, hot - gap, hot)
        p.drawLine(hot + gap,       hot, hot + gap + arm, hot)

        p.end()
        return QCursor(px, hot, hot)

    def _on_measure_cursor_changed(self, enabled: bool) -> None:
        """Set or restore the crosshair cursor on the map web view only."""
        from qtpy.QtWidgets import QApplication
        self._measure_cursor_active = bool(enabled)
        # Always clear any application-level override so toolbar/panel stay normal
        while QApplication.overrideCursor():
            QApplication.restoreOverrideCursor()
        if enabled:
            self._apply_crosshair_to_webview()
        else:
            self.web_view.unsetCursor()
            vp = self.web_view.focusProxy() or self.web_view.childAt(1, 1)
            if vp:
                vp.unsetCursor()

    def _apply_crosshair_to_webview(self) -> None:
        """Set crosshair cursor on the web view widget and its viewport child."""
        if getattr(self, "_applying_cursor", False):
            return
        self._applying_cursor = True
        try:
            self.web_view.setCursor(self._measure_crosshair_cursor)
            vp = self.web_view.focusProxy() or self.web_view.childAt(1, 1)
            if vp:
                vp.setCursor(self._measure_crosshair_cursor)
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
                background: #f1f3f7;
                border: none;
                border-bottom: 1px solid #d7dde6;
                spacing: 2px;
                padding: 2px 4px;
            }
            QToolBar#desktopMainToolbar QToolButton {
                background: #eef2f7;
                border: 1px solid #c4ccd6;
                border-radius: 3px;
                padding: 1px;
                margin: 0px;
                min-width: 30px;
                min-height: 30px;
                max-width: 30px;
                max-height: 30px;
            }
            QToolBar#desktopMainToolbar QToolButton:hover {
                background: #f7f9fc;
                border: 1px solid #aeb8c5;
            }
            QToolBar#desktopMainToolbar QToolButton:pressed {
                background: #dde3eb;
                border: 1px solid #9ba7b6;
            }
            QToolBar#desktopMainToolbar QToolButton:checked {
                background: #ffc857;
                border: 1px solid #d97a00;
            }
            QToolBar#desktopMainToolbar QToolButton:checked:hover {
                background: #ffd983;
                border: 1px solid #be6500;
            }
            QToolBar#desktopMainToolbar QToolButton:disabled {
                background: #e3e7ee;
                border: 1px solid #c8d0dc;
                color: #8c97a8;
            }
            QToolBar#desktopMainToolbar QCheckBox#toolbarModuleToggle {
                spacing: 6px;
                margin-left: 8px;
                margin-right: 4px;
                color: #1b2b3e;
                font-size: 12px;
                font-weight: 600;
            }
            QToolBar#desktopMainToolbar QCheckBox#toolbarModuleToggle::indicator {
                width: 15px;
                height: 15px;
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
