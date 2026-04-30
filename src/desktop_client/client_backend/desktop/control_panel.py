from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from qtpy.QtCore import Qt, Signal, QTimer
from qtpy.QtGui import QColor
from qtpy.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QFormLayout,
    QGraphicsDropShadowEffect,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QProgressBar,
    QProgressDialog,
    QSlider,
    QStyle,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolBox,
    QVBoxLayout,
    QWidget,
)

from desktop_client.client_backend.desktop.app_mode import DesktopAppMode

if TYPE_CHECKING:
    from desktop_client.client_backend.desktop.api_client import DesktopApiClient


class ClientCollapsibleSection(QFrame):
    """Client-only collapsible section wrapper with a full-width header."""

    class _HeaderBar(QFrame):
        """Clickable header with title on left and arrow on right."""

        toggled = Signal(bool)

        def __init__(self, title: str, expanded: bool, parent: QWidget | None = None):
            super().__init__(parent)
            self.setObjectName("clientCollapseHeader")
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self._expanded = expanded

            self._title_label = QLabel(title, self)
            self._title_label.setObjectName("clientCollapseTitle")
            self._title_label.setCursor(Qt.CursorShape.PointingHandCursor)

            self._arrow_label = QLabel(self)
            self._arrow_label.setObjectName("clientCollapseArrow")
            self._arrow_label.setCursor(Qt.CursorShape.PointingHandCursor)
            self._arrow_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._arrow_label.setFixedSize(16, 16)

            layout = QHBoxLayout(self)
            layout.setContentsMargins(10, 6, 10, 6)
            layout.setSpacing(8)
            layout.addWidget(self._title_label, 1)
            layout.addWidget(self._arrow_label, 0)

            self.setMinimumHeight(34)
            self._apply_state()

        def set_expanded(self, expanded: bool) -> None:
            self._expanded = expanded
            self._apply_state()

        def _apply_state(self) -> None:
            arrow_icon = self.style().standardIcon(
                QStyle.StandardPixmap.SP_ArrowDown
                if self._expanded
                else QStyle.StandardPixmap.SP_ArrowRight
            )
            self._arrow_label.setPixmap(arrow_icon.pixmap(14, 14))

        def mousePressEvent(self, event) -> None:  # type: ignore[override]
            if event.button() == Qt.MouseButton.LeftButton:
                self._expanded = not self._expanded
                self._apply_state()
                self.toggled.emit(self._expanded)
                event.accept()
                return
            super().mousePressEvent(event)

    def __init__(
        self,
        title: str,
        content: QWidget,
        expanded: bool = True,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("clientCollapseSection")
        self._content = content
        self._expanded = expanded

        self._header = self._HeaderBar(title, expanded, self)
        self._header.toggled.connect(self._on_toggled)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._header)
        layout.addWidget(self._content)

        self._apply_shadow()
        self._apply_state(expanded)

    def _apply_shadow(self) -> None:
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(3.0)
        shadow.setOffset(0.0, 1.0)
        shadow.setColor(QColor(0, 0, 0, 28))
        self.setGraphicsEffect(shadow)

    def _apply_state(self, expanded: bool) -> None:
        self._expanded = expanded
        self._header.set_expanded(expanded)
        self._content.setVisible(expanded)

    def set_expanded(self, expanded: bool) -> None:
        self._apply_state(expanded)

    def _on_toggled(self, checked: bool) -> None:
        self._apply_state(checked)


class ControlPanel(QWidget):
    """Desktop control panel widgets for ingest, search, display, and measurement tools."""

    search_result_visibility_toggled = Signal(str, bool)
    search_layers_reordered = Signal(list)  # Signal for drag-and-drop layer reordering
    visualization_tools_toggled = Signal(bool)
    measurement_tools_toggled = Signal(bool)
    measurement_result_clear_selected_requested = Signal()
    measurement_result_clear_all_requested = Signal()
    uploaded_assets_refresh_requested = Signal()  # Signal to request controller cache clearing

    def __init__(
        self,
        parent: QWidget | None = None,
        app_mode: DesktopAppMode = DesktopAppMode.UNIFIED,
        api_client: DesktopApiClient | None = None,
    ):
        super().__init__(parent)
        self.api_client = api_client
        self.setMinimumWidth(380)
        
        # Drag-and-drop reordering debounce timer
        self._reorder_debounce_timer = QTimer(self)
        self._reorder_debounce_timer.setSingleShot(True)
        self._reorder_debounce_timer.timeout.connect(self._process_pending_reorder)
        self._pending_reorder_data = None
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        self.sections = QToolBox(self)
        self.sections.setObjectName("controlSections")
        self.sections.setMinimumWidth(360)

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(
            "Select folder containing rasters (GeoTIFF / JP2 / MBTiles / DEM)..."
        )
        self.browse_btn = QPushButton("Browse Folder")
        self.ingest_btn = QPushButton("Ingest Folder")

        self.browse_btn.setToolTip("Select folder containing rasters from local disk or secure LAN mount.")
        self.ingest_btn.setToolTip(
            "Queue folder for ingestion with automatic processing, transformation, and tiling."
        )

        self.upload_box = QGroupBox("Ingest")
        upload_layout = QVBoxLayout(self.upload_box)
        upload_layout.addWidget(self.path_edit)
        row = QHBoxLayout()
        row.addWidget(self.browse_btn, 1)
        row.addWidget(self.ingest_btn, 1)
        upload_layout.addLayout(row)

        self.ingest_progress_bar = QProgressBar()
        self.ingest_progress_bar.setRange(0, 100)
        self.ingest_progress_bar.setValue(0)
        self.ingest_progress_bar.setFormat("%p%")
        self.ingest_status_value = QLabel("Idle")
        self.ingest_step_value = QLabel("No active ingest")
        self.ingest_counts_value = QLabel("Processed: 0/0 | Failed: 0")
        self.ingest_elapsed_value = QLabel("Elapsed: 00:00")
        self.ingest_item_value = QLabel("Current: -")
        self.ingest_details = QTextEdit()
        self.ingest_details.setReadOnly(True)
        self.ingest_details.setMaximumHeight(100)
        self.ingest_details.setStyleSheet("""
            QTextEdit { 
                background: #fafafa; 
                border: 1px solid #e0e0e0; 
                border-radius: 2px; 
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 11px;
                padding: 4px;
            }
        """)

        # Uploaded Assets table (numbered metadata view)
        self.uploaded_assets_list = QTableWidget(0, 7)
        self.uploaded_assets_list.setMaximumHeight(200)
        self.uploaded_assets_list.setHorizontalHeaderLabels(
            ["#", "File Name", "Type", "CRS", "Cell Size", "Dimensions", "Added"]
        )
        self.uploaded_assets_list.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.uploaded_assets_list.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self.uploaded_assets_list.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents
        )
        self.uploaded_assets_list.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeToContents
        )
        self.uploaded_assets_list.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeToContents
        )
        self.uploaded_assets_list.horizontalHeader().setSectionResizeMode(
            5, QHeaderView.ResizeToContents
        )
        self.uploaded_assets_list.horizontalHeader().setSectionResizeMode(
            6, QHeaderView.ResizeToContents
        )
        # Configure column widths for better display and enable horizontal scrolling
        self.uploaded_assets_list.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.uploaded_assets_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # Set minimum column widths to ensure content is visible
        self.uploaded_assets_list.setColumnWidth(0, 40)   # Row number
        self.uploaded_assets_list.setColumnWidth(1, 350)  # File Name (increased for full visibility)
        self.uploaded_assets_list.setColumnWidth(2, 100)  # Type (increased)
        self.uploaded_assets_list.setColumnWidth(3, 120)  # CRS (increased)
        self.uploaded_assets_list.setColumnWidth(4, 120)  # Cell Size (increased)
        self.uploaded_assets_list.setColumnWidth(5, 120)  # Dimensions (increased)
        self.uploaded_assets_list.setColumnWidth(6, 140)  # Added (increased)
        
        # Allow columns to be resized by user
        header = self.uploaded_assets_list.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)  # Don't stretch last column
        
        # Set minimum section size to prevent columns from becoming too narrow
        header.setMinimumSectionSize(60)
        self.uploaded_assets_list.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.uploaded_assets_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.uploaded_assets_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.uploaded_assets_list.setStyleSheet("""
            QTableWidget { background: #ffffff; border: 1px solid #d0d0d0; border-radius: 3px; gridline-color: #f0f0f0; }
            QTableWidget::item { padding: 2px; }
            QTableWidget::item:selected { background: #e8f4ff; }
            QHeaderView::section { background: #f5f5f5; padding: 2px; border: none; border-right: 1px solid #d0d0d0; }
        """)

        self.assets_refresh_btn = QPushButton("Refresh Catalog")
        self.assets_refresh_btn.setToolTip("Refresh the list of uploaded assets and clear all caches.")

        self.uploaded_box = QGroupBox("Uploaded Assets")
        uploaded_layout = QVBoxLayout(self.uploaded_box)
        uploaded_layout.addWidget(self.uploaded_assets_list, 1)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self.assets_refresh_btn)
        uploaded_layout.addLayout(btn_row)

        self.ingest_progress_box = QGroupBox("Progress")
        ingest_progress_layout = QFormLayout(self.ingest_progress_box)
        ingest_progress_layout.setSpacing(6)
        ingest_progress_layout.setContentsMargins(10, 10, 10, 10)
        ingest_progress_layout.addRow("Overall:", self.ingest_progress_bar)
        ingest_progress_layout.addRow("Status:", self.ingest_status_value)
        ingest_progress_layout.addRow("Stage:", self.ingest_step_value)
        ingest_progress_layout.addRow("Items:", self.ingest_counts_value)
        ingest_progress_layout.addRow("Elapsed:", self.ingest_elapsed_value)
        ingest_progress_layout.addRow("Current:", self.ingest_item_value)
        ingest_progress_layout.addRow("Activity:", self.ingest_details)

        self.assets_combo = QComboBox()
        self.refresh_assets_btn = QPushButton("Refresh")
        self.add_layer_btn = QPushButton("Load Selected")

        self.assets_combo.setToolTip(
            "Catalog entries are metadata records. Raw data stays on storage."
        )
        self.add_layer_btn.setToolTip("Render selected raster as imagery overlay.")
        self.refresh_assets_btn.setToolTip("Refresh asset list from catalog.")

        self.layer_load_status = QLabel("Status: idle")
        self.layer_load_progress = QProgressBar()
        self.layer_load_progress.setRange(0, 100)
        self.layer_load_progress.setValue(0)
        self.layer_load_progress.setVisible(False)

        self.assets_box = QGroupBox("Available Assets")
        assets_layout = QVBoxLayout(self.assets_box)
        assets_layout.setSpacing(12)
        assets_layout.setContentsMargins(10, 10, 10, 10)
        assets_layout.addWidget(self.assets_combo)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addWidget(self.refresh_assets_btn)
        btn_row.addWidget(self.add_layer_btn)
        assets_layout.addLayout(btn_row)

        assets_layout.addWidget(self.layer_load_status)
        assets_layout.addWidget(self.layer_load_progress)
        assets_layout.addStretch()

        self.search_coord_lon = QDoubleSpinBox()
        self.search_coord_lon.setRange(-180.0, 180.0)
        self.search_coord_lon.setDecimals(6)
        self.search_coord_lon.setSingleStep(0.0001)
        self.search_coord_lat = QDoubleSpinBox()
        self.search_coord_lat.setRange(-90.0, 90.0)
        self.search_coord_lat.setDecimals(6)
        self.search_coord_lat.setSingleStep(0.0001)
        self.search_point_btn = QPushButton("Coordinate Search")
        self.search_point_btn.setToolTip(
            "Search around lon/lat using the configured buffer radius in meters."
        )

        for box in (
            self.search_coord_lon,
            self.search_coord_lat,
        ):
            box.setMinimumWidth(120)
            box.setMaximumWidth(145)

        self.search_buffer_m = QSpinBox()
        self.search_buffer_m.setRange(0, 50000)
        self.search_buffer_m.setValue(250)
        self.search_buffer_m.setMaximumWidth(145)
        self.search_draw_polygon_btn = QPushButton("Draw")
        self.search_draw_polygon_btn.setCheckable(True)
        self.search_finish_polygon_btn = QPushButton("Finish")
        self.search_clear_geometry_btn = QPushButton("Clear")
        self.search_from_draw_btn = QPushButton("Search")
        self.search_draw_polygon_btn.setToolTip("Start polygon drawing on the map.")
        self.search_finish_polygon_btn.setToolTip("Complete the active polygon.")
        self.search_clear_geometry_btn.setToolTip(
            "Clear the current polygon from the map."
        )
        self.search_from_draw_btn.setToolTip(
            "Search catalog assets overlapping the drawn polygon."
        )
        self.search_point_btn.setObjectName("searchPrimaryButton")
        self.search_from_draw_btn.setObjectName("searchPrimaryButton")
        for button in (
            self.search_point_btn,
            self.search_draw_polygon_btn,
            self.search_finish_polygon_btn,
            self.search_clear_geometry_btn,
            self.search_from_draw_btn,
        ):
            button.setMinimumHeight(24)
            button.setMaximumHeight(28)
        for button in (
            self.search_draw_polygon_btn,
            self.search_finish_polygon_btn,
            self.search_clear_geometry_btn,
            self.search_from_draw_btn,
        ):
            button.setMinimumWidth(80)
            button.setMaximumWidth(96)

        self.search_box = QGroupBox("Search Catalog")
        search_layout = QVBoxLayout(self.search_box)
        search_layout.setSpacing(8)
        search_layout.setContentsMargins(8, 8, 8, 8)

        # Point search
        point_label = QLabel("<b>Point Search</b>")
        search_layout.addWidget(point_label)
        coord_row = QHBoxLayout()
        coord_row.setSpacing(6)
        coord_row.addWidget(QLabel("Lon:"))
        coord_row.addWidget(self.search_coord_lon, 1)
        coord_row.addWidget(QLabel("Lat:"))
        coord_row.addWidget(self.search_coord_lat, 1)
        search_layout.addLayout(coord_row)
        point_buffer_row = QHBoxLayout()
        point_buffer_row.setSpacing(6)
        point_buffer_row.addWidget(QLabel("Buffer (m):"))
        point_buffer_row.addWidget(self.search_buffer_m)
        point_buffer_row.addStretch()
        search_layout.addLayout(point_buffer_row)
        point_actions_row = QHBoxLayout()
        point_actions_row.setSpacing(6)
        point_actions_row.addWidget(self.search_point_btn)
        point_actions_row.addStretch()
        search_layout.addLayout(point_actions_row)

        search_layout.addSpacing(6)

        # Draw search
        draw_label = QLabel("<b>Polygon Search</b>")
        search_layout.addWidget(draw_label)
        draw_actions_row = QHBoxLayout()
        draw_actions_row.setSpacing(4)
        draw_actions_row.addWidget(self.search_draw_polygon_btn)
        draw_actions_row.addWidget(self.search_finish_polygon_btn)
        draw_actions_row.addWidget(self.search_clear_geometry_btn)
        draw_actions_row.addWidget(self.search_from_draw_btn)
        draw_actions_row.addStretch()
        search_layout.addLayout(draw_actions_row)

        search_layout.addSpacing(8)
        search_layout.addWidget(QLabel("<b>Search Results</b>"))
        self.search_results_summary = QLabel(
            "Matches: 0 | DEM: 0 | Imagery: 0 | CRS: - | Latest: -"
        )
        self.search_results_summary.setStyleSheet("font-weight: 600; color: #2a2a2a;")
        search_layout.addWidget(self.search_results_summary)

        self.search_results_table = QTableWidget(0, 6)  # Added one more column for drag handle
        self.search_results_table.setHorizontalHeaderLabels(
            ["⋮⋮", "File", "Kind", "CRS", "Added", "View"]  # Added drag handle column
        )
        
        # Configure drag and drop for layer reordering
        self.search_results_table.setDragDropMode(QAbstractItemView.InternalMove)
        self.search_results_table.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.search_results_table.setDragDropOverwriteMode(False)
        self.search_results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        
        # Enable drag indicator and ensure text visibility during drag
        self.search_results_table.setDragEnabled(True)
        self.search_results_table.setAcceptDrops(True)
        
        # Set column widths for drag handle
        self.search_results_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents  # Drag handle column
        )
        self.search_results_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch  # File name
        )
        self.search_results_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents  # Kind
        )
        self.search_results_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeToContents  # CRS
        )
        self.search_results_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeToContents  # Added
        )
        self.search_results_table.horizontalHeader().setSectionResizeMode(
            5, QHeaderView.ResizeToContents  # View
        )
        
        # Set specific column widths
        self.search_results_table.setColumnWidth(0, 30)   # Drag handle
        self.search_results_table.setColumnWidth(1, 220)  # File name
        self.search_results_table.setColumnWidth(2, 78)   # Kind
        self.search_results_table.setColumnWidth(3, 96)   # CRS
        self.search_results_table.setColumnWidth(4, 120)  # Added
        self.search_results_table.setColumnWidth(5, 60)   # View
        self.search_results_table.verticalHeader().setVisible(False)
        self.search_results_table.verticalHeader().setDefaultSectionSize(22)
        self.search_results_table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.search_results_table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.search_results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.search_results_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.search_results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.search_results_table.setAlternatingRowColors(True)
        self.search_results_table.setWordWrap(False)
        self.search_results_table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.search_results_table.setStyleSheet(
            """
            QTableWidget {
                background: #ffffff;
                border: 1px solid #d0d0d0;
                border-radius: 3px;
                gridline-color: #f0f0f0;
                font-size: 11px;
            }
            QTableWidget::item:selected {
                background: #dcecff;
                color: #10233f;
            }
            QTableWidget::item:alternate {
                background: #fafafa;
            }
            QTableWidget::item { 
                padding: 2px; 
            }
            QTableWidget::item:first-child {
                text-align: center;
                color: #666666;
                font-weight: bold;
                background: #f8f8f8;
            }
            QTableWidget::item:first-child:hover {
                background: #e8e8e8;
                color: #333333;
            }
            QTableWidget::item:selected {
                background: #dcecff;
                color: #10233f;
            }
            QTableWidget::item:selected:first-child {
                background: #c8e0ff;
                color: #0a1a2f;
            }
            /* Enhanced drag-and-drop styling for better text visibility */
            QTableWidget::item:drag {
                background: #ffffff !important;
                color: #000000 !important;
                border: 2px solid #0066cc !important;
                opacity: 0.9 !important;
                font-weight: bold !important;
            }
            QTableWidget::item:drop {
                background: #e8f4ff !important;
                border: 2px dashed #0066cc !important;
                color: #000000 !important;
            }
            /* Ensure text remains visible during drag operations */
            QTableWidget QTableWidgetItem {
                color: #000000;
            }
            QTableWidget::item:drag QTableWidgetItem {
                color: #000000 !important;
                background: transparent !important;
            }
            QTableWidget QHeaderView::section {
                background: #f5f5f5;
                padding: 2px;
                border: none;
                border-right: 1px solid #d0d0d0;
                font-weight: 600;
                font-size: 11px;
            }
            QHeaderView::section:first {
                text-align: center;
                color: #888888;
            }
            """
        )
        self._set_search_results_table_visible_rows(5)
        search_layout.addWidget(self.search_results_table)
        
        # Connect drag-and-drop signals for real-time layer reordering
        self.search_results_table.model().rowsMoved.connect(self._on_search_results_reordered)

        search_layout.addStretch()

        self.brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setRange(0, 200)
        self.brightness_slider.setValue(100)
        self.brightness_value = QLabel()
        self.brightness_value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.brightness_value.setMinimumWidth(64)
        self.contrast_slider = QSlider(Qt.Orientation.Horizontal)
        self.contrast_slider.setRange(10, 300)
        self.contrast_slider.setValue(100)
        self.contrast_value = QLabel()
        self.contrast_value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.contrast_value.setMinimumWidth(64)
        self.pitch_slider = QSlider(Qt.Orientation.Horizontal)
        self.pitch_slider.setRange(-85, -10)
        self.pitch_slider.setValue(-45)
        self.pitch_value = QLabel()
        self.pitch_value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.pitch_value.setMinimumWidth(64)
        self.rotate_left_btn = QPushButton("Rotate Left")
        self.rotate_right_btn = QPushButton("Rotate Right")
        self.dem_exaggeration_slider = QSlider(Qt.Orientation.Horizontal)
        self.dem_exaggeration_slider.setRange(50, 800)
        self.dem_exaggeration_slider.setValue(150)
        self.dem_exaggeration_value = QLabel()
        self.dem_exaggeration_value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.dem_exaggeration_value.setMinimumWidth(64)
        self.dem_hillshade_slider = QSlider(Qt.Orientation.Horizontal)
        self.dem_hillshade_slider.setRange(0, 100)
        self.dem_hillshade_slider.setValue(75)
        self.dem_hillshade_value = QLabel()
        self.dem_hillshade_value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.dem_hillshade_value.setMinimumWidth(64)
        self.dem_color_mode_combo = QComboBox()
        self.dem_color_mode_combo.addItem("White relief", "gray")
        self.dem_color_mode_combo.addItem("Color relief", "terrain")
        self.dem_color_mode_combo.addItem("Slope map (deg)", "slope")
        self.dem_color_mode_combo.addItem("Aspect map (deg)", "aspect")
        self.dem_color_mode_combo.setCurrentIndex(0)
        self.rgb_view_mode_combo = QComboBox()
        self.rgb_view_mode_combo.addItem("3D Terrain Scene", "3d")
        self.rgb_view_mode_combo.addItem("2D Map View", "2d")
        self.rgb_view_mode_combo.setToolTip(
            "RGB can switch between an offline 3D terrain scene and a flat 2D map view."
        )
        self.apply_rgb_view_mode_btn = QPushButton("Apply View Mode")
        self.apply_rgb_view_mode_btn.setToolTip(
            "Switch the active raster between 3D terrain and 2D map views."
        )
        self.rgb_view_mode_combo.setVisible(False)
        self.apply_rgb_view_mode_btn.setVisible(False)

        self.view_box = QGroupBox("Display Settings")
        view_layout = QVBoxLayout(self.view_box)
        view_layout.setSpacing(14)
        view_layout.setContentsMargins(10, 10, 10, 10)

        # RGB Layer controls
        rgb_label = QLabel("<b>Imagery</b>")
        view_layout.addWidget(rgb_label)
        bright_layout = QHBoxLayout()
        bright_layout.addWidget(QLabel("Brightness:"))
        bright_layout.addWidget(self.brightness_slider, 1)
        bright_layout.addWidget(self.brightness_value)
        view_layout.addLayout(bright_layout)
        contrast_layout = QHBoxLayout()
        contrast_layout.addWidget(QLabel("Contrast:"))
        contrast_layout.addWidget(self.contrast_slider, 1)
        contrast_layout.addWidget(self.contrast_value)
        view_layout.addLayout(contrast_layout)

        view_layout.addSpacing(8)

        # Camera controls
        camera_label = QLabel("<b>Camera</b>")
        view_layout.addWidget(camera_label)
        pitch_layout = QHBoxLayout()
        pitch_layout.addWidget(QLabel("Pitch:"))
        pitch_layout.addWidget(self.pitch_slider, 1)
        pitch_layout.addWidget(self.pitch_value)
        view_layout.addLayout(pitch_layout)
        rotate_layout = QHBoxLayout()
        rotate_layout.setSpacing(8)
        rotate_layout.addWidget(self.rotate_left_btn, 1)
        rotate_layout.addWidget(self.rotate_right_btn, 1)
        view_layout.addLayout(rotate_layout)

        view_layout.addSpacing(8)

        # DEM-specific controls (initially hidden)
        dem_label = QLabel("<b>Terrain</b>")
        view_layout.addWidget(dem_label)
        exagg_layout = QHBoxLayout()
        exagg_layout.addWidget(QLabel("Exaggeration:"))
        exagg_layout.addWidget(self.dem_exaggeration_slider, 1)
        exagg_layout.addWidget(self.dem_exaggeration_value)
        view_layout.addLayout(exagg_layout)
        hillshade_layout = QHBoxLayout()
        hillshade_layout.addWidget(QLabel("Hillshade:"))
        hillshade_layout.addWidget(self.dem_hillshade_slider, 1)
        hillshade_layout.addWidget(self.dem_hillshade_value)
        view_layout.addLayout(hillshade_layout)
        dem_color_layout = QHBoxLayout()
        dem_color_layout.addWidget(QLabel("Style:"))
        dem_color_layout.addWidget(self.dem_color_mode_combo, 1)
        view_layout.addLayout(dem_color_layout)

        view_layout.addStretch()

        for slider in (
            self.brightness_slider,
            self.contrast_slider,
            self.pitch_slider,
            self.dem_exaggeration_slider,
            self.dem_hillshade_slider,
        ):
            slider.valueChanged.connect(self._update_display_value_labels)
        self._update_display_value_labels()

        self.click_label = QLabel("None")
        self.measure_label = QLabel("N/A")
        self.status_box = QTextEdit()
        self.status_box.setReadOnly(True)
        self.status_box.setMaximumHeight(120)

        self.log_box = QGroupBox("Activity Log")
        log_layout = QVBoxLayout(self.log_box)
        log_layout.setSpacing(8)
        log_layout.setContentsMargins(10, 10, 10, 10)
        click_row = QHBoxLayout()
        click_row.addWidget(QLabel("Last Click:"))
        click_row.addWidget(self.click_label, 1)
        log_layout.addLayout(click_row)
        measure_row = QHBoxLayout()
        measure_row.addWidget(QLabel("Distance:"))
        measure_row.addWidget(self.measure_label, 1)
        log_layout.addLayout(measure_row)
        log_layout.addWidget(QLabel("Messages:"))
        log_layout.addWidget(self.status_box, 1)

        self.measurement_results_box = QGroupBox("Measurement Results")
        measurement_results_layout = QVBoxLayout(self.measurement_results_box)
        measurement_results_layout.setSpacing(8)
        measurement_results_layout.setContentsMargins(10, 10, 10, 10)
        self.measurement_results_list = QListWidget()
        self.measurement_results_list.setSelectionMode(
            QAbstractItemView.SingleSelection
        )
        self.measurement_results_list.setMinimumHeight(96)
        self.measurement_results_list.setMaximumHeight(160)
        measurement_results_layout.addWidget(self.measurement_results_list)
        measurement_results_btn_row = QHBoxLayout()
        measurement_results_btn_row.setSpacing(8)
        self.clear_selected_measurement_btn = QPushButton("Clear Selected")
        self.clear_all_measurements_btn = QPushButton("Clear All")
        self.clear_selected_measurement_btn.clicked.connect(
            self.measurement_result_clear_selected_requested.emit
        )
        self.clear_all_measurements_btn.clicked.connect(
            self.measurement_result_clear_all_requested.emit
        )
        measurement_results_btn_row.addWidget(self.clear_selected_measurement_btn, 1)
        measurement_results_btn_row.addWidget(self.clear_all_measurements_btn, 1)
        measurement_results_layout.addLayout(measurement_results_btn_row)
        self.data_section = QWidget(self)
        data_layout = QVBoxLayout(self.data_section)
        data_layout.setContentsMargins(8, 8, 8, 8)
        data_layout.setSpacing(10)
        data_layout.addWidget(self.upload_box)
        data_layout.addWidget(self.ingest_progress_box)
        data_layout.addWidget(self.assets_box, 1)

        self.search_section = QWidget(self)
        search_section_layout = QVBoxLayout(self.search_section)
        search_section_layout.setContentsMargins(8, 8, 8, 8)
        search_section_layout.setSpacing(10)
        search_section_layout.addWidget(self.search_box)

        self.view_section = QWidget(self)
        view_section_layout = QVBoxLayout(self.view_section)
        view_section_layout.setContentsMargins(8, 8, 8, 8)
        view_section_layout.setSpacing(10)
        view_section_layout.addWidget(self.view_box)

        self.analysis_section = QWidget(self)
        analysis_layout = QVBoxLayout(self.analysis_section)
        analysis_layout.setContentsMargins(8, 8, 8, 8)
        analysis_layout.setSpacing(10)
        analysis_layout.addWidget(self.measurement_results_box)
        analysis_layout.addWidget(self.log_box, 1)

        self.sections.addItem(self.data_section, "Data")
        self.search_section_index = self.sections.addItem(self.search_section, "Search")
        self.sections.addItem(self.view_section, "Display")
        self.sections.addItem(self.analysis_section, "Analysis")

        self._client_section_specs: list[tuple[str, QGroupBox, bool]] = [
            ("Search", self.search_box, True),
            ("Display", self.view_box, False),
            ("Assets", self.assets_box, False),
            ("Activity Log", self.log_box, False),
        ]
        self._client_original_group_titles = {
            section: section.title()
            for _name, section, _expanded in self._client_section_specs
        }
        self._client_collapsible_sections: list[ClientCollapsibleSection] = []
        self._server_refresh_connected = False
        self._search_busy_dialog: QProgressDialog | None = None
        self._search_busy_timer: QTimer | None = None
        self._search_busy_start_time: float | None = None
        self._search_busy_message: str = "Searching..."
        self._search_busy_value: int = 0

        root.addWidget(self.sections, 1)
        self._apply_panel_styles()
        self._apply_widget_shadows()
        self.configure_for_mode(app_mode)

    def configure_for_mode(self, app_mode: DesktopAppMode) -> None:
        """Configure panel for server or client mode."""
        root_layout = self.layout()

        def _remove_widget(widget: QWidget) -> None:
            for i in range(root_layout.count()):
                item = root_layout.itemAt(i)
                if item is not None and item.widget() == widget:
                    root_layout.takeAt(i)
                    break

        for collapsible in self._client_collapsible_sections:
            collapsible.setVisible(False)
            _remove_widget(collapsible)

        if app_mode == DesktopAppMode.SERVER:
            # Server mode: show sections WITHOUT toolbox tabs
            self.sections.setVisible(False)
            self._set_client_group_title_visibility(visible=True)

            # Add server sections directly to main layout
            # Remove the toolbox before adding sections
            _remove_widget(self.sections)

            # Add server-specific sections directly
            root_layout.addWidget(self.upload_box)
            root_layout.addWidget(self.ingest_progress_box)
            root_layout.addWidget(self.uploaded_box, 1)
            root_layout.addStretch()

            # Connect refresh button to clear caches and refresh
            if not self._server_refresh_connected:
                self.assets_refresh_btn.clicked.connect(self._on_refresh_catalog_clicked)
                self._server_refresh_connected = True
            # Show loading state initially - will be populated by controller
            self.uploaded_assets_list.setRowCount(1)
            self.uploaded_assets_list.setItem(0, 0, QTableWidgetItem("Loading..."))

            # Hide client-only sections
            self.search_box.setVisible(False)
            self.view_box.setVisible(False)
            self.log_box.setVisible(False)
            self.assets_box.setVisible(False)

        elif app_mode == DesktopAppMode.CLIENT:
            # Client mode: use the same stacked section style as server mode.
            self.sections.setVisible(False)
            _remove_widget(self.sections)
            self._set_client_group_title_visibility(visible=False)
            self._ensure_client_collapsible_sections()

            self.upload_box.setVisible(False)
            self.ingest_progress_box.setVisible(False)
            self.uploaded_box.setVisible(False)

            self.assets_box.setVisible(True)
            self.search_box.setVisible(True)
            self.view_box.setVisible(True)
            self.log_box.setVisible(True)

            for collapsible, (_name, _section, expanded) in zip(
                self._client_collapsible_sections,
                self._client_section_specs,
            ):
                collapsible.set_expanded(expanded)
                collapsible.setVisible(True)
                root_layout.addWidget(collapsible)
            root_layout.addStretch()

        else:
            # Unified mode: keep tabbed workflow.
            self._set_client_group_title_visibility(visible=True)
            if root_layout.indexOf(self.sections) == -1:
                root_layout.addWidget(self.sections, 1)
            self.sections.setVisible(True)
            self.upload_box.setVisible(False)
            self.ingest_progress_box.setVisible(False)
            self.uploaded_box.setVisible(False)
            self.search_box.setVisible(True)
            self.view_box.setVisible(True)
            self.log_box.setVisible(True)
            self.assets_box.setVisible(True)
            self.sections.setCurrentIndex(self.search_section_index)

    def _ensure_client_collapsible_sections(self) -> None:
        if self._client_collapsible_sections:
            return
        for name, section_widget, expanded in self._client_section_specs:
            collapsible = ClientCollapsibleSection(
                name, section_widget, expanded=expanded, parent=self
            )
            self._client_collapsible_sections.append(collapsible)

    def _set_client_group_title_visibility(self, visible: bool) -> None:
        for _name, section_widget, _expanded in self._client_section_specs:
            original_title = self._client_original_group_titles.get(section_widget, "")
            section_widget.setTitle(original_title if visible else "")
            section_widget.setFlat(not visible)

    def update_search_results(
        self, assets: list[dict], visibility_by_path: dict[str, bool] | None = None
    ) -> None:
        self.search_results_table.setRowCount(0)
        self.search_results_table.setSortingEnabled(False)
        visibility_map = visibility_by_path or {}

        sorted_assets = sorted(
            assets,
            key=lambda item: self._search_created_at_sort_key(item.get("created_at")),
            reverse=True,
        )

        total_matches = len(sorted_assets)
        dem_count = sum(
            1
            for asset in sorted_assets
            if str(asset.get("kind") or "").lower() == "dem"
        )
        imagery_count = max(0, total_matches - dem_count)
        visible_count = sum(
            1
            for asset in sorted_assets
            if visibility_map.get(str(asset.get("file_path") or ""), True)
        )
        crs_values = sorted(
            {
                str(asset.get("crs") or "-")
                for asset in sorted_assets
                if str(asset.get("crs") or "-") != "-"
            }
        )
        if len(crs_values) > 2:
            crs_summary = ", ".join(crs_values[:2]) + f" (+{len(crs_values) - 2} more)"
        else:
            crs_summary = ", ".join(crs_values) if crs_values else "-"
        latest_date = (
            self._format_search_created_at(sorted_assets[0].get("created_at"))
            if sorted_assets
            else "-"
        )
        self.search_results_summary.setText(
            f"Matches: {total_matches} | DEM: {dem_count} | Imagery: {imagery_count} | Visible: {visible_count} | CRS: {crs_summary} | Latest: {latest_date}"
        )

        for asset in sorted_assets:
            row = self.search_results_table.rowCount()
            self.search_results_table.insertRow(row)

            file_name = str(asset.get("file_name") or "-")
            kind = str(asset.get("kind") or "-").upper()
            crs = str(asset.get("crs") or "-")
            created_at = self._format_search_created_at(asset.get("created_at"))
            file_path = str(asset.get("file_path") or "")
            is_visible = visibility_map.get(file_path, True)
            toggle_button = QPushButton("●" if is_visible else "○")
            toggle_button.setObjectName("searchVisibilityToggle")
            toggle_button.setToolTip("Hide from map" if is_visible else "Show on map")
            toggle_button.setFixedSize(28, 22)
            if not file_path:
                toggle_button.setEnabled(False)
            else:
                toggle_button.clicked.connect(
                    lambda _checked=False, path=file_path, visible=is_visible: (
                        self.search_result_visibility_toggled.emit(path, not visible)
                    )
                )

            # Add drag handle in first column
            drag_handle_item = QTableWidgetItem("⋮⋮")
            drag_handle_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            drag_handle_item.setToolTip(f"Drag to reorder (Layer {row + 1})")
            drag_handle_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            
            self.search_results_table.setItem(row, 0, drag_handle_item)
            self.search_results_table.setItem(row, 1, QTableWidgetItem(file_name))
            self.search_results_table.setItem(row, 2, QTableWidgetItem(kind))
            self.search_results_table.setItem(row, 3, QTableWidgetItem(crs))
            self.search_results_table.setItem(row, 4, QTableWidgetItem(created_at))
            self.search_results_table.setCellWidget(row, 5, toggle_button)

        self.search_results_table.setSortingEnabled(True)

    def _set_search_results_table_visible_rows(self, visible_rows: int) -> None:
        header_height = self.search_results_table.horizontalHeader().sizeHint().height()
        row_height = self.search_results_table.verticalHeader().defaultSectionSize()
        frame_height = self.search_results_table.frameWidth() * 2
        total_height = (
            header_height + (row_height * max(1, visible_rows)) + frame_height
        )
        self.search_results_table.setMinimumHeight(total_height)
        self.search_results_table.setMaximumHeight(total_height)

    @staticmethod
    def _format_search_created_at(value: object) -> str:
        if value is None:
            return "-"
        try:
            if isinstance(value, str):
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed.strftime("%d-%b-%Y")
            if isinstance(value, datetime):
                return value.strftime("%d-%b-%Y")
        except Exception:
            return str(value)
        return str(value)

    @staticmethod
    def _parse_search_created_at(value: object) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except Exception:
                return None
        return None

    @staticmethod
    def _search_created_at_sort_key(value: object) -> float:
        parsed = ControlPanel._parse_search_created_at(value)
        if parsed is None:
            return 0.0
        try:
            return parsed.timestamp()
        except Exception:
            return 0.0

    @staticmethod
    def _format_asset_created_at(value: object) -> str:
        formatted = ControlPanel._format_search_created_at(value)
        return formatted

    @staticmethod
    def _format_asset_cell_size(resolution_x: object, resolution_y: object) -> str:
        try:
            x_value = float(resolution_x)
            y_value = float(resolution_y)
        except (TypeError, ValueError):
            return "-"
        return f"{x_value:.4f} × {y_value:.4f}"

    @staticmethod
    def _format_asset_dimensions(width: object, height: object) -> str:
        try:
            width_value = int(width)
            height_value = int(height)
        except (TypeError, ValueError):
            return "-"
        return f"{width_value:,} × {height_value:,}"

    @staticmethod
    def _summarize_asset_location(value: object) -> tuple[str, str]:
        raw_path = str(value or "-")
        if raw_path == "-":
            return "-", "-"
        normalized = raw_path.replace("\\", "/")
        parts = [part for part in normalized.split("/") if part]
        if len(parts) >= 2:
            return f"{parts[-2]}/{parts[-1]}", raw_path
        if parts:
            return parts[-1], raw_path
        return raw_path, raw_path

    def _update_display_value_labels(self, _value: int | None = None) -> None:
        brightness_scale = self.brightness_slider.value() / 100.0
        contrast_scale = self.contrast_slider.value() / 100.0
        pitch_degrees = int(self.pitch_slider.value())
        exaggeration_scale = self.dem_exaggeration_slider.value() / 100.0
        hillshade_percent = int(self.dem_hillshade_slider.value())

        self.brightness_value.setText(f"{brightness_scale:.2f}x")
        self.contrast_value.setText(f"{contrast_scale:.2f}x")
        self.pitch_value.setText(f"{pitch_degrees} deg")
        self.dem_exaggeration_value.setText(f"{exaggeration_scale:.2f}x")
        self.dem_hillshade_value.setText(f"{hillshade_percent}%")

    def log(self, message: str) -> None:
        self.status_box.append(message)

    def add_measurement_result_entry(self, message: str) -> None:
        item = QListWidgetItem(message)
        self.measurement_results_list.addItem(item)
        self.measurement_results_list.setCurrentItem(item)
        self.measurement_results_list.scrollToItem(item)

    def selected_measurement_result_row(self) -> int:
        return int(self.measurement_results_list.currentRow())

    def remove_measurement_result_row(self, row: int) -> None:
        if 0 <= row < self.measurement_results_list.count():
            self.measurement_results_list.takeItem(row)

    def clear_measurement_result_entries(self) -> None:
        self.measurement_results_list.clear()

    def set_search_busy(
        self, active: bool, message: str = "Searching...", progress: int | None = None
    ) -> None:
        if active:
            if self._search_busy_dialog is None:
                import time

                parent_widget = (
                    self.window() if isinstance(self.window(), QWidget) else self
                )
                dialog = QProgressDialog(message, "", 0, 100, parent_widget)
                dialog.setWindowTitle("Please wait")
                dialog.setCancelButton(None)
                dialog.setMinimumDuration(0)
                dialog.setAutoClose(False)
                dialog.setAutoReset(False)
                dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
                dialog.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
                dialog.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
                dialog.setStyleSheet(
                    """
                    QProgressDialog {
                        background: #ffffff;
                        border: 1px solid #d0d0d0;
                        border-radius: 6px;
                    }
                    QProgressDialog QLabel {
                        color: #1a1a1a;
                        font-weight: 600;
                        font-size: 13px;
                    }
                    """
                )
                self._search_busy_dialog = dialog
                self._search_busy_start_time = time.time()
                self._search_busy_value = 5
                if self._search_busy_timer is None:
                    self._search_busy_timer = QTimer(self)
                    self._search_busy_timer.timeout.connect(
                        self._update_search_busy_timer
                    )
                self._search_busy_timer.start(100)

            dialog = self._search_busy_dialog
            if dialog is None:
                return
            self._search_busy_message = str(message or "Searching...")
            if progress is not None:
                self._search_busy_value = max(1, min(100, int(progress)))
            elif self._search_busy_value <= 0:
                self._search_busy_value = 5
            dialog.setValue(self._search_busy_value)
            if self._search_busy_start_time is not None:
                import time

                elapsed = time.time() - self._search_busy_start_time
                dialog.setLabelText(f"{self._search_busy_message} {elapsed:.1f}s")
            else:
                dialog.setLabelText(self._search_busy_message)
            dialog.show()
            self._center_search_busy_dialog()
            QApplication.processEvents()
            return

        if self._search_busy_dialog is not None:
            if self._search_busy_timer is not None:
                self._search_busy_timer.stop()
            self._search_busy_dialog.setValue(100)
            self._search_busy_dialog.hide()
            self._search_busy_dialog.reset()
            self._search_busy_start_time = None
            self._search_busy_message = "Searching..."
            self._search_busy_value = 0
            QApplication.processEvents()

    def _update_search_busy_timer(self) -> None:
        if self._search_busy_dialog is None or self._search_busy_start_time is None:
            return
        import time

        elapsed = time.time() - self._search_busy_start_time
        # Keep a visibly moving bar while backend search is running.
        self._search_busy_value = min(94, max(self._search_busy_value + 1, 5))
        self._search_busy_dialog.setValue(self._search_busy_value)
        self._search_busy_dialog.setLabelText(
            f"{self._search_busy_message} {elapsed:.1f}s"
        )

    def _center_search_busy_dialog(self) -> None:
        if self._search_busy_dialog is None:
            return
        parent_widget = self.window() if isinstance(self.window(), QWidget) else self
        if parent_widget is None:
            return
        parent_rect = parent_widget.frameGeometry()
        dialog_rect = self._search_busy_dialog.frameGeometry()
        target_x = parent_rect.center().x() - dialog_rect.width() // 2
        target_y = parent_rect.center().y() - dialog_rect.height() // 2
        self._search_busy_dialog.move(max(0, target_x), max(0, target_y))

    def append_ingest_detail(self, message: str) -> None:
        self.ingest_details.append(message)

    def refresh_uploaded_assets(self) -> None:
        """Fetch and display list of uploaded assets from the catalog."""
        # Clear caches first, but don't emit the signal to prevent infinite loop
        if hasattr(self, '_refreshing_assets') and self._refreshing_assets:
            return  # Prevent recursive calls
        
        self._refreshing_assets = True
        
        try:
            # Force a complete table reset to ensure no cached data persists
            self.uploaded_assets_list.clear()
            self.uploaded_assets_list.setRowCount(0)
            self.uploaded_assets_list.setColumnCount(7)
            self.uploaded_assets_list.setHorizontalHeaderLabels(
                ["#", "File Name", "Type", "CRS", "Cell Size", "Dimensions", "Added"]
            )
            
            # Force a complete widget refresh (only if model is accessible)
            self.uploaded_assets_list.clearContents()
            try:
                self.uploaded_assets_list.model().beginResetModel()
                self.uploaded_assets_list.model().endResetModel()
            except RuntimeError:
                # Model not accessible (e.g., in test environment), skip model reset
                pass
            
            # Ensure header text is visible and properly formatted
            header = self.uploaded_assets_list.horizontalHeader()
            header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            header.setStretchLastSection(False)
            header.setMinimumSectionSize(60)
            
            if not self.api_client:
                self.uploaded_assets_list.setRowCount(1)
                # Show waiting message in File Name column
                waiting_item = QTableWidgetItem("Waiting for API...")
                waiting_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                waiting_item.setForeground(QColor("#666666"))  # Gray text
                self.uploaded_assets_list.setItem(0, 1, waiting_item)
                
                # Clear other columns
                for col in [0, 2, 3, 4, 5, 6]:
                    empty_item = QTableWidgetItem("")
                    self.uploaded_assets_list.setItem(0, col, empty_item)
                return

            try:
                # Force a fresh API call without any caching
                assets = self.api_client.list_assets()

                if not assets:
                    self.uploaded_assets_list.setRowCount(1)
                    # Show a centered "No assets" message across all columns
                    no_assets_item = QTableWidgetItem("No assets ingested yet - database is empty")
                    no_assets_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    no_assets_item.setForeground(QColor("#666666"))  # Gray text
                    no_assets_item.setToolTip("The database has been cleared or no assets have been ingested yet")
                    self.uploaded_assets_list.setItem(0, 1, no_assets_item)  # Show in File Name column
                    
                    # Clear other columns
                    for col in [0, 2, 3, 4, 5, 6]:
                        empty_item = QTableWidgetItem("")
                        self.uploaded_assets_list.setItem(0, col, empty_item)
                    
                    # Log the empty state for debugging
                    print("DEBUG: refresh_uploaded_assets - No assets returned from API")
                    return

                # Sort by ingest timestamp (most recent first) - API already returns in this order
                # but we ensure it here for consistency
                sorted_assets = sorted(
                    assets, key=lambda a: a.get("created_at", ""), reverse=True
                )
                
                # Log the asset count for debugging
                print(f"DEBUG: refresh_uploaded_assets - Found {len(sorted_assets)} assets from API")

                for row, asset in enumerate(sorted_assets):
                    filename = str(asset.get("file_name") or "Unknown")
                    timestamp = asset.get("created_at")
                    kind = str(asset.get("kind") or "Unknown").upper()
                    
                    # Enhanced CRS display with better formatting
                    crs_raw = str(asset.get("crs") or "-")
                    if crs_raw.startswith("EPSG:"):
                        crs = crs_raw
                    elif crs_raw.startswith("http://www.opengis.net/def/crs/EPSG/0/"):
                        epsg_code = crs_raw.split("/")[-1]
                        crs = f"EPSG:{epsg_code}"
                    else:
                        crs = crs_raw if crs_raw != "-" else "Unknown"
                    
                    cell_size = self._format_asset_cell_size(
                        asset.get("resolution_x"), asset.get("resolution_y")
                    )
                    dimensions = self._format_asset_dimensions(
                        asset.get("width"), asset.get("height")
                    )
                    formatted_date = self._format_asset_created_at(timestamp)

                    self.uploaded_assets_list.insertRow(row)
                    
                    # Row number (1-based, newest first)
                    number_item = QTableWidgetItem(str(row + 1))
                    number_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.uploaded_assets_list.setItem(row, 0, number_item)

                    # File name with asset data attached - show just filename, full path in tooltip
                    display_name = filename
                    file_item = QTableWidgetItem(display_name)
                    file_item.setData(Qt.ItemDataRole.UserRole, asset)
                    file_item.setToolTip(f"Full path: {asset.get('file_path', 'Unknown')}")
                    
                    # Highlight recently added files (within last hour)
                    if self._is_recent_asset(timestamp):
                        file_item.setBackground(QColor("#e8f5e8"))  # Light green background
                        file_item.setToolTip(f"Recently added asset\nFull path: {asset.get('file_path', 'Unknown')}")
                    self.uploaded_assets_list.setItem(row, 1, file_item)
                    
                    # Enhanced kind display with proper capitalization
                    kind_item = QTableWidgetItem(kind)
                    if kind == "DEM":
                        kind_item.setBackground(QColor("#fff3e0"))  # Light orange for DEM
                        kind_item.setToolTip("Digital Elevation Model")
                    elif kind == "GEOTIFF":
                        kind_item.setBackground(QColor("#e3f2fd"))  # Light blue for imagery
                        kind_item.setToolTip("GeoTIFF raster image")
                    elif kind == "JPEG2000":
                        kind_item.setBackground(QColor("#f3e5f5"))  # Light purple for JPEG2000
                        kind_item.setToolTip("JPEG2000 compressed image")
                    elif kind == "MBTILES":
                        kind_item.setBackground(QColor("#e8f5e8"))  # Light green for tiles
                        kind_item.setToolTip("Pre-tiled MBTiles format")
                    self.uploaded_assets_list.setItem(row, 2, kind_item)
                    
                    # CRS with enhanced formatting
                    crs_item = QTableWidgetItem(crs)
                    crs_item.setToolTip(f"Coordinate Reference System: {crs}")
                    self.uploaded_assets_list.setItem(row, 3, crs_item)
                    
                    self.uploaded_assets_list.setItem(row, 4, QTableWidgetItem(cell_size))
                    self.uploaded_assets_list.setItem(row, 5, QTableWidgetItem(dimensions))
                    self.uploaded_assets_list.setItem(row, 6, QTableWidgetItem(formatted_date))

            except Exception as e:
                # Clear everything and show error message
                self.uploaded_assets_list.clear()
                self.uploaded_assets_list.setRowCount(1)
                self.uploaded_assets_list.setColumnCount(7)
                self.uploaded_assets_list.setHorizontalHeaderLabels(
                    ["#", "File Name", "Type", "CRS", "Cell Size", "Dimensions", "Added"]
                )
                
                # Ensure header text is visible and properly formatted
                header = self.uploaded_assets_list.horizontalHeader()
                header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
                header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
                header.setStretchLastSection(False)
                header.setMinimumSectionSize(60)
                
                # Show error message in the File Name column
                error_item = QTableWidgetItem(f"Error loading assets: {str(e)}")
                error_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                error_item.setForeground(QColor("#cc0000"))  # Red text for errors
                error_item.setToolTip("Click 'Refresh Catalog' to retry after fixing the issue")
                self.uploaded_assets_list.setItem(0, 1, error_item)
                
                # Clear the other columns for this error row
                for col in [0, 2, 3, 4, 5, 6]:
                    empty_item = QTableWidgetItem("")
                    self.uploaded_assets_list.setItem(0, col, empty_item)
        
        finally:
            # Reset the refreshing flag to allow future refreshes
            self._refreshing_assets = False

    def _on_refresh_catalog_clicked(self) -> None:
        """Handle refresh catalog button click - refreshes without clearing caches to prevent loops."""
        import time
        
        # Prevent rapid successive refreshes
        if hasattr(self, '_last_refresh_time'):
            if time.time() - self._last_refresh_time < 2.0:  # 2 second cooldown
                return
        
        self._last_refresh_time = time.time()
        
        # Just refresh the uploaded assets without clearing caches
        # Cache clearing will be handled by the controller when needed
        self.refresh_uploaded_assets()

    def _is_recent_asset(self, timestamp: str | None) -> bool:
        """Check if an asset was created recently (within last hour)."""
        if not timestamp:
            return False
        try:
            from datetime import datetime, timezone, timedelta
            # Parse ISO timestamp
            if timestamp.endswith('Z'):
                asset_time = datetime.fromisoformat(timestamp[:-1] + '+00:00')
            else:
                asset_time = datetime.fromisoformat(timestamp)
            
            # Make timezone-aware if needed
            if asset_time.tzinfo is None:
                asset_time = asset_time.replace(tzinfo=timezone.utc)
            
            now = datetime.now(timezone.utc)
            return (now - asset_time) < timedelta(hours=1)
        except Exception:
            return False

    def _apply_panel_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background: #f5f5f5;
                color: #1a1a1a;
            }
            QToolBox {
                background: transparent;
                color: #1a1a1a;
            }
            QToolBox::tab {
                background: #e8e8e8;
                border: 1px solid #b0b0b0;
                border-radius: 3px;
                padding: 7px 12px;
                margin: 1px 1px;
                font-weight: 700;
                font-size: 12px;
                color: #1a1a1a;
                text-align: center;
            }
            QToolBox::tab:selected {
                background: #ffffff;
                color: #0044aa;
                border: 2px solid #0066cc;
                padding: 6px 11px;
                font-weight: 700;
            }
            QToolBox::tab:hover {
                background: #f5f5f5;
            }
            QFrame#clientCollapseSection {
                background: #ffffff;
                border: 1px solid #d8d8d8;
                border-radius: 4px;
            }
            QFrame#clientCollapseHeader {
                background: #f0f0f0;
                border: none;
                border-bottom: 1px solid #e2e2e2;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QFrame#clientCollapseHeader:hover {
                background: #e8e8e8;
            }
            QLabel#clientCollapseTitle {
                color: #1a1a1a;
                font-weight: 700;
                font-size: 13px;
            }
            QLabel#clientCollapseArrow {
                color: #1a1a1a;
            }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                margin-top: 10px;
                padding: 8px;
                font-weight: 700;
                font-size: 13px;
                color: #1a1a1a;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
                color: #1a1a1a;
            }
            QFormLayout QLabel {
                font-weight: 600;
                color: #4a4a4a;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit {
                background: #ffffff;
                border: 1px solid #d0d0d0;
                border-radius: 2px;
                min-height: 26px;
                padding: 2px 6px;
                font-size: 12px;
                color: #1a1a1a;
            }
            QLineEdit:disabled,
            QComboBox:disabled,
            QSpinBox:disabled,
            QDoubleSpinBox:disabled,
            QTextEdit:disabled {
                background: #efefef;
                color: #8f8f8f;
                border: 1px solid #d1d1d1;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                border: 2px solid #0066cc;
            }
            QPushButton {
                background: #eef2f7;
                color: #1a1a1a;
                border: 1px solid #c4ccd6;
                border-radius: 2px;
                padding: 2px 8px;
                font-weight: 600;
                font-size: 11px;
                min-height: 24px;
            }
            QPushButton:hover {
                background: #f7f9fc;
                border: 1px solid #aeb8c5;
            }
            QPushButton:pressed {
                background: #dde3eb;
                border: 1px solid #9ba7b6;
            }
            QPushButton:disabled {
                background: #dfe3e8;
                color: #7b8592;
                border: 1px solid #bcc5cf;
            }
            QPushButton#searchPrimaryButton {
                background: #0b66d6;
                color: #ffffff;
                border: 1px solid #0a57b8;
            }
            QPushButton#searchPrimaryButton:hover {
                background: #0f74ee;
                border: 1px solid #0d63cf;
            }
            QPushButton#searchPrimaryButton:pressed {
                background: #0956b7;
                border: 1px solid #084a9e;
            }
            QPushButton#searchVisibilityToggle {
                background: #eef2f7;
                color: #1a1a1a;
                border: 1px solid #b8c2cf;
                border-radius: 2px;
                padding: 0px;
                min-height: 20px;
                min-width: 24px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton#searchVisibilityToggle:hover {
                background: #e2e8f0;
                border: 1px solid #9aa7b8;
            }
            QPushButton#searchVisibilityToggle:pressed {
                background: #d3dbe6;
                border: 1px solid #8895a8;
            }
            QSlider#moduleToggleSlider::groove:horizontal {
                border: 1px solid #c6cdd6;
                height: 8px;
                background: #d8dee6;
                border-radius: 4px;
            }
            QSlider#moduleToggleSlider::sub-page:horizontal {
                background: #0b66d6;
                border: 1px solid #0a57b8;
                border-radius: 4px;
            }
            QSlider#moduleToggleSlider::add-page:horizontal {
                background: #d8dee6;
                border: 1px solid #c6cdd6;
                border-radius: 4px;
            }
            QSlider#moduleToggleSlider::handle:horizontal {
                background: #ffffff;
                border: 1px solid #8d99aa;
                width: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            QSlider::groove:horizontal {
                border: 1px solid #d0d0d0;
                height: 6px;
                background: #e8e8e8;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #0b66d6;
                border: 1px solid #0b66d6;
                border-radius: 3px;
            }
            QSlider::add-page:horizontal {
                background: #e8e8e8;
                border: 1px solid #d0d0d0;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #0066cc;
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
                border: 1px solid #0066cc;
            }
            QSlider::groove:horizontal:disabled {
                background: #ededed;
                border: 1px solid #d7d7d7;
            }
            QSlider::sub-page:horizontal:disabled,
            QSlider::add-page:horizontal:disabled {
                background: #d7d7d7;
                border: 1px solid #cccccc;
            }
            QSlider::handle:horizontal:disabled {
                background: #b9b9b9;
                border: 1px solid #aeaeae;
            }
            QProgressBar {
                border: 1px solid #d0d0d0;
                border-radius: 2px;
                background: #f0f0f0;
                text-align: center;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background: #0066cc;
                border-radius: 3px;
            }
            QLabel {
                color: #1a1a1a;
                font-size: 12px;
            }
            QFormLayout {
                font-size: 12px;
            }
            """
        )

    def _apply_widget_shadows(self) -> None:
        # Apply subtle shadows to buttons for traditional desktop GUI look
        for button in (
            self.browse_btn,
            self.ingest_btn,
            self.assets_refresh_btn,
            self.refresh_assets_btn,
            self.add_layer_btn,
            self.rotate_left_btn,
            self.rotate_right_btn,
        ):
            effect = QGraphicsDropShadowEffect(button)
            effect.setBlurRadius(1.0)
            effect.setOffset(0.0, 0.0)
            effect.setColor(QColor(0, 0, 0, 20))
            button.setGraphicsEffect(effect)

    def set_layer_loading(self, active: bool, message: str) -> None:
        self.layer_load_status.setText(message)
        if active:
            self.layer_load_progress.setRange(0, 0)
            self.layer_load_progress.setVisible(True)
            return
        self.layer_load_progress.setRange(0, 100)
        self.layer_load_progress.setValue(100)
        self.layer_load_progress.setVisible(False)

    def _on_search_results_reordered(self, parent, start, end, destination, row) -> None:
        """Handle drag-and-drop reordering of search results with debounced real-time globe updates."""
        try:
            # Get the current search results data
            table = self.search_results_table
            if table.rowCount() == 0:
                return
            
            # Extract layer information from reordered table
            reordered_layers = []
            for i in range(table.rowCount()):
                # Get file name from the File column (index 1)
                file_item = table.item(i, 1)
                if not file_item:
                    continue
                    
                file_name = file_item.text()
                
                # Get kind from the Kind column (index 2) 
                kind_item = table.item(i, 2)
                kind = kind_item.text() if kind_item else "Unknown"
                
                # Get CRS from the CRS column (index 3)
                crs_item = table.item(i, 3)
                crs = crs_item.text() if crs_item else "-"
                
                reordered_layers.append({
                    "file_name": file_name,
                    "kind": kind,
                    "crs": crs,
                    "display_order": i  # New order based on table position
                })
            
            # Update the drag handle column to show new order immediately with better visibility
            for i, layer_info in enumerate(reordered_layers):
                handle_item = table.item(i, 0)  # Drag handle column
                if handle_item:
                    handle_item.setText("⋮⋮")
                    handle_item.setToolTip(f"Layer order: {i + 1}")
                    # Ensure text is visible during and after drag operations
                    handle_item.setForeground(QColor(102, 102, 102))  # Dark gray for visibility
                
                # Ensure all text items maintain visibility
                for col in range(1, table.columnCount()):
                    item = table.item(i, col)
                    if item:
                        item.setForeground(QColor(0, 0, 0))  # Black text for visibility
            
            # Store the reorder data and start debounce timer
            self._pending_reorder_data = reordered_layers
            self._reorder_debounce_timer.start(150)  # 150ms debounce
            
        except Exception as e:
            print(f"ERROR: Failed to handle search results reordering: {e}")
            import traceback
            traceback.print_exc()

    def _process_pending_reorder(self) -> None:
        """Process the pending reorder operation after debounce delay."""
        if self._pending_reorder_data is None:
            return
        
        try:
            # Emit signal to controller for real-time globe layer reordering
            if hasattr(self, 'search_layers_reordered'):
                self.search_layers_reordered.emit(self._pending_reorder_data)
            
            self._pending_reorder_data = None
            
        except Exception as e:
            print(f"ERROR: Failed to process pending reorder: {e}")
            import traceback
            traceback.print_exc()
