from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtCore import Qt, Signal, QTimer
from qtpy.QtGui import QColor, QPalette
from qtpy.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QPushButton,
    QProgressBar,
    QProgressDialog,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolBox,
    QVBoxLayout,
    QWidget,
)

from src_new.clients.desktop_search.app_mode import DesktopAppMode
from src_new.clients.desktop_search.control_panel_collapsible import (
    ClientCollapsibleSection,
)
from src_new.clients.desktop_search.control_panel_display import ControlPanelDisplayMixin
from src_new.clients.desktop_search.control_panel_ingest import ControlPanelIngestMixin
from src_new.clients.desktop_search.control_panel_log import ControlPanelLogMixin
from src_new.clients.desktop_search.control_panel_search import ControlPanelSearchMixin
from src_new.clients.desktop_search.control_panel_styles import ControlPanelStyleMixin

if TYPE_CHECKING:
    from src_new.clients.desktop_search.api_client import DesktopApiClient


class ControlPanel(
    ControlPanelIngestMixin,
    ControlPanelSearchMixin,
    ControlPanelDisplayMixin,
    ControlPanelLogMixin,
    ControlPanelStyleMixin,
    QWidget,
):
    """Desktop control panel widgets for ingest, search, display, and measurement tools."""

    search_result_visibility_toggled = Signal(str, bool)
    search_layers_reordered = Signal(list)  # Signal for drag-and-drop layer reordering
    asset_focus_requested = Signal(str)
    vector_layer_visibility_toggled = Signal(str, bool)
    vector_layer_delete_requested = Signal(str)
    visualization_tools_toggled = Signal(bool)
    measurement_tools_toggled = Signal(bool)
    measurement_result_clear_selected_requested = Signal()
    measurement_result_clear_all_requested = Signal()
    uploaded_assets_refresh_requested = (
        Signal()
    )  # Signal to request controller cache clearing
    asset_delete_requested = Signal(dict)  # Signal to request asset deletion
    search_layer_delete_requested = Signal(str)  # Signal to request search layer deletion

    def __init__(
        self,
        parent: QWidget | None = None,
        app_mode: DesktopAppMode = DesktopAppMode.UNIFIED,
        api_client: DesktopApiClient | None = None,
    ):
        super().__init__(parent)
        self.api_client = api_client
        self.setMinimumWidth(380)

        # Persistent layer order tracking (independent of Qt table state)
        self._layer_order_registry = {}  # {file_path: {"file_name": str, "kind": str, "crs": str, "created_at": str, "is_visible": bool, "order": int}}

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
        self.sections.setStyleSheet("""
            QToolBox::tab {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #fcfdfe, stop:1 #e2e8f0);
                border: 1px solid #cbd5e0;
                border-radius: 4px;
                color: #2d3748;
                font-weight: 600;
                padding: 4px;
            }
            QToolBox::tab:selected {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ebf8ff, stop:1 #bee3f8);
                border: 1px solid #4299e1;
                color: #2b6cb0;
            }
            QGroupBox {
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                margin-top: 10px;
                background: #ffffff;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
                color: #4a5568;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #edf2f7);
                border: 1px solid #cbd5e0;
                border-radius: 4px;
                padding: 6px 12px;
                color: #2d3748;
                font-weight: 500;
            }
            QPushButton:hover {
                background: #ffffff;
                border: 1px solid #4299e1;
                color: #2b6cb0;
            }
            QPushButton:pressed {
                background: #e2e8f0;
            }
        """)

        # Multiple file selection UI
        self.selected_files_list = QListWidget()
        self.selected_files_list.setMaximumHeight(120)
        self.selected_files_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.selected_files_list.setStyleSheet("""
            QListWidget { 
                background: #ffffff; 
                border: 1px solid #d0d0d0; 
                border-radius: 3px; 
                font-size: 11px;
            }
            QListWidget::item { 
                padding: 4px; 
                border-bottom: 1px solid #f0f0f0;
            }
            QListWidget::item:selected { 
                background: #e8f4ff; 
                color: #10233f;
            }
        """)

        # Format selection dropdown
        self.format_combo = QComboBox()
        self.format_combo.addItems(
            ["GeoTIFF (.tif)", "JPEG2000 (.jp2, .j2k) + .prj", "MBTiles (.mbtiles)"]
        )
        self.format_combo.setCurrentIndex(0)  # Default to GeoTIFF
        self.format_combo.setToolTip("Select raster format type for ingestion")
        self.format_combo.setStyleSheet("""
            QComboBox {
                padding: 5px;
                border: 1px solid #c0c0c0;
                border-radius: 3px;
                background: white;
                font-size: 11px;
            }
            QComboBox:hover {
                border: 1px solid #0078d4;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
        """)

        self.browse_files_btn = QPushButton("Select Files")
        self.clear_selection_btn = QPushButton("Clear")
        self.ingest_btn = QPushButton("Ingest Files")

        self.browse_files_btn.setToolTip(
            "Select multiple raster files based on chosen format"
        )
        self.clear_selection_btn.setToolTip("Clear all selected files")
        self.ingest_btn.setToolTip(
            "Queue selected files for ingestion with automatic processing"
        )

        # Validation status label
        self.validation_status_label = QLabel("")
        self.validation_status_label.setStyleSheet("""
            QLabel {
                padding: 5px;
                border-radius: 3px;
                font-size: 11px;
                font-weight: 600;
            }
        """)
        self.validation_status_label.setWordWrap(True)

        self.upload_box = QGroupBox("Ingest")
        upload_layout = QVBoxLayout(self.upload_box)

        # Format selection row
        format_row = QHBoxLayout()
        format_label = QLabel("Format:")
        format_label.setStyleSheet("font-weight: 600; color: #4a4a4a;")
        format_row.addWidget(format_label)
        format_row.addWidget(self.format_combo, 1)
        upload_layout.addLayout(format_row)

        # File selection area
        selection_label = QLabel("Selected Files:")
        selection_label.setStyleSheet("font-weight: 600; color: #4a4a4a;")
        upload_layout.addWidget(selection_label)
        upload_layout.addWidget(self.selected_files_list)

        # Validation status
        upload_layout.addWidget(self.validation_status_label)

        # Button row for file selection (removed Select Folder button)
        selection_row = QHBoxLayout()
        selection_row.addWidget(self.browse_files_btn, 1)
        selection_row.addWidget(self.clear_selection_btn, 0)
        upload_layout.addLayout(selection_row)

        # Ingest button
        ingest_row = QHBoxLayout()
        ingest_row.addStretch()
        ingest_row.addWidget(self.ingest_btn, 1)
        ingest_row.addStretch()
        upload_layout.addLayout(ingest_row)

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

        # Uploaded Assets table (simplified view with delete functionality)
        self.uploaded_assets_list = QTableWidget(
            0, 4
        )  # Simplified: #, Type, Added, Delete
        self.uploaded_assets_list.setMaximumHeight(200)
        self.uploaded_assets_list.setHorizontalHeaderLabels(
            ["#", "Type", "Added", "Delete"]
        )
        self.uploaded_assets_list.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeToContents,  # Serial number
        )
        self.uploaded_assets_list.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.ResizeToContents,  # Type
        )
        self.uploaded_assets_list.horizontalHeader().setSectionResizeMode(
            2,
            QHeaderView.Stretch,  # Added date (stretch to fill)
        )
        self.uploaded_assets_list.horizontalHeader().setSectionResizeMode(
            3,
            QHeaderView.ResizeToContents,  # Delete button
        )
        # Configure column widths for better display and enable horizontal scrolling
        self.uploaded_assets_list.setHorizontalScrollMode(
            QAbstractItemView.ScrollPerPixel
        )
        self.uploaded_assets_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        # Set column widths for simplified table
        self.uploaded_assets_list.setColumnWidth(0, 50)  # Serial number
        self.uploaded_assets_list.setColumnWidth(1, 100)  # Type
        self.uploaded_assets_list.setColumnWidth(2, 150)  # Added date
        self.uploaded_assets_list.setColumnWidth(3, 70)  # Delete button

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
        self.assets_refresh_btn.setToolTip(
            "Refresh the list of uploaded assets and clear all caches."
        )

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
        # add_layer_btn removed per user request

        self.assets_combo.setToolTip(
            "Catalog entries are metadata records. Raw data stays on storage."
        )
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

        self.search_results_table = QTableWidget(
            0, 7
        )  # Added one more column for drag handle and delete
        self._ensure_search_results_header()

        # Configure drag and drop for layer reordering with smooth animations
        self.search_results_table.setDragDropMode(QAbstractItemView.InternalMove)
        self.search_results_table.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.search_results_table.setDragDropOverwriteMode(False)
        self.search_results_table.setSelectionBehavior(QAbstractItemView.SelectRows)

        # Enable drag indicator and ensure smooth dragging
        self.search_results_table.setDragEnabled(True)
        self.search_results_table.setAcceptDrops(True)
        self.search_results_table.setAutoScroll(True)
        self.search_results_table.setAutoScrollMargin(35)

        # CRITICAL: Disable sorting during drag operations to prevent conflicts
        self.search_results_table.setSortingEnabled(False)

        # Enable smooth scrolling for better UX
        self.search_results_table.setVerticalScrollMode(
            QAbstractItemView.ScrollPerPixel
        )
        self.search_results_table.setHorizontalScrollMode(
            QAbstractItemView.ScrollPerPixel
        )

        # Install custom drop event handler for drag-and-drop reordering
        self.search_results_table.dropEvent = self._create_table_drop_handler()

        # Set column widths for drag handle
        self.search_results_table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeToContents,  # Drag handle column
        )
        self.search_results_table.itemClicked.connect(self._on_search_table_item_clicked)
        self.search_results_table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.Stretch,  # File name
        )
        self.search_results_table.horizontalHeader().setSectionResizeMode(
            2,
            QHeaderView.ResizeToContents,  # Kind
        )
        self.search_results_table.horizontalHeader().setSectionResizeMode(
            3,
            QHeaderView.ResizeToContents,  # CRS
        )
        self.search_results_table.horizontalHeader().setSectionResizeMode(
            4,
            QHeaderView.Interactive,  # View
        )
        self.search_results_table.horizontalHeader().setSectionResizeMode(
            5,
            QHeaderView.Interactive,  # Delete
        )

        # Set specific column widths
        self.search_results_table.setColumnWidth(0, 30)  # Drag handle
        self.search_results_table.setColumnWidth(1, 220)  # File name
        self.search_results_table.setColumnWidth(2, 78)  # Kind
        self.search_results_table.setColumnWidth(3, 96)  # CRS
        self.search_results_table.setColumnWidth(4, 60)  # View
        self.search_results_table.setColumnWidth(5, 60)  # Delete
        self.search_results_table.verticalHeader().setVisible(False)
        self.search_results_table.verticalHeader().setDefaultSectionSize(30)
        self.search_results_table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.search_results_table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.search_results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.search_results_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.search_results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.search_results_table.setStyleSheet(
            """
            QTableWidget {
                background: #ffffff;
                border: 1px solid #d0d0d0;
                border-radius: 4px;
                gridline-color: #e0e0e0;
                font-size: 11px;
                color: #000000;
            }
            QTableWidget::item {
                padding: 2px;
                color: #000000;
            }
            QHeaderView::section {
                background: #f5f5f5;
                color: #333333;
                font-weight: 600;
                padding: 4px;
                border: 1px solid #d0d0d0;
                font-size: 11px;
            }
            """
        )
        self.search_results_table.setAlternatingRowColors(False)
        self.search_results_table.setWordWrap(False)
        self.search_results_table.setTextElideMode(Qt.TextElideMode.ElideMiddle)

        # macOS QMacStyle ignores rgba alpha in palette and in CSS background on ::item.
        # Must use fully opaque colors. AlternateBase must also be white (not gray)
        # or macOS will paint its own system blue on alternating rows.
        palette = self.search_results_table.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))           # all rows: white
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(255, 255, 255)) # alt rows: also white
        palette.setColor(QPalette.ColorRole.Highlight, QColor(204, 228, 255))     # selected row: soft blue
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))    # selected text: black
        palette.setColor(QPalette.ColorRole.Text, QColor(0, 0, 0))               # normal text: black
        self.search_results_table.setPalette(palette)

        self.search_results_table.setStyleSheet(
            """
            QTableWidget {
                background: #ffffff;
                border: 1px solid #d0d0d0;
                border-radius: 3px;
                gridline-color: #ebebeb;
                font-size: 11px;
                color: #000000;
            }
            QTableWidget::item {
                background: #ffffff;
                padding: 2px 4px;
                border: none;
                color: #000000;
            }
            QTableWidget::item:hover {
                background: #f0f7ff;
                color: #000000;
            }
            QTableWidget::item:selected {
                background: #cce4ff;
                color: #000000;
            }
            QTableWidget::item:selected:active {
                background: #cce4ff;
                color: #000000;
            }
            QTableWidget::item:selected:!active {
                background: #e5f0ff;
                color: #000000;
            }
            QTableWidget QHeaderView::section {
                background: #f5f5f5;
                padding: 2px;
                border: none;
                border-right: 1px solid #d8d8d8;
                border-bottom: 1px solid #d0d0d0;
                font-weight: 600;
                font-size: 11px;
                color: #000000;
            }
            /* Remove focus rectangle/dotted lines */
            QTableWidget::item:focus {
                outline: none;
                border: none;
            }
            QTableWidget:focus {
                outline: none;
                border: 1px solid #0078d4;
            }
            """
        )
        self._set_search_results_table_visible_rows(5)
        search_layout.addWidget(self.search_results_table)

        search_layout.addSpacing(6)
        search_layout.addWidget(QLabel("<b>Vector Layers</b>"))
        self.vector_layers_table = QTableWidget(0, 4)
        self._ensure_vector_layers_header()
        self.vector_layers_table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.Stretch,
        )
        self.vector_layers_table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.ResizeToContents,
        )
        self.vector_layers_table.horizontalHeader().setSectionResizeMode(
            2,
            QHeaderView.ResizeToContents,
        )
        self.vector_layers_table.horizontalHeader().setSectionResizeMode(
            3,
            QHeaderView.ResizeToContents,
        )
        self.vector_layers_table.setColumnWidth(0, 220)  # Name
        self.vector_layers_table.setColumnWidth(1, 120)  # Source
        self.vector_layers_table.setColumnWidth(2, 60)  # View
        self.vector_layers_table.setColumnWidth(3, 60)  # Delete
        self.vector_layers_table.verticalHeader().setVisible(False)
        self.vector_layers_table.verticalHeader().setDefaultSectionSize(22)
        self.vector_layers_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.vector_layers_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.vector_layers_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.vector_layers_table.setAlternatingRowColors(True)
        self.vector_layers_table.setWordWrap(False)
        self.vector_layers_table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.vector_layers_table.setStyleSheet(
            """
            QTableWidget {
                background: #ffffff;
                border: 1px solid #d0d0d0;
                border-radius: 4px;
                gridline-color: #e0e0e0;
                font-size: 11px;
                color: #000000;
            }
            QTableWidget::item {
                padding: 2px;
                border: none;
                color: #000000;
            }
            QTableWidget::item:selected {
                background: rgba(232, 244, 255, 0.7);
                color: #000000;
            }
            QHeaderView::section {
                background: #f5f5f5;
                color: #333333;
                font-weight: 600;
                padding: 4px;
                border: 1px solid #d0d0d0;
                font-size: 11px;
            }
            """
        )
        search_layout.addWidget(self.vector_layers_table)

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
        self.stretch_mode_combo = QComboBox()
        self.stretch_mode_combo.addItem("RGB Min-Max (Per-Channel)", "minmax")
        self.stretch_mode_combo.addItem("RGB Linear (Shared)", "linear_shared")
        self.stretch_mode_combo.setCurrentIndex(0)
        self.stretch_mode_combo.setToolTip(
            "Rescale RGB imagery values before rendering."
        )
        self.dem_stretch_mode_combo = QComboBox()
        self.dem_stretch_mode_combo.addItem("Min-Max", "minmax")
        self.dem_stretch_mode_combo.addItem("Std Dev (2x)", "stddev")
        self.dem_stretch_mode_combo.addItem("Histogram Equalization", "histeq")
        self.dem_stretch_mode_combo.setCurrentIndex(0)
        self.dem_stretch_mode_combo.setToolTip(
            "Rescale DEM values before rendering terrain."
        )
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
        self.dem_hillshade_slider = QSlider(Qt.Orientation.Horizontal)
        self.dem_hillshade_slider.setRange(0, 100)
        self.dem_hillshade_slider.setValue(0)
        self.dem_hillshade_value = QLabel()
        self.dem_hillshade_value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.dem_hillshade_value.setMinimumWidth(64)
        self.dem_color_mode_combo = QComboBox()
        self.dem_color_mode_combo.addItem("White relief", "gray")
        self.dem_color_mode_combo.addItem("Color relief", "terrain")
        self.dem_color_mode_combo.addItem("Slope map (deg)", "slope")
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
        rgb_label = QLabel("<b>Imagery (RGB)</b>")
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
        stretch_layout = QHBoxLayout()
        stretch_layout.addWidget(QLabel("Stretch:"))
        stretch_layout.addWidget(self.stretch_mode_combo, 1)
        view_layout.addLayout(stretch_layout)

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
        dem_label = QLabel("<b>Terrain (DEM)</b>")
        view_layout.addWidget(dem_label)
        hillshade_layout = QHBoxLayout()
        hillshade_layout.addWidget(QLabel("Hillshade:"))
        hillshade_layout.addWidget(self.dem_hillshade_slider, 1)
        hillshade_layout.addWidget(self.dem_hillshade_value)
        view_layout.addLayout(hillshade_layout)
        dem_color_layout = QHBoxLayout()
        dem_color_layout.addWidget(QLabel("Style:"))
        dem_color_layout.addWidget(self.dem_color_mode_combo, 1)
        view_layout.addLayout(dem_color_layout)
        dem_stretch_layout = QHBoxLayout()
        dem_stretch_layout.addWidget(QLabel("Stretch:"))
        dem_stretch_layout.addWidget(self.dem_stretch_mode_combo, 1)
        view_layout.addLayout(dem_stretch_layout)

        view_layout.addStretch()

        for slider in (
            self.brightness_slider,
            self.contrast_slider,
            self.pitch_slider,
            self.dem_hillshade_slider,
        ):
            slider.valueChanged.connect(self._update_display_value_labels)
        self._update_display_value_labels()

        self.click_label = QLabel("None")
        self.measure_label = QLabel("N/A")
        self.status_box = QTextEdit()
        self.status_box.setReadOnly(True)
        self.status_box.setAcceptRichText(True)
        self.status_box.setMinimumHeight(180)
        self.status_box.setStyleSheet("""
            QTextEdit {
                background: #0d1117;
                border: 1px solid #30363d;
                border-radius: 6px;
                font-family: 'Consolas', 'Cascadia Code', 'Monaco', monospace;
                font-size: 11px;
                color: #c9d1d9;
                padding: 6px;
            }
            QScrollBar:vertical {
                background: #161b22;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #30363d;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #484f58;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        self.log_box = QGroupBox("Activity Log")
        log_layout = QVBoxLayout(self.log_box)
        log_layout.setSpacing(0)
        log_layout.setContentsMargins(8, 8, 8, 8)
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
        # Removed measurement_results_box per user request: "remove all.just keep a scrollable thing where logs are shown"
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
                self.assets_refresh_btn.clicked.connect(
                    self._on_refresh_catalog_clicked
                )
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
