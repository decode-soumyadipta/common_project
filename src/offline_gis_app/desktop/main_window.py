from __future__ import annotations

from pathlib import Path
import time

from PySide6.QtCore import QEvent, QSize, Qt, QUrl
from PySide6.QtGui import QAction, QGuiApplication, QIcon
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStyle,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from offline_gis_app.desktop.app_mode import DesktopAppMode
from offline_gis_app.desktop.bridge import WebBridge
from offline_gis_app.desktop.control_panel import ControlPanel
from offline_gis_app.desktop.controller import DesktopController
from offline_gis_app.desktop.icon_registry import IconRegistry
from offline_gis_app.desktop.titiler_manager import TiTilerManager
from offline_gis_app.desktop.web_page import LoggingWebEnginePage


class ComparatorOverlayWidget(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._pane_frames: list[QFrame] = []
        self._pane_count: int = 0
        self.hide()

    def clear_overlay(self) -> None:
        for frame in self._pane_frames:
            frame.deleteLater()
        self._pane_frames.clear()
        self._pane_count = 0
        self.hide()

    def show_overlay(self, pane_count: int, layer_names: list[str]) -> None:
        pane_count = max(0, min(int(pane_count), 4))
        if pane_count < 2:
            self.clear_overlay()
            return

        for frame in self._pane_frames:
            frame.deleteLater()
        self._pane_frames.clear()

        for idx in range(pane_count):
            frame = QFrame(self)
            frame.setObjectName("comparatorPane")
            frame.setStyleSheet(
                """
                QFrame#comparatorPane {
                    border: 2px solid rgba(255, 221, 89, 0.95);
                    border-radius: 6px;
                    background: rgba(5, 12, 22, 0.06);
                }
                """
            )
            label = QLabel(layer_names[idx] if idx < len(layer_names) else f"Layer {idx + 1}", frame)
            label.setObjectName("comparatorPaneLabel")
            label.setStyleSheet(
                """
                QLabel#comparatorPaneLabel {
                    background: rgba(12, 20, 34, 0.82);
                    color: #f8fbff;
                    border-radius: 4px;
                    padding: 3px 7px;
                    font-size: 11px;
                    font-weight: 600;
                }
                """
            )
            label.adjustSize()
            frame.show()
            self._pane_frames.append(frame)

        self._pane_count = pane_count
        self._relayout_panes()
        self.show()
        self.raise_()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._relayout_panes()

    def _relayout_panes(self) -> None:
        if self._pane_count < 2 or not self._pane_frames:
            return

        spacing = 8
        width = max(0, self.width())
        height = max(0, self.height())
        if width <= 0 or height <= 0:
            return

        rects: list[tuple[int, int, int, int]] = []
        if self._pane_count == 2:
            half = (width - spacing) // 2
            rects = [
                (0, 0, half, height),
                (half + spacing, 0, width - (half + spacing), height),
            ]
        elif self._pane_count == 3:
            half = (width - spacing) // 2
            top_h = (height - spacing) // 2
            rects = [
                (0, 0, half, top_h),
                (half + spacing, 0, width - (half + spacing), top_h),
                (0, top_h + spacing, width, height - (top_h + spacing)),
            ]
        else:
            half_w = (width - spacing) // 2
            half_h = (height - spacing) // 2
            rects = [
                (0, 0, half_w, half_h),
                (half_w + spacing, 0, width - (half_w + spacing), half_h),
                (0, half_h + spacing, half_w, height - (half_h + spacing)),
                (half_w + spacing, half_h + spacing, width - (half_w + spacing), height - (half_h + spacing)),
            ]

        for idx, frame in enumerate(self._pane_frames):
            if idx >= len(rects):
                break
            x, y, w, h = rects[idx]
            frame.setGeometry(x, y, max(80, w), max(60, h))
            label = frame.findChild(QLabel, "comparatorPaneLabel")
            if label is not None:
                label.move(8, 8)


class MainWindow(QMainWindow):
    IMAGERY_ONLY_ACTIONS: set[str] = {
        "Layer Compositor",
    }
    DEM_ONLY_ACTIONS: set[str] = {
        "Hillshade",
        "Colour Relief",
        "Elevation Profile",
        "Volume Cut/Fill",
        "Viewshed / LOS",
        "Slope & Aspect",
    }
    TOGGLE_ACTIONS: set[str] = {
        "Hillshade",
        "Swipe Comparator",
        "Distance / Azimuth",
        "Pan",
        "Add Point",
        "Add Polygon",
        "Shadow Height",
    }
    TOOLBAR_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
        (
            "visualization",
            (
                ("Layer Compositor", "layer_compositor"),
                ("Hillshade", "hillshade"),
                ("Colour Relief", "colour_relief"),
                ("Swipe Comparator", "swipe_comparator"),
            ),
        ),
        (
            "measurement",
            (
                ("Distance / Azimuth", "measure_distance"),
                ("Polygon Area", "measure_area"),
                ("Elevation Profile", "elevation_profile"),
                ("Volume Cut/Fill", "volume"),
                ("Viewshed / LOS", "viewshed"),
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
                ("Shadow Height", "shadow_height"),
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
                ("North Arrow", "north_arrow"),
            ),
        ),
        (
            "file",
            (
                ("Open Raster", "open_raster"),
                ("Open DEM", "open_dem"),
                ("Save Project", "save_project"),
                ("Export GeoPackage", "export_gpkg"),
                ("Export Profile CSV", "export_profile_csv"),
            ),
        ),
    )

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
        self.web_view.installEventFilter(self)
        web_settings = self.web_view.settings()
        web_settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        web_settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        splitter = QSplitter(self)
        splitter.addWidget(self.panel_scroll)
        splitter.addWidget(self.web_view)
        if app_mode == DesktopAppMode.CLIENT:
            splitter.setSizes([500, 1100])
        else:
            splitter.setSizes([420, 1180])
        self.setCentralWidget(splitter)

        self.comparator_overlay = ComparatorOverlayWidget(self.web_view)
        self.comparator_overlay.setGeometry(self.web_view.rect())

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
            toolbar_context_callback=self.set_toolbar_layer_context,
        )

        for label, action in self.toolbar_actions.items():
            action.triggered.connect(
                lambda checked=False, action_label=label: self._on_toolbar_action_triggered(action_label, checked)
            )

        self.visualization_tools_switch.toggled.connect(self._set_visualization_tools_visible)
        self.measurement_tools_switch.toggled.connect(self._set_measurement_tools_visible)
        self._set_visualization_tools_visible(bool(self.visualization_tools_switch.isChecked()))
        self._set_measurement_tools_visible(bool(self.measurement_tools_switch.isChecked()))

        html_path = Path(__file__).parent / "web_assets" / "index.html"
        html_url = QUrl.fromLocalFile(str(html_path.resolve()))
        html_url.setQuery(f"v={int(time.time())}")
        self.web_view.setUrl(html_url)

    def _set_visualization_tools_visible(self, visible: bool) -> None:
        self._visualization_tools_enabled = bool(visible)
        self._refresh_toolbar_action_state()
        if hasattr(self, "controller") and not visible:
            self.controller.on_toolbar_group_disabled("visualization")

    def _set_measurement_tools_visible(self, visible: bool) -> None:
        self._measurement_tools_enabled = bool(visible)
        self._refresh_toolbar_action_state()
        if hasattr(self, "controller") and not visible:
            self.controller.on_toolbar_group_disabled("measurement")

    def _on_toolbar_action_triggered(self, action_label: str, checked: bool) -> None:
        if action_label == "Colour Relief":
            self._show_colour_relief_dropdown()
            return

        if action_label == "Swipe Comparator":
            action = self.toolbar_actions.get(action_label)
            if action is None:
                return
            if checked:
                self._show_swipe_comparator_dropdown()
                return
            final_state = self.controller.handle_toolbar_action(action_label, checked=checked)
            if isinstance(final_state, bool):
                action.setChecked(final_state)
            if not bool(final_state):
                self.comparator_overlay.clear_overlay()
            return

        final_state = self.controller.handle_toolbar_action(action_label, checked=checked)
        action = self.toolbar_actions.get(action_label)
        if action is None or not action.isCheckable():
            return
        if isinstance(final_state, bool):
            action.setChecked(final_state)

        interaction_toggles = {
            "Pan",
            "Distance / Azimuth",
            "Add Point",
            "Add Polygon",
            "Shadow Height",
        }
        if action_label in interaction_toggles and bool(final_state):
            for other_label in interaction_toggles:
                if other_label == action_label:
                    continue
                other_action = self.toolbar_actions.get(other_label)
                if other_action is not None and other_action.isCheckable() and other_action.isChecked():
                    other_action.setChecked(False)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if hasattr(self, "comparator_overlay"):
            self.comparator_overlay.setGeometry(self.web_view.rect())

    def eventFilter(self, watched, event) -> bool:  # type: ignore[override]
        if watched is self.web_view and hasattr(self, "comparator_overlay"):
            if event.type() in {QEvent.Type.Resize, QEvent.Type.Show}:
                self.comparator_overlay.setGeometry(self.web_view.rect())
                self.comparator_overlay.raise_()
        return super().eventFilter(watched, event)

    def _show_colour_relief_dropdown(self) -> None:
        if not self.controller._selected_dem_path():  # noqa: SLF001 - local UI guard
            self.panel.log("Colour relief requires a visible DEM layer.")
            return

        action = self.toolbar_actions.get("Colour Relief")
        if action is None:
            return
        anchor = self.main_toolbar.widgetForAction(action)
        if anchor is None:
            return

        menu = QMenu(self)
        menu.setStyleSheet(
            """
            QMenu {
                background: #f8fafc;
                border: 1px solid #c9d3df;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 14px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background: #e6eef8;
            }
            """
        )

        current_mode = self.controller.get_dem_color_mode()
        white_action = menu.addAction("White relief")
        color_action = menu.addAction("Color relief")
        white_action.setCheckable(True)
        color_action.setCheckable(True)
        white_action.setChecked(current_mode == "gray")
        color_action.setChecked(current_mode == "terrain")

        global_pos = anchor.mapToGlobal(anchor.rect().bottomLeft())
        selected = menu.exec(global_pos)
        if selected is None:
            return
        if selected == white_action:
            self.controller.set_dem_color_mode("gray", log_to_panel=True)
            return
        if selected == color_action:
            self.controller.set_dem_color_mode("terrain", log_to_panel=True)

    def _show_swipe_comparator_dropdown(self) -> None:
        action = self.toolbar_actions.get("Swipe Comparator")
        if action is None:
            return

        layers = self.controller.available_swipe_layer_options()
        if len(layers) < 2:
            self.panel.log("Swipe comparator needs at least two layers in current region.")
            action.setChecked(False)
            return

        anchor = self.main_toolbar.widgetForAction(action)
        if anchor is None:
            action.setChecked(False)
            return

        popup = QDialog(self, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        popup.setObjectName("swipeComparatorDropdown")
        popup.setStyleSheet(
            """
            QDialog#swipeComparatorDropdown {
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

        title = QLabel("Swipe Comparator")
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
            item.setCheckState(Qt.CheckState.Checked if layer["visible"] else Qt.CheckState.Unchecked)
        layout.addWidget(layer_list)

        info_label = QLabel("Select up to 4 layers.")
        layout.addWidget(info_label)

        apply_button = QPushButton("Apply")
        layout.addWidget(apply_button)
        applied = {"done": False}

        def enforce_max_selection(changed_item: QListWidgetItem) -> None:
            checked_items = [
                layer_list.item(i)
                for i in range(layer_list.count())
                if layer_list.item(i).checkState() == Qt.CheckState.Checked
            ]
            if len(checked_items) <= 4:
                info_label.setText("Select up to 4 layers.")
                return
            changed_item.setCheckState(Qt.CheckState.Unchecked)
            info_label.setText("Maximum 4 layers are allowed.")

        layer_list.itemChanged.connect(enforce_max_selection)

        def apply_selection() -> None:
            selected_paths: list[str] = []
            selected_labels: list[str] = []
            for i in range(layer_list.count()):
                item = layer_list.item(i)
                if item.checkState() != Qt.CheckState.Checked:
                    continue
                selected_paths.append(str(item.data(Qt.ItemDataRole.UserRole) or ""))
                selected_labels.append(item.text())

            selected_paths = [path for path in selected_paths if path]
            if len(selected_paths) < 2:
                self.panel.log("Select at least two layers for swipe comparator.")
                action.setChecked(False)
                popup.close()
                return

            pane_count = int(layout_combo.currentData())
            if len(selected_paths) < pane_count:
                self.panel.log(f"Select at least {pane_count} layers for selected layout.")
                return

            success = self.controller.apply_swipe_comparator_selection(selected_paths)
            if success:
                action.setChecked(True)
                applied["done"] = True
            else:
                self.comparator_overlay.clear_overlay()
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
        if not action.isChecked():
            self.comparator_overlay.clear_overlay()

    def set_toolbar_layer_context(self, context: str) -> None:
        normalized = str(context or "none").lower()
        if normalized not in {"none", "imagery", "dem", "mixed"}:
            normalized = "none"
        self._toolbar_layer_context = normalized
        self._refresh_toolbar_action_state()

    def _refresh_toolbar_action_state(self) -> None:
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
                if self._toolbar_layer_context == "imagery" and label in self.DEM_ONLY_ACTIONS:
                    action.setVisible(False)
                    if action.isCheckable():
                        action.setChecked(False)
                    continue
                if self._toolbar_layer_context == "dem" and label in self.IMAGERY_ONLY_ACTIONS:
                    action.setVisible(False)
                    if action.isCheckable():
                        action.setChecked(False)
                    continue

            action.setVisible(True)

            if group in {"visualization", "measurement"} and self._toolbar_layer_context == "none":
                action.setEnabled(False)
                if action.isCheckable():
                    action.setChecked(False)
            else:
                action.setEnabled(True)

            if label == "Swipe Comparator" and hasattr(self, "controller"):
                swipe_available = self.controller.can_attempt_enable_swipe_comparator()
                if not swipe_available:
                    action.setEnabled(False)
                    if action.isCheckable():
                        action.setChecked(False)

    def _toolbar_icon(self, tool_name: str, fallback: QStyle.StandardPixmap) -> QIcon:
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
        if app_mode == DesktopAppMode.SERVER:
            return "Offline GIS Server Desktop"
        if app_mode == DesktopAppMode.CLIENT:
            return "Offline GIS Client Desktop"
        return "Offline 3D GIS Desktop"
