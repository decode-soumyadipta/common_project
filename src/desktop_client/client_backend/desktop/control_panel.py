from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from qtpy.QtCore import Qt, Signal, QTimer, Slot
from qtpy.QtGui import QColor, QBrush, QPalette
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
    uploaded_assets_refresh_requested = (
        Signal()
    )  # Signal to request controller cache clearing
    asset_delete_requested = Signal(dict)  # Signal to request asset deletion

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
            0, 6
        )  # Added one more column for drag handle
        self._ensure_search_results_header()

        # Configure drag and drop for layer reordering with smooth animations
        self.search_results_table.setDragDropMode(QAbstractItemView.InternalMove)
        self.search_results_table.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.search_results_table.setDragDropOverwriteMode(False)
        self.search_results_table.setSelectionBehavior(QAbstractItemView.SelectRows)

        # Enable drag indicator and ensure smooth dragging
        self.search_results_table.setDragEnabled(True)
        self.search_results_table.setAcceptDrops(True)

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
            QHeaderView.ResizeToContents,  # Added
        )
        self.search_results_table.horizontalHeader().setSectionResizeMode(
            5,
            QHeaderView.ResizeToContents,  # View
        )

        # Set specific column widths
        self.search_results_table.setColumnWidth(0, 30)  # Drag handle
        self.search_results_table.setColumnWidth(1, 220)  # File name
        self.search_results_table.setColumnWidth(2, 78)  # Kind
        self.search_results_table.setColumnWidth(3, 96)  # CRS
        self.search_results_table.setColumnWidth(4, 120)  # Added
        self.search_results_table.setColumnWidth(5, 60)  # View
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

        # Set palette for proper text colors (more reliable than CSS for selection)
        # CRITICAL: Force black text even when selected to prevent blue bar from hiding text
        from qtpy.QtGui import QPalette

        palette = self.search_results_table.palette()
        palette.setColor(QPalette.ColorRole.Text, QColor(0, 0, 0))  # Normal text: black
        palette.setColor(
            QPalette.ColorRole.HighlightedText, QColor(0, 0, 0)
        )  # Selected text: FORCE BLACK
        palette.setColor(
            QPalette.ColorRole.Highlight, QColor(232, 244, 255, 180)
        )  # Selection background: semi-transparent light blue
        palette.setColor(
            QPalette.ColorRole.AlternateBase, QColor(250, 250, 250)
        )  # Alternate row: light gray
        palette.setColor(
            QPalette.ColorRole.Base, QColor(255, 255, 255)
        )  # Base background: white
        self.search_results_table.setPalette(palette)

        self.search_results_table.setStyleSheet(
            """
            QTableWidget {
                background: #ffffff;
                border: 1px solid #d0d0d0;
                border-radius: 3px;
                gridline-color: #f0f0f0;
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
            QTableWidget::item:first-child:selected {
                background: #c8e0ff;
                color: #000000;
            }
            QTableWidget QHeaderView::section {
                background: #f5f5f5;
                padding: 2px;
                border: none;
                border-right: 1px solid #d0d0d0;
                font-weight: 600;
                font-size: 11px;
                color: #000000;
            }
            QHeaderView::section:first {
                text-align: center;
                color: #888888;
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

    def update_search_results(
        self, assets: list[dict], visibility_by_path: dict[str, bool] | None = None
    ) -> None:
        """Update search results table with proper ordering: Imagery first (top), then DEM (bottom)."""
        print(f"\n{'=' * 80}")
        print(f"DEBUG: update_search_results called with {len(assets)} assets")
        if visibility_by_path:
            print(f"DEBUG: Visibility map provided: {visibility_by_path}")
        else:
            print(f"DEBUG: No visibility map provided")
        print(f"{'=' * 80}\n")

        self.search_results_table.setRowCount(0)
        self.search_results_table.setSortingEnabled(False)
        self._ensure_search_results_header()
        visibility_map = visibility_by_path or {}

        # Sort assets: Imagery first (top of list), DEM last (bottom of list)
        # This matches the visual stacking on the globe where imagery is on top
        def sort_key(asset):
            kind = str(asset.get("kind") or "").lower()
            created_at = self._search_created_at_sort_key(asset.get("created_at"))
            # Imagery (kind != "dem") gets priority 0, DEM gets priority 1
            # Within each group, sort by date (newest first)
            is_dem = 1 if kind == "dem" else 0
            return (is_dem, -created_at)  # Negative for reverse date order

        default_sorted_assets = sorted(assets, key=sort_key)
        assets_by_path = {
            str(asset.get("file_path") or "").replace("\\", "/"): asset
            for asset in default_sorted_assets
        }
        ordered_paths = []
        if self._layer_order_registry:
            ordered_paths = [
                path
                for path, entry in sorted(
                    self._layer_order_registry.items(),
                    key=lambda item: item[1].get("order", 0),
                )
                if path in assets_by_path
            ]
        remaining_assets = [
            asset
            for asset in default_sorted_assets
            if str(asset.get("file_path") or "").replace("\\", "/") not in ordered_paths
        ]
        sorted_assets = [
            assets_by_path[path] for path in ordered_paths
        ] + remaining_assets
        # Preserve existing metadata and visibility while updating orders
        new_registry = {}
        for idx, asset in enumerate(sorted_assets):
            path = str(asset.get("file_path") or "").replace("\\", "/")
            if not path:
                continue

            if path in self._layer_order_registry:
                # Existing entry: preserve its metadata and specific visibility unless overridden
                entry = self._layer_order_registry[path].copy()
                entry["order"] = idx
                if path in visibility_map:
                    entry["is_visible"] = visibility_map[path]
                new_registry[path] = entry
            else:
                # New entry: use provided visibility or default to True
                new_registry[path] = {
                    "file_name": str(asset.get("file_name") or "-"),
                    "kind": str(asset.get("kind") or "-"),
                    "crs": str(asset.get("crs") or "-"),
                    "created_at": self._format_search_created_at(asset.get("created_at")),
                    "is_visible": visibility_map.get(path, True),
                    "order": idx,
                }
        self._layer_order_registry = new_registry

        print(f"DEBUG: Sorted assets order:")
        for i, asset in enumerate(sorted_assets):
            kind = str(asset.get("kind") or "").upper()
            file_name = str(asset.get("file_name") or "-")
            print(f"  {i + 1}. {kind}: {file_name}")

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

            # Normalize path for lookup (match controller's normalization)
            normalized_path = file_path.replace("\\", "/")
            is_visible = visibility_map.get(normalized_path, True)

            print(f"\nDEBUG: Creating row {row} for {kind} - {file_name}")
            print(f"  file_path (raw): {file_path}")
            print(f"  normalized_path: {normalized_path}")
            print(f"  visibility_map has key: {normalized_path in visibility_map}")
            print(f"  is_visible: {is_visible}")

            # Create visibility toggle button with eye icons
            toggle_button = QPushButton(
                "👁" if is_visible else "👁‍🗨"
            )  # Eye / Eye with speech bubble (crossed)
            toggle_button.setObjectName("searchVisibilityToggle")
            toggle_button.setToolTip("Hide from map" if is_visible else "Show on map")
            toggle_button.setFixedSize(32, 24)
            toggle_button.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: 1px solid #d0d0d0;
                    border-radius: 3px;
                    font-size: 14px;
                    padding: 0px;
                }
                QPushButton:hover {
                    background: #f0f0f0;
                    border: 1px solid #0066cc;
                }
                QPushButton:pressed {
                    background: #e0e0e0;
                }
                QPushButton:disabled {
                    color: #cccccc;
                    border: 1px solid #e0e0e0;
                }
            """)

            if not file_path:
                toggle_button.setEnabled(False)
                print(f"  Button disabled (no file path)")
            else:
                # Normalize path to match controller's format
                normalized_path = file_path.replace("\\", "/")

                # Store current visibility state in button property
                toggle_button.setProperty("is_visible", is_visible)
                toggle_button.setProperty(
                    "file_path", normalized_path
                )  # Store normalized path

                print(
                    f"  Button created: text={'👁' if is_visible else '👁‍🗨'}, is_visible={is_visible}, path={normalized_path}"
                )

                def make_toggle_handler(btn, path):
                    def handler():
                        current_visible = btn.property("is_visible")
                        new_visible = not current_visible
                        print(f"\nDEBUG: Toggle button clicked!")
                        print(f"  path: {path}")
                        print(f"  current_visible: {current_visible}")
                        print(f"  new_visible: {new_visible}")
                        # Update button immediately for responsive feel
                        btn.setText("👁" if new_visible else "👁‍🗨")
                        btn.setToolTip(
                            "Hide from map" if new_visible else "Show on map"
                        )
                        btn.setProperty("is_visible", new_visible)
                        print(f"  Button updated: text={'👁' if new_visible else '👁‍🗨'}")
                        # Emit signal to update map
                        print(
                            f"  Emitting signal: search_result_visibility_toggled({path}, {new_visible})"
                        )
                        self.search_result_visibility_toggled.emit(path, new_visible)

                    return handler

                toggle_button.clicked.connect(
                    make_toggle_handler(toggle_button, normalized_path)
                )

            # Add drag handle in first column
            drag_handle_item = QTableWidgetItem("⋮⋮")
            drag_handle_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            drag_handle_item.setToolTip(f"Drag to reorder (Layer {row + 1})")
            drag_handle_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsDragEnabled
                | Qt.ItemFlag.ItemIsDropEnabled
            )
            drag_handle_item.setForeground(
                QBrush(QColor(102, 102, 102))
            )  # Dark gray for visibility

            # Create table items with explicit text color for visibility
            # CRITICAL: Store file_path in UserRole for drag-and-drop reordering
            file_item = QTableWidgetItem(file_name)
            file_item.setData(
                Qt.ItemDataRole.UserRole, normalized_path
            )  # Store file_path for reordering
            file_item.setForeground(QBrush(QColor(0, 0, 0)))  # Black text
            file_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsDragEnabled
                | Qt.ItemFlag.ItemIsDropEnabled
            )

            kind_item = QTableWidgetItem(kind)
            kind_item.setForeground(QBrush(QColor(0, 0, 0)))  # Black text
            kind_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsDragEnabled
                | Qt.ItemFlag.ItemIsDropEnabled
            )

            crs_item = QTableWidgetItem(crs)
            crs_item.setForeground(QBrush(QColor(0, 0, 0)))  # Black text
            crs_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsDragEnabled
                | Qt.ItemFlag.ItemIsDropEnabled
            )

            created_item = QTableWidgetItem(created_at)
            created_item.setForeground(QBrush(QColor(0, 0, 0)))  # Black text
            created_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsDragEnabled
                | Qt.ItemFlag.ItemIsDropEnabled
            )

            self.search_results_table.setItem(row, 0, drag_handle_item)
            self.search_results_table.setItem(row, 1, file_item)
            self.search_results_table.setItem(row, 2, kind_item)
            self.search_results_table.setItem(row, 3, crs_item)
            self.search_results_table.setItem(row, 4, created_item)
            self.search_results_table.setCellWidget(row, 5, toggle_button)

            # Force text color update after setting items (workaround for Qt palette issues)
            for col_idx, item in [
                (1, file_item),
                (2, kind_item),
                (3, crs_item),
                (4, created_item),
            ]:
                if item:
                    item.setData(
                        Qt.ItemDataRole.ForegroundRole, QBrush(QColor(0, 0, 0))
                    )

            print(
                f"DEBUG: Created table items for row {row}: file={file_name}, kind={kind}, crs={crs}, path={normalized_path}"
            )

        # Don't enable sorting - it conflicts with drag-and-drop
        # self.search_results_table.setSortingEnabled(True)
        print(
            f"\nDEBUG: Search results table populated with {self.search_results_table.rowCount()} rows"
        )
        print(f"DEBUG: update_search_results completed\n{'=' * 80}\n")

    def _set_search_results_table_visible_rows(self, visible_rows: int) -> None:
        header_height = self.search_results_table.horizontalHeader().sizeHint().height()
        row_height = self.search_results_table.verticalHeader().defaultSectionSize()
        frame_height = self.search_results_table.frameWidth() * 2
        total_height = (
            header_height + (row_height * max(1, visible_rows)) + frame_height
        )
        self.search_results_table.setMinimumHeight(total_height)
        self.search_results_table.setMaximumHeight(total_height)

    def _ensure_search_results_header(self) -> None:
        labels = ["⋮⋮", "File", "Kind", "CRS", "Added", "View"]
        if self.search_results_table.columnCount() != len(labels):
            self.search_results_table.setColumnCount(len(labels))
        self.search_results_table.setHorizontalHeaderLabels(labels)
        self.search_results_table.horizontalHeader().setVisible(True)

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
        hillshade_percent = int(self.dem_hillshade_slider.value())

        self.brightness_value.setText(f"{brightness_scale:.2f}x")
        self.contrast_value.setText(f"{contrast_scale:.2f}x")
        self.pitch_value.setText(f"{pitch_degrees} deg")
        self.dem_hillshade_value.setText(f"{hillshade_percent}%")

    def log(self, message: str) -> None:
        """Append a message to the Activity Log with coloured tags for warnings/errors."""
        import html as _html
        from datetime import datetime as _dt
        ts = _dt.now().strftime("%H:%M:%S")
        msg_lower = message.lower()
        safe_msg = _html.escape(message)
        if "error" in msg_lower or "failed" in msg_lower or "exception" in msg_lower:
            line = (
                f'<span style="color:#6e7681">[{ts}]</span> '
                f'<span style="background:#3d0c0c;color:#ff7b7b;border-radius:3px;padding:1px 5px;font-weight:bold;">ERR</span> '
                f'<span style="color:#ffa6a6">{safe_msg}</span>'
            )
        elif "warn" in msg_lower:
            line = (
                f'<span style="color:#6e7681">[{ts}]</span> '
                f'<span style="background:#3d2a00;color:#f0b429;border-radius:3px;padding:1px 5px;font-weight:bold;">WRN</span> '
                f'<span style="color:#f0d080">{safe_msg}</span>'
            )
        else:
            line = (
                f'<span style="color:#6e7681">[{ts}]</span> '
                f'<span style="color:#c9d1d9">{safe_msg}</span>'
            )
        self.status_box.append(line)
        # Auto-scroll to bottom
        sb = self.status_box.verticalScrollBar()
        sb.setValue(sb.maximum())

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

    @Slot(float, float, float)
    def update_camera_info(self, scale_denominator: float, heading_deg: float, pitch_deg: float) -> None:
        """Update the pitch slider from live camera telemetry without triggering a bounce-back."""
        if not self.pitch_slider.isEnabled():
            return
            
        # Pitch from Cesium is roughly -90 (looking straight down) to 0 (looking horizontal)
        # Or it might be positive depending on the coordinate frame, but usually negative in the slider.
        # Clamp it to the slider range and set the value.
        pitch_val = int(pitch_deg)
        if pitch_val > self.pitch_slider.maximum():
            pitch_val = self.pitch_slider.maximum()
        elif pitch_val < self.pitch_slider.minimum():
            pitch_val = self.pitch_slider.minimum()
            
        # Set value silently so we don't emit valueChanged and cause an infinite loop
        self.pitch_slider.blockSignals(True)
        self.pitch_slider.setValue(pitch_val)
        self.pitch_slider.blockSignals(False)
        self._update_display_value_labels()

    def add_selected_files(self, file_paths: list[str]) -> None:
        """Add files to the selection list with format-specific validation."""
        from pathlib import Path

        # Clear existing selection
        self.selected_files_list.clear()
        self.validation_status_label.clear()

        if not file_paths:
            return

        # Get selected format
        format_index = self.format_combo.currentIndex()
        format_name = self.format_combo.currentText()

        # Validate and group files based on format
        if format_index == 0:  # GeoTIFF
            validated_files, errors = self._validate_geotiff_files(file_paths)
        elif format_index == 1:  # JPEG2000 + PRJ
            validated_files, errors = self._validate_jp2_files(file_paths)
        elif format_index == 2:  # MBTiles
            validated_files, errors = self._validate_mbtiles_files(file_paths)
        else:
            validated_files, errors = file_paths, []

        # Display validated files
        for file_path in validated_files:
            path_obj = Path(file_path)

            # Create list item with file info
            item_text = f"{path_obj.name}"

            # Add file size info (terabyte-aware)
            try:
                size_bytes = path_obj.stat().st_size
                if size_bytes >= 1024**4:  # Terabytes
                    size_str = f"{size_bytes / (1024**4):.2f} TB"
                elif size_bytes >= 1024**3:  # Gigabytes
                    size_str = f"{size_bytes / (1024**3):.2f} GB"
                elif size_bytes >= 1024**2:  # Megabytes
                    size_str = f"{size_bytes / (1024**2):.1f} MB"
                else:
                    size_str = f"{size_bytes / 1024:.1f} KB"
                item_text += f" ({size_str})"
            except:
                pass

            # Check for auxiliary files
            aux_files = self._find_auxiliary_files(path_obj)
            if aux_files:
                item_text += f" + {len(aux_files)} aux"

            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, file_path)
            item.setToolTip(f"Full path: {file_path}")

            # Color code by file type
            if path_obj.suffix.lower() in [".jp2", ".j2k"]:
                item.setBackground(QColor("#f3e5f5"))  # Light purple for JPEG2000
            elif path_obj.suffix.lower() in [".tif", ".tiff"]:
                item.setBackground(QColor("#e3f2fd"))  # Light blue for GeoTIFF
            elif path_obj.suffix.lower() == ".mbtiles":
                item.setBackground(QColor("#e8f5e8"))  # Light green for MBTiles

            self.selected_files_list.addItem(item)

        # Update validation status
        total_selected = len(validated_files)
        total_errors = len(errors)

        if total_errors == 0 and total_selected > 0:
            self.validation_status_label.setText(
                f"✓ {total_selected} file(s) ready for ingestion ({format_name})"
            )
            self.validation_status_label.setStyleSheet("""
                QLabel {
                    padding: 5px;
                    border-radius: 3px;
                    font-size: 11px;
                    font-weight: 600;
                    background: #d4edda;
                    color: #155724;
                }
            """)
        elif total_errors > 0:
            error_summary = f"✗ {total_errors} validation error(s):"
            for error in errors[:3]:  # Show first 3 errors
                error_summary += f"\n  • {error}"
            if len(errors) > 3:
                error_summary += f"\n  ... and {len(errors) - 3} more"

            self.validation_status_label.setText(error_summary)
            self.validation_status_label.setStyleSheet("""
                QLabel {
                    padding: 5px;
                    border-radius: 3px;
                    font-size: 11px;
                    font-weight: 600;
                    background: #f8d7da;
                    color: #721c24;
                }
            """)
        else:
            self.validation_status_label.clear()

    def _validate_geotiff_files(
        self, file_paths: list[str]
    ) -> tuple[list[str], list[str]]:
        """Validate GeoTIFF files with optional world files (.tfw)."""
        from pathlib import Path

        validated = []
        errors = []
        world_files = set()  # Track world files

        # First pass: identify world files
        for file_path in file_paths:
            path_obj = Path(file_path)
            if path_obj.suffix.lower() in [".tfw", ".tifw"]:
                world_files.add(path_obj.stem)

        # Second pass: validate GeoTIFF files
        for file_path in file_paths:
            path_obj = Path(file_path)

            if not path_obj.exists():
                errors.append(f"{path_obj.name}: File not found")
                continue

            suffix_lower = path_obj.suffix.lower()

            # Skip world files in validation (they're auxiliary)
            if suffix_lower in [".tfw", ".tifw"]:
                continue

            if suffix_lower not in [".tif", ".tiff"]:
                errors.append(
                    f"{path_obj.name}: Not a GeoTIFF file (.tif/.tiff required)"
                )
                continue

            validated.append(file_path)

            # Log if world file is present (optional but useful for positioning)
            if path_obj.stem in world_files:
                self.log(f"  ✓ {path_obj.name} has world file (.tfw)")

        return validated, errors

    def _validate_jp2_files(self, file_paths: list[str]) -> tuple[list[str], list[str]]:
        """Validate JPEG2000 files with required .prj files and optional world files."""
        from pathlib import Path

        validated = []
        errors = []

        # Group JP2 files and check for matching .prj and world files
        jp2_files = {}
        prj_files = set()
        world_files = set()  # Track world files (.j2w, .jgw, etc.)

        for file_path in file_paths:
            path_obj = Path(file_path)

            if not path_obj.exists():
                errors.append(f"{path_obj.name}: File not found")
                continue

            suffix_lower = path_obj.suffix.lower()

            if suffix_lower in [".jp2", ".j2k"]:
                jp2_files[path_obj.stem] = file_path
            elif suffix_lower == ".prj":
                prj_files.add(path_obj.stem)
            elif suffix_lower in [".j2w", ".jgw"]:  # World files for JPEG2000
                world_files.add(path_obj.stem)

        # Validate JP2+PRJ pairs (PRJ is required, world files are optional)
        for stem, jp2_path in jp2_files.items():
            if stem in prj_files:
                validated.append(jp2_path)
                # Log if world file is also present (optional but useful)
                if stem in world_files:
                    self.log(f"  ✓ {Path(jp2_path).name} has .prj and world file")
                else:
                    self.log(
                        f"  ✓ {Path(jp2_path).name} has .prj (world file optional)"
                    )
            else:
                errors.append(f"{Path(jp2_path).name}: Missing required .prj file")

        # Check for orphaned .prj files
        for stem in prj_files:
            if stem not in jp2_files:
                errors.append(f"{stem}.prj: No matching JPEG2000 file (.jp2 or .j2k) found")

        # Note: World files without matching JP2 are silently ignored (they're optional)

        return validated, errors

    def _validate_mbtiles_files(
        self, file_paths: list[str]
    ) -> tuple[list[str], list[str]]:
        """Validate MBTiles files."""
        from pathlib import Path

        validated = []
        errors = []

        for file_path in file_paths:
            path_obj = Path(file_path)

            if not path_obj.exists():
                errors.append(f"{path_obj.name}: File not found")
                continue

            if path_obj.suffix.lower() != ".mbtiles":
                errors.append(
                    f"{path_obj.name}: Not an MBTiles file (.mbtiles required)"
                )
                continue

            validated.append(file_path)

        return validated, errors

    def get_selected_files(self) -> list[str]:
        """Get list of selected file paths."""
        files = []
        for i in range(self.selected_files_list.count()):
            item = self.selected_files_list.item(i)
            if item:
                file_path = item.data(Qt.ItemDataRole.UserRole)
                if file_path:
                    files.append(file_path)
        return files

    def _on_delete_asset_clicked(self, asset_data: dict) -> None:
        """Handle delete asset button click with confirmation."""
        from qtpy.QtWidgets import QMessageBox

        filename = asset_data.get("file_name", "Unknown")
        file_path = asset_data.get("file_path", "Unknown")

        # Show confirmation dialog
        reply = QMessageBox.question(
            self,
            "Delete Asset",
            f"Are you sure you want to delete this asset?\n\n"
            f"File: {filename}\n"
            f"Path: {file_path}\n\n"
            f"This will remove the asset from the database and catalog.\n"
            f"The original file will remain on disk.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Emit signal to controller for actual deletion
            self.asset_delete_requested.emit(asset_data)

    def clear_selected_files(self) -> None:
        """Clear all selected files."""
        self.selected_files_list.clear()

    def _group_files_intelligently(self, file_paths: list[str]) -> list[str]:
        """Group files intelligently, automatically including .prj files for JP2s."""
        from pathlib import Path

        result_files = []
        processed_files = set()

        for file_path in file_paths:
            if file_path in processed_files:
                continue

            path_obj = Path(file_path)
            result_files.append(file_path)
            processed_files.add(file_path)

            # For JP2 files, automatically include matching .prj file if not already selected
            if path_obj.suffix.lower() in [".jp2", ".j2k"]:
                prj_file = path_obj.with_suffix(".prj")
                if prj_file.exists() and str(prj_file) not in file_paths:
                    # Don't add .prj to result_files, just mark as processed
                    # The ingestion system will handle auxiliary files automatically
                    processed_files.add(str(prj_file))

        return result_files

    def _find_auxiliary_files(self, primary_file: Path) -> list[Path]:
        """Find auxiliary files for a primary raster file."""
        aux_files = []
        base_name = primary_file.stem
        parent_dir = primary_file.parent

        # Common auxiliary file extensions
        aux_extensions = [".prj", ".tfw", ".jgw", ".aux.xml", ".xml", ".wld"]

        for ext in aux_extensions:
            aux_file = parent_dir / f"{base_name}{ext}"
            if aux_file.exists() and aux_file != primary_file:
                aux_files.append(aux_file)

        return aux_files

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
        if hasattr(self, "_refreshing_assets") and self._refreshing_assets:
            return  # Prevent recursive calls

        self._refreshing_assets = True

        try:
            # Force a complete table reset to ensure no cached data persists
            self.uploaded_assets_list.clear()
            self.uploaded_assets_list.setRowCount(0)
            self.uploaded_assets_list.setColumnCount(4)  # #, File Name, Added, Delete
            self.uploaded_assets_list.setHorizontalHeaderLabels(
                ["#", "File Name", "Added", "Delete"]
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
                # Show waiting message in Type column
                waiting_item = QTableWidgetItem("Waiting for API...")
                waiting_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                waiting_item.setForeground(QColor("#666666"))  # Gray text
                self.uploaded_assets_list.setItem(0, 1, waiting_item)

                # Clear other columns
                for col in [0, 2, 3]:  # Simplified columns
                    empty_item = QTableWidgetItem("")
                    self.uploaded_assets_list.setItem(0, col, empty_item)
                return

            try:
                # Force a fresh API call without any caching
                assets = self.api_client.list_assets()

                if not assets:
                    self.uploaded_assets_list.setRowCount(1)
                    # Show a centered "No assets" message
                    no_assets_item = QTableWidgetItem("No assets ingested yet")
                    no_assets_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    no_assets_item.setForeground(QColor("#666666"))  # Gray text
                    no_assets_item.setToolTip(
                        "The database has been cleared or no assets have been ingested yet"
                    )
                    self.uploaded_assets_list.setItem(
                        0, 1, no_assets_item
                    )  # Show in Type column

                    # Clear other columns
                    for col in [0, 2, 3]:  # Simplified columns
                        empty_item = QTableWidgetItem("")
                        self.uploaded_assets_list.setItem(0, col, empty_item)

                    # Log the empty state for debugging
                    print(
                        "DEBUG: refresh_uploaded_assets - No assets returned from API"
                    )
                    return

                # Sort by ingest timestamp (most recent first) - API already returns in this order
                # but we ensure it here for consistency
                sorted_assets = sorted(
                    assets, key=lambda a: a.get("created_at", ""), reverse=True
                )

                # Log the asset count for debugging
                print(
                    f"DEBUG: refresh_uploaded_assets - Found {len(sorted_assets)} assets from API"
                )

                for row, asset in enumerate(sorted_assets):
                    filename = str(asset.get("file_name") or "Unknown")
                    timestamp = asset.get("created_at")
                    kind = str(asset.get("kind") or "Unknown").upper()
                    formatted_date = self._format_asset_created_at(timestamp)

                    self.uploaded_assets_list.insertRow(row)

                    # Serial number (reverse order: latest first gets highest number)
                    serial_number = len(sorted_assets) - row
                    number_item = QTableWidgetItem(str(serial_number))
                    number_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    number_item.setData(
                        Qt.ItemDataRole.UserRole, asset
                    )  # Store asset data
                    number_item.setToolTip(f"Asset #{serial_number}: {filename}")
                    self.uploaded_assets_list.setItem(row, 0, number_item)

                    # File Name (no color coding - plain text only)
                    name_item = QTableWidgetItem(filename)
                    name_item.setToolTip(f"{kind}: {filename}")
                    self.uploaded_assets_list.setItem(row, 1, name_item)

                    # Upload date (no highlighting)
                    date_item = QTableWidgetItem(formatted_date)
                    date_item.setToolTip(f"Uploaded: {formatted_date}")
                    self.uploaded_assets_list.setItem(row, 2, date_item)

                    # Add delete button
                    delete_btn = QPushButton("🗑️")
                    delete_btn.setObjectName("assetDeleteButton")
                    delete_btn.setToolTip(f"Delete asset: {filename}")
                    delete_btn.setFixedSize(28, 22)
                    delete_btn.setStyleSheet("""
                        QPushButton#assetDeleteButton {
                            background: #ffebee;
                            color: #c62828;
                            border: 1px solid #ef9a9a;
                            border-radius: 2px;
                            font-weight: bold;
                        }
                        QPushButton#assetDeleteButton:hover {
                            background: #ffcdd2;
                            border: 1px solid #e57373;
                        }
                        QPushButton#assetDeleteButton:pressed {
                            background: #ef5350;
                            color: white;
                        }
                    """)

                    # Store asset data in button for deletion
                    delete_btn.setProperty("asset_data", asset)
                    delete_btn.clicked.connect(
                        lambda checked=False, asset_data=asset: (
                            self._on_delete_asset_clicked(asset_data)
                        )
                    )

                    self.uploaded_assets_list.setCellWidget(row, 3, delete_btn)

            except Exception as e:
                # Clear everything and show error message
                self.uploaded_assets_list.clear()
                self.uploaded_assets_list.setRowCount(1)
                self.uploaded_assets_list.setColumnCount(4)  # Simplified columns
                self.uploaded_assets_list.setHorizontalHeaderLabels(
                    ["#", "Type", "Added", "Delete"]
                )

                # Ensure header text is visible and properly formatted
                header = self.uploaded_assets_list.horizontalHeader()
                header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
                header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
                header.setStretchLastSection(False)
                header.setMinimumSectionSize(60)

                # Show error message in the Type column
                error_item = QTableWidgetItem(f"Error: {str(e)}")
                error_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                error_item.setForeground(QColor("#cc0000"))  # Red text for errors
                error_item.setToolTip(
                    "Click 'Refresh Catalog' to retry after fixing the issue"
                )
                self.uploaded_assets_list.setItem(0, 1, error_item)

                # Clear the other columns for this error row
                for col in [0, 2, 3]:  # Simplified columns
                    empty_item = QTableWidgetItem("")
                    self.uploaded_assets_list.setItem(0, col, empty_item)

        finally:
            # Reset the refreshing flag to allow future refreshes
            self._refreshing_assets = False

    def _on_refresh_catalog_clicked(self) -> None:
        """Handle refresh catalog button click - refreshes without clearing caches to prevent loops."""
        import time

        # Prevent rapid successive refreshes
        if hasattr(self, "_last_refresh_time"):
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
            if timestamp.endswith("Z"):
                asset_time = datetime.fromisoformat(timestamp[:-1] + "+00:00")
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
            self.browse_files_btn,
            self.clear_selection_btn,
            self.ingest_btn,
            self.assets_refresh_btn,
            self.refresh_assets_btn,
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

    def _create_table_drop_handler(self):
        """Create a custom drop event handler for drag-and-drop reordering."""
        table = self.search_results_table
        original_drop_event = table.dropEvent
        original_drag_enter = table.dragEnterEvent
        original_drag_move = table.dragMoveEvent
        original_start_drag = table.startDrag

        # Store captured data at class level so it persists across events
        self._drag_captured_data = []
        self._drag_source_row = None

        def custom_start_drag(supported_actions):
            """Capture data when drag STARTS (earliest possible moment).

            CRITICAL: We must capture ALL rows, not just selected rows.
            Qt will clear the dragged row's data during the drag operation,
            so we need to preserve everything before that happens.
            """
            print(f"\n{'=' * 80}")
            print(
                f"DEBUG: START DRAG - capturing ALL {table.rowCount()} rows NOW (earliest moment)!"
            )
            print(f"{'=' * 80}\n")

            # Clear previous capture
            self._drag_captured_data = []

            # Capture ALL rows (not just selected ones)
            for i in range(table.rowCount()):
                # Get all table items for this row
                file_item = table.item(i, 1)
                kind_item = table.item(i, 2)
                crs_item = table.item(i, 3)
                created_item = table.item(i, 4)

                # Capture visibility button state
                visibility_button = table.cellWidget(i, 5)
                is_visible = True
                if visibility_button:
                    # Get the visibility state from the button property
                    is_visible = visibility_button.property("is_visible")
                    if is_visible is None:
                        is_visible = True

                # Extract data from items
                if file_item:
                    file_path = file_item.data(Qt.ItemDataRole.UserRole)
                    file_name = file_item.text()
                    kind = kind_item.text() if kind_item else "Unknown"
                    crs = crs_item.text() if crs_item else "-"
                    created_at = created_item.text() if created_item else "-"

                    if file_path and file_name:
                        row_data = {
                            "file_name": file_name,
                            "file_path": file_path,
                            "kind": kind,
                            "crs": crs,
                            "created_at": created_at,
                            "is_visible": is_visible,
                            "original_row": i,
                        }
                        self._drag_captured_data.append(row_data)
                        print(
                            f"DEBUG: Captured row {i}: {file_name} - {file_path} (visible={is_visible})"
                        )
                    else:
                        print(f"WARNING: Row {i} missing file_path or file_name")
                else:
                    print(f"WARNING: Row {i} has no file_item")

            print(f"DEBUG: Captured {len(self._drag_captured_data)} rows at START DRAG")
            print(f"{'=' * 80}\n")

            selected_rows = (
                table.selectionModel().selectedRows() if table.selectionModel() else []
            )
            if selected_rows:
                self._drag_source_row = selected_rows[0].row()
            else:
                self._drag_source_row = table.currentRow()
            print(f"DEBUG: Drag source row = {self._drag_source_row}")

            # Call original handler to start the drag
            original_start_drag(supported_actions)

        def custom_drag_enter(event):
            # Just pass through - data already captured in startDrag
            print(
                f"DEBUG: Drag enter - using {len(self._drag_captured_data)} pre-captured rows from startDrag"
            )
            original_drag_enter(event)

        def custom_drag_move(event):
            # Just pass through
            original_drag_move(event)

        def custom_drop_event(event):
            print(f"\n{'=' * 80}")
            print(
                f"DEBUG: Drop event - using {len(self._drag_captured_data)} pre-captured rows"
            )
            print(f"{'=' * 80}\n")

            if not self._drag_captured_data:
                print("ERROR: No captured data available for reordering!")
                original_drop_event(event)
                return

            drop_index = table.indexAt(event.pos())
            drop_row = drop_index.row() if drop_index.isValid() else table.rowCount()
            indicator_pos = table.dropIndicatorPosition()
            if indicator_pos == QAbstractItemView.DropIndicatorPosition.BelowItem:
                drop_row += 1
            elif indicator_pos == QAbstractItemView.DropIndicatorPosition.OnViewport:
                drop_row = table.rowCount()

            source_row = self._drag_source_row
            if (
                source_row is None
                or source_row < 0
                or source_row >= len(self._drag_captured_data)
            ):
                source_row = table.currentRow()
            if (
                source_row is None
                or source_row < 0
                or source_row >= len(self._drag_captured_data)
            ):
                source_row = 0

            print(
                f"DEBUG: Drop target row = {drop_row} (indicator={indicator_pos}), source row = {source_row}"
            )

            reordered = list(self._drag_captured_data)
            moved = reordered.pop(source_row)
            if drop_row > source_row:
                drop_row -= 1
            if drop_row < 0:
                drop_row = 0
            if drop_row > len(reordered):
                drop_row = len(reordered)
            reordered.insert(drop_row, moved)

            event.acceptProposedAction()
            print(f"DEBUG: Drop completed, triggering reorder handler")
            self._on_search_results_reordered_with_data(
                self._drag_captured_data, forced_order=reordered
            )

        # Install all custom handlers
        table.startDrag = custom_start_drag  # CRITICAL: Capture at drag start
        table.dragEnterEvent = custom_drag_enter
        table.dragMoveEvent = custom_drag_move

        return custom_drop_event

    def _on_search_results_reordered_with_data(
        self, pre_drop_row_data: list[dict], forced_order: list[dict] | None = None
    ) -> None:
        """Handle drag-and-drop reordering using pre-captured data.

        CRITICAL: Qt's drag-and-drop corrupts table item data during the operation.
        We use pre-captured data to rebuild the table with the correct order.
        """
        print(f"\n{'=' * 80}")
        print(f"DEBUG: _on_search_results_reordered_with_data called!")
        print(f"{'=' * 80}\n")
        try:
            table = self.search_results_table
            if table.rowCount() == 0:
                print("DEBUG: Table is empty, returning")
                return

            print(f"DEBUG: Table has {table.rowCount()} rows")
            print(f"DEBUG: Using {len(pre_drop_row_data)} pre-captured rows")

            if not pre_drop_row_data:
                print(
                    "ERROR: No pre-drop data provided! Cannot reconstruct layer order."
                )
                return

            if forced_order is not None:
                print(f"DEBUG: Using forced order with {len(forced_order)} rows")
                table.setRowCount(0)
                table.setRowCount(len(forced_order))
                reordered_layers = []
                for i, row_data in enumerate(forced_order):
                    self._create_table_row(table, i, row_data)
                    reordered_layers.append(
                        {
                            "file_name": row_data["file_name"],
                            "file_path": row_data["file_path"],
                            "kind": row_data["kind"],
                            "crs": row_data["crs"],
                            "is_visible": row_data.get("is_visible", True),
                            "display_order": i,
                        }
                    )
                    print(
                        f"  Row {i} rebuilt: {row_data['file_name']} ({row_data['kind']}) visible={row_data.get('is_visible', True)}"
                    )
                table.viewport().update()
                self._force_table_text_colors(table)
                print(f"DEBUG: Extracted {len(reordered_layers)} layers")

                if len(reordered_layers) == 0:
                    print("ERROR: No layers extracted! Cannot proceed with reordering.")
                    return

                self._pending_reorder_data = reordered_layers
                self._layer_order_registry = {
                    str(layer.get("file_path") or "").replace("\\", "/"): {
                        "file_name": str(layer.get("file_name") or "-"),
                        "kind": str(layer.get("kind") or "-"),
                        "crs": str(layer.get("crs") or "-"),
                        "created_at": str(layer.get("created_at") or "-"),
                        "is_visible": bool(layer.get("is_visible", True)),
                        "order": int(layer.get("display_order", 0)),
                    }
                    for layer in reordered_layers
                    if layer.get("file_path")
                }
                print(f"DEBUG: Starting debounce timer (150ms)")
                self._reorder_debounce_timer.start(150)
                print(f"DEBUG: _on_search_results_reordered_with_data completed\n")
                return

            # Build a map of file_path -> full row data (use file_path as key for uniqueness)
            data_by_filepath = {}
            for row_data in pre_drop_row_data:
                data_by_filepath[row_data["file_path"]] = row_data

            print(f"DEBUG: Data map has {len(data_by_filepath)} unique file paths")

            # Try to extract the new order from existing table items after Qt's drop
            current_order = []
            table_corrupted = False

            for i in range(table.rowCount()):
                file_item = table.item(i, 1)
                if file_item:
                    file_path = file_item.data(Qt.ItemDataRole.UserRole)
                    if file_path and file_path in data_by_filepath:
                        current_order.append(file_path)
                        print(f"  Row {i} has valid file_path: {file_path}")
                    else:
                        print(f"  Row {i} has invalid/missing file_path: {file_path}")
                        table_corrupted = True
                        break
                else:
                    print(f"  Row {i} has no file_item")
                    table_corrupted = True
                    break

            # If Qt corrupted the table or we couldn't extract proper order, rebuild completely
            if table_corrupted or len(current_order) != len(pre_drop_row_data):
                print(
                    f"  Table corrupted or incomplete: extracted {len(current_order)} paths but expected {len(pre_drop_row_data)}"
                )
                print(
                    f"  Rebuilding table completely from pre-drop data in current order"
                )

                # Get the current row order by examining which rows are where
                # Qt moves rows but may clear data, so we need to infer the new order
                new_order = []

                # Try to match rows by position and any remaining data
                for i in range(min(table.rowCount(), len(pre_drop_row_data))):
                    # If we have some valid data, use it to match
                    if i < len(current_order):
                        new_order.append(current_order[i])
                    else:
                        # Fallback: use original order for remaining items
                        remaining_paths = [
                            data["file_path"]
                            for data in pre_drop_row_data
                            if data["file_path"] not in new_order
                        ]
                        if remaining_paths:
                            new_order.append(remaining_paths[0])

                # If we still don't have a complete order, use the original order
                if len(new_order) != len(pre_drop_row_data):
                    print(f"  Could not determine new order, using original order")
                    new_order = [data["file_path"] for data in pre_drop_row_data]

                # Clear and rebuild the table with the determined order
                table.setRowCount(0)
                table.setRowCount(len(new_order))

                reordered_layers = []
                for i, file_path in enumerate(new_order):
                    row_data = data_by_filepath[file_path]

                    # Create all table items from scratch with proper formatting
                    self._create_table_row(table, i, row_data)

                    # Add to reordered layers list
                    reordered_layers.append(
                        {
                            "file_name": row_data["file_name"],
                            "file_path": row_data["file_path"],
                            "kind": row_data["kind"],
                            "crs": row_data["crs"],
                            "is_visible": row_data.get("is_visible", True),
                            "display_order": i,
                        }
                    )

                    print(
                        f"  Row {i} rebuilt: {row_data['file_name']} ({row_data['kind']}) visible={row_data.get('is_visible', True)}"
                    )

                print(f"DEBUG: Table rebuilt with {len(reordered_layers)} rows")

            else:
                # Table items are intact, just update them to ensure consistency
                print(f"  Table intact: processing {len(current_order)} rows normally")

                reordered_layers = []
                for i, file_path in enumerate(current_order):
                    row_data = data_by_filepath[file_path]

                    # Update existing items to ensure correct data and formatting
                    self._update_table_row(table, i, row_data)

                    # Add to reordered layers list
                    reordered_layers.append(
                        {
                            "file_name": row_data["file_name"],
                            "file_path": row_data["file_path"],
                            "kind": row_data["kind"],
                            "crs": row_data["crs"],
                            "is_visible": row_data.get("is_visible", True),
                            "display_order": i,
                        }
                    )

                    print(
                        f"  Row {i} updated: {row_data['file_name']} ({row_data['kind']}) visible={row_data.get('is_visible', True)}"
                    )

            # Force table update to apply all changes
            table.viewport().update()

            # CRITICAL: Force text color refresh after table operations
            self._force_table_text_colors(table)

            print(f"DEBUG: Extracted {len(reordered_layers)} layers")

            if len(reordered_layers) == 0:
                print("ERROR: No layers extracted! Cannot proceed with reordering.")
                return

            # Store the reorder data and update the local order registry
            self._pending_reorder_data = reordered_layers
            self._layer_order_registry = {
                str(layer.get("file_path") or "").replace("\\", "/"): {
                    "file_name": str(layer.get("file_name") or "-"),
                    "kind": str(layer.get("kind") or "-"),
                    "crs": str(layer.get("crs") or "-"),
                    "created_at": str(layer.get("created_at") or "-"),
                    "is_visible": bool(layer.get("is_visible", True)),
                    "order": int(layer.get("display_order", 0)),
                }
                for layer in reordered_layers
                if layer.get("file_path")
            }
            print(f"DEBUG: Starting debounce timer (150ms)")
            self._reorder_debounce_timer.start(150)  # 150ms debounce
            print(f"DEBUG: _on_search_results_reordered_with_data completed\n")

        except Exception as e:
            print(f"ERROR: Failed to handle search results reordering: {e}")
            import traceback

            traceback.print_exc()

    def _create_table_row(
        self, table: QTableWidget, row_index: int, row_data: dict
    ) -> None:
        """Create a complete table row with proper formatting and event handlers."""
        # Drag handle (column 0)
        handle_item = QTableWidgetItem("⋮⋮")
        handle_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        handle_item.setToolTip(f"Layer order: {row_index + 1}")
        handle_item.setForeground(QBrush(QColor(102, 102, 102)))
        handle_item.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDragEnabled
            | Qt.ItemFlag.ItemIsDropEnabled
        )
        table.setItem(row_index, 0, handle_item)

        # File name (column 1)
        file_item = QTableWidgetItem(row_data["file_name"])
        file_item.setData(Qt.ItemDataRole.UserRole, row_data["file_path"])
        file_item.setForeground(QBrush(QColor(0, 0, 0)))
        file_item.setData(Qt.ItemDataRole.ForegroundRole, QBrush(QColor(0, 0, 0)))
        file_item.setTextAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        file_item.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDragEnabled
            | Qt.ItemFlag.ItemIsDropEnabled
        )
        table.setItem(row_index, 1, file_item)

        # Kind (column 2)
        kind_item = QTableWidgetItem(row_data["kind"])
        kind_item.setForeground(QBrush(QColor(0, 0, 0)))
        kind_item.setData(Qt.ItemDataRole.ForegroundRole, QBrush(QColor(0, 0, 0)))
        kind_item.setTextAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        kind_item.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDragEnabled
            | Qt.ItemFlag.ItemIsDropEnabled
        )
        table.setItem(row_index, 2, kind_item)

        # CRS (column 3)
        crs_item = QTableWidgetItem(row_data["crs"])
        crs_item.setForeground(QBrush(QColor(0, 0, 0)))
        crs_item.setData(Qt.ItemDataRole.ForegroundRole, QBrush(QColor(0, 0, 0)))
        crs_item.setTextAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        crs_item.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDragEnabled
            | Qt.ItemFlag.ItemIsDropEnabled
        )
        table.setItem(row_index, 3, crs_item)

        # Created date (column 4)
        created_item = QTableWidgetItem(row_data["created_at"])
        created_item.setForeground(QBrush(QColor(0, 0, 0)))
        created_item.setData(Qt.ItemDataRole.ForegroundRole, QBrush(QColor(0, 0, 0)))
        created_item.setTextAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        created_item.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDragEnabled
            | Qt.ItemFlag.ItemIsDropEnabled
        )
        table.setItem(row_index, 4, created_item)

        # Visibility button (column 5)
        is_visible = row_data.get("is_visible", True)
        visibility_button = QPushButton("👁" if is_visible else "👁‍🗨")
        visibility_button.setObjectName("searchVisibilityToggle")
        visibility_button.setToolTip("Hide from map" if is_visible else "Show on map")
        visibility_button.setFixedSize(32, 24)
        visibility_button.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid #d0d0d0;
                border-radius: 3px;
                font-size: 14px;
                padding: 0px;
            }
            QPushButton:hover {
                background: #f0f0f0;
                border: 1px solid #0066cc;
            }
            QPushButton:pressed {
                background: #e0e0e0;
            }
        """)
        visibility_button.setProperty("is_visible", is_visible)
        visibility_button.setProperty("file_path", row_data["file_path"])

        # Connect the click handler
        def make_toggle_handler(btn, path):
            def handler():
                current_visible = btn.property("is_visible")
                new_visible = not current_visible
                btn.setText("👁" if new_visible else "👁‍🗨")
                btn.setToolTip("Hide from map" if new_visible else "Show on map")
                btn.setProperty("is_visible", new_visible)
                # Emit signal to update map
                self.search_result_visibility_toggled.emit(path, new_visible)

            return handler

        visibility_button.clicked.connect(
            make_toggle_handler(visibility_button, row_data["file_path"])
        )
        table.setCellWidget(row_index, 5, visibility_button)

    def _update_table_row(
        self, table: QTableWidget, row_index: int, row_data: dict
    ) -> None:
        """Update an existing table row with correct data and formatting."""
        # Update existing items (they should be intact)
        file_item = table.item(row_index, 1)
        kind_item = table.item(row_index, 2)
        crs_item = table.item(row_index, 3)
        created_item = table.item(row_index, 4)
        visibility_button = table.cellWidget(row_index, 5)

        # Ensure all items have correct data and colors
        if file_item:
            file_item.setText(row_data["file_name"])
            file_item.setData(Qt.ItemDataRole.UserRole, row_data["file_path"])
            file_item.setForeground(QBrush(QColor(0, 0, 0)))
            file_item.setData(Qt.ItemDataRole.ForegroundRole, QBrush(QColor(0, 0, 0)))

        if kind_item:
            kind_item.setText(row_data["kind"])
            kind_item.setForeground(QBrush(QColor(0, 0, 0)))
            kind_item.setData(Qt.ItemDataRole.ForegroundRole, QBrush(QColor(0, 0, 0)))

        if crs_item:
            crs_item.setText(row_data["crs"])
            crs_item.setForeground(QBrush(QColor(0, 0, 0)))
            crs_item.setData(Qt.ItemDataRole.ForegroundRole, QBrush(QColor(0, 0, 0)))

        if created_item:
            created_item.setText(row_data["created_at"])
            created_item.setForeground(QBrush(QColor(0, 0, 0)))
            created_item.setData(
                Qt.ItemDataRole.ForegroundRole, QBrush(QColor(0, 0, 0))
            )

        if visibility_button:
            is_visible = row_data.get("is_visible", True)
            visibility_button.setText("👁" if is_visible else "👁‍🗨")
            visibility_button.setProperty("is_visible", is_visible)
            visibility_button.setProperty("file_path", row_data["file_path"])

    def _force_table_text_colors(self, table: QTableWidget) -> None:
        """Force black text colors on all table items to prevent visibility issues after drag operations."""
        try:
            for row in range(table.rowCount()):
                for col in range(
                    table.columnCount() - 1
                ):  # Skip last column (visibility button)
                    item = table.item(row, col)
                    if item:
                        # Force black text color
                        item.setForeground(QBrush(QColor(0, 0, 0)))
                        item.setData(
                            Qt.ItemDataRole.ForegroundRole, QBrush(QColor(0, 0, 0))
                        )
        except Exception as e:
            print(f"WARNING: Failed to force table text colors: {e}")

    def _process_pending_reorder(self) -> None:
        """Process the pending reorder operation after debounce delay."""
        print(f"\n{'=' * 80}")
        print(f"DEBUG: _process_pending_reorder called!")
        print(f"  _pending_reorder_data: {self._pending_reorder_data}")
        print(f"{'=' * 80}\n")

        if self._pending_reorder_data is None:
            print("DEBUG: No pending reorder data, returning")
            return

        try:
            # Emit signal to controller for real-time globe layer reordering
            if hasattr(self, "search_layers_reordered"):
                print(
                    f"DEBUG: Emitting search_layers_reordered signal with {len(self._pending_reorder_data)} layers"
                )
                self.search_layers_reordered.emit(self._pending_reorder_data)
                print(f"DEBUG: Signal emitted successfully")
            else:
                print("ERROR: search_layers_reordered signal not found!")

            self._pending_reorder_data = None
            print(f"DEBUG: _process_pending_reorder completed\n")

        except Exception as e:
            print(f"ERROR: Failed to process pending reorder: {e}")
            import traceback

            traceback.print_exc()
