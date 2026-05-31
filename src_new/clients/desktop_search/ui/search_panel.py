"""Search panel module for the Desktop Search Client.

Provides the SearchPanel widget containing:
- Point search (lat/lon coordinate input with buffer radius)
- Polygon search (draw AOI on map, then search)
- Search results table (drag-and-drop reorderable layer list)
- Vector layers table

Extracted from src/client_desktop/backend/control_panel.py.

Requirements: 7.2, 7.6
"""

from __future__ import annotations

import logging

from qtpy.QtCore import Qt, Signal, QTimer
from qtpy.QtGui import QColor, QPalette
from qtpy.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class SearchPanel(QWidget):
    """Panel providing spatial search controls and results display.

    Signals:
        search_result_visibility_toggled: Emitted when a result layer's
            visibility checkbox is toggled. Args: (file_path: str, visible: bool)
        search_layers_reordered: Emitted after drag-and-drop reorder.
            Args: (ordered_paths: list[str])
        search_layer_delete_requested: Emitted when a result layer delete
            button is clicked. Args: (file_path: str)
        vector_layer_visibility_toggled: Emitted when a vector layer
            visibility checkbox is toggled. Args: (file_path: str, visible: bool)
        vector_layer_delete_requested: Emitted when a vector layer delete
            button is clicked. Args: (file_path: str)
        point_search_requested: Emitted when the "Coordinate Search" button
            is clicked. Args: (lon: float, lat: float, buffer_m: int)
        polygon_search_requested: Emitted when the "Search" (polygon) button
            is clicked.
        draw_polygon_toggled: Emitted when the "Draw" toggle button changes.
            Args: (active: bool)
        finish_polygon_requested: Emitted when the "Finish" button is clicked.
        clear_geometry_requested: Emitted when the "Clear" button is clicked.
    """

    # Search result / layer signals
    search_result_visibility_toggled = Signal(str, bool)
    search_layers_reordered = Signal(list)
    search_layer_delete_requested = Signal(str)
    vector_layer_visibility_toggled = Signal(str, bool)
    vector_layer_delete_requested = Signal(str)

    # Search action signals
    point_search_requested = Signal(float, float, int)
    polygon_search_requested = Signal()
    draw_polygon_toggled = Signal(bool)
    finish_polygon_requested = Signal()
    clear_geometry_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layer_order_registry: dict[str, dict] = {}

        # Drag-and-drop reorder debounce
        self._reorder_debounce_timer = QTimer(self)
        self._reorder_debounce_timer.setSingleShot(True)
        self._reorder_debounce_timer.timeout.connect(self._process_pending_reorder)
        self._pending_reorder_data: list | None = None

        self._build_ui()
        self._connect_signals()

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        root.addWidget(self._build_search_box())
        root.addStretch()

    def _build_search_box(self) -> QGroupBox:
        """Build the 'Search Catalog' group box."""
        self.search_box = QGroupBox("Search Catalog")
        layout = QVBoxLayout(self.search_box)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)

        # ── Point search ──────────────────────────────────────────────── #
        layout.addWidget(QLabel("<b>Point Search</b>"))

        self.search_coord_lon = QDoubleSpinBox()
        self.search_coord_lon.setRange(-180.0, 180.0)
        self.search_coord_lon.setDecimals(6)
        self.search_coord_lon.setSingleStep(0.0001)
        self.search_coord_lon.setMinimumWidth(120)
        self.search_coord_lon.setMaximumWidth(145)

        self.search_coord_lat = QDoubleSpinBox()
        self.search_coord_lat.setRange(-90.0, 90.0)
        self.search_coord_lat.setDecimals(6)
        self.search_coord_lat.setSingleStep(0.0001)
        self.search_coord_lat.setMinimumWidth(120)
        self.search_coord_lat.setMaximumWidth(145)

        coord_row = QHBoxLayout()
        coord_row.setSpacing(6)
        coord_row.addWidget(QLabel("Lon:"))
        coord_row.addWidget(self.search_coord_lon, 1)
        coord_row.addWidget(QLabel("Lat:"))
        coord_row.addWidget(self.search_coord_lat, 1)
        layout.addLayout(coord_row)

        self.search_buffer_m = QSpinBox()
        self.search_buffer_m.setRange(0, 50_000)
        self.search_buffer_m.setValue(250)
        self.search_buffer_m.setMaximumWidth(145)

        buffer_row = QHBoxLayout()
        buffer_row.setSpacing(6)
        buffer_row.addWidget(QLabel("Buffer (m):"))
        buffer_row.addWidget(self.search_buffer_m)
        buffer_row.addStretch()
        layout.addLayout(buffer_row)

        self.search_point_btn = QPushButton("Coordinate Search")
        self.search_point_btn.setObjectName("searchPrimaryButton")
        self.search_point_btn.setToolTip(
            "Search around lon/lat using the configured buffer radius in metres."
        )
        self.search_point_btn.setMinimumHeight(24)
        self.search_point_btn.setMaximumHeight(28)

        point_actions_row = QHBoxLayout()
        point_actions_row.setSpacing(6)
        point_actions_row.addWidget(self.search_point_btn)
        point_actions_row.addStretch()
        layout.addLayout(point_actions_row)

        layout.addSpacing(6)

        # ── Polygon search ────────────────────────────────────────────── #
        layout.addWidget(QLabel("<b>Polygon Search</b>"))

        self.search_draw_polygon_btn = QPushButton("Draw")
        self.search_draw_polygon_btn.setCheckable(True)
        self.search_draw_polygon_btn.setToolTip("Start polygon drawing on the map.")

        self.search_finish_polygon_btn = QPushButton("Finish")
        self.search_finish_polygon_btn.setToolTip("Complete the active polygon.")

        self.search_clear_geometry_btn = QPushButton("Clear")
        self.search_clear_geometry_btn.setToolTip(
            "Clear the current polygon from the map."
        )

        self.search_from_draw_btn = QPushButton("Search")
        self.search_from_draw_btn.setObjectName("searchPrimaryButton")
        self.search_from_draw_btn.setToolTip(
            "Search catalog assets overlapping the drawn polygon."
        )

        for btn in (
            self.search_draw_polygon_btn,
            self.search_finish_polygon_btn,
            self.search_clear_geometry_btn,
            self.search_from_draw_btn,
        ):
            btn.setMinimumHeight(24)
            btn.setMaximumHeight(28)
            btn.setMinimumWidth(80)
            btn.setMaximumWidth(96)

        draw_row = QHBoxLayout()
        draw_row.setSpacing(4)
        draw_row.addWidget(self.search_draw_polygon_btn)
        draw_row.addWidget(self.search_finish_polygon_btn)
        draw_row.addWidget(self.search_clear_geometry_btn)
        draw_row.addWidget(self.search_from_draw_btn)
        draw_row.addStretch()
        layout.addLayout(draw_row)

        layout.addSpacing(8)

        # ── Search results ────────────────────────────────────────────── #
        layout.addWidget(QLabel("<b>Search Results</b>"))

        self.search_results_summary = QLabel(
            "Matches: 0 | DEM: 0 | Imagery: 0 | CRS: - | Latest: -"
        )
        self.search_results_summary.setStyleSheet("font-weight: 600; color: #2a2a2a;")
        layout.addWidget(self.search_results_summary)

        self.search_results_table = self._build_search_results_table()
        self._set_search_results_table_visible_rows(5)
        layout.addWidget(self.search_results_table)

        layout.addSpacing(6)

        # ── Vector layers ─────────────────────────────────────────────── #
        layout.addWidget(QLabel("<b>Vector Layers</b>"))
        self.vector_layers_table = self._build_vector_layers_table()
        layout.addWidget(self.vector_layers_table)

        return self.search_box

    def _build_search_results_table(self) -> QTableWidget:
        """Build the search results QTableWidget with drag-and-drop support."""
        # 6 columns: drag-handle | file | kind | CRS | visibility | delete
        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(
            ["⋮⋮", "File", "Kind", "CRS", "View", "Delete"]
        )

        # Drag-and-drop reordering
        table.setDragDropMode(QAbstractItemView.InternalMove)
        table.setDefaultDropAction(Qt.DropAction.MoveAction)
        table.setDragDropOverwriteMode(False)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setDragEnabled(True)
        table.setAcceptDrops(True)
        table.setAutoScroll(True)
        table.setAutoScrollMargin(35)
        table.setSortingEnabled(False)
        table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)

        # Install custom drop handler for reorder tracking
        table.dropEvent = self._create_table_drop_handler()
        table.itemClicked.connect(self._on_search_table_item_clicked)

        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # drag handle
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)            # file name
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)   # kind
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)   # CRS
        hdr.setSectionResizeMode(4, QHeaderView.Fixed)              # visibility btn
        hdr.setSectionResizeMode(5, QHeaderView.Fixed)              # delete btn

        table.setColumnWidth(0, 30)
        table.setColumnWidth(1, 220)
        table.setColumnWidth(2, 72)
        table.setColumnWidth(3, 90)
        table.setColumnWidth(4, 44)
        table.setColumnWidth(5, 36)

        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(30)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # All rows white; only the actively selected row turns blue.
        # macOS QMacStyle ignores CSS `background` on ::item and uses QPalette instead.
        # AlternatingRowColors=True + system palette = persistent blue on all odd rows.
        # Fix: disable alternating colors + set palette with fully opaque colors
        # (macOS ignores rgba alpha in palette, so use opaque hex values only).
        table.setAlternatingRowColors(False)
        table.setWordWrap(False)
        table.setTextElideMode(Qt.TextElideMode.ElideMiddle)

        palette = table.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))           # rows: white
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(255, 255, 255)) # alt rows: also white
        palette.setColor(QPalette.ColorRole.Highlight, QColor(204, 228, 255))     # selected: light blue
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))    # selected text: black
        palette.setColor(QPalette.ColorRole.Text, QColor(0, 0, 0))               # normal text: black
        table.setPalette(palette)

        table.setStyleSheet(
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
                color: #333333;
                font-weight: 600;
                padding: 4px 6px;
                border: none;
                border-right: 1px solid #d8d8d8;
                border-bottom: 1px solid #d0d0d0;
                font-size: 11px;
            }
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
        return table

    def _build_vector_layers_table(self) -> QTableWidget:
        """Build the vector layers QTableWidget."""
        table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels(["Layer", "CRS", "Vis", "Del"])
        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(22)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setStyleSheet(
            """
            QTableWidget {
                background: #ffffff;
                border: 1px solid #d0d0d0;
                border-radius: 3px;
                gridline-color: #f0f0f0;
                font-size: 11px;
            }
            QTableWidget::item { padding: 2px; }
            QTableWidget::item:selected { background: #e8f4ff; }
            QHeaderView::section {
                background: #f5f5f5;
                padding: 2px;
                border: none;
                border-right: 1px solid #d0d0d0;
                font-weight: 600;
                font-size: 11px;
            }
            """
        )
        return table

    # ------------------------------------------------------------------ #
    # Signal wiring                                                        #
    # ------------------------------------------------------------------ #

    def _connect_signals(self) -> None:
        self.search_point_btn.clicked.connect(self._on_point_search_clicked)
        self.search_from_draw_btn.clicked.connect(self.polygon_search_requested)
        self.search_draw_polygon_btn.toggled.connect(self.draw_polygon_toggled)
        self.search_finish_polygon_btn.clicked.connect(self.finish_polygon_requested)
        self.search_clear_geometry_btn.clicked.connect(self.clear_geometry_requested)

    def _on_point_search_clicked(self) -> None:
        self.point_search_requested.emit(
            self.search_coord_lon.value(),
            self.search_coord_lat.value(),
            self.search_buffer_m.value(),
        )

    # ------------------------------------------------------------------ #
    # Drag-and-drop helpers                                                #
    # ------------------------------------------------------------------ #

    def _create_table_drop_handler(self):
        """Return a custom dropEvent handler that tracks row reordering."""
        original_drop = QTableWidget.dropEvent

        def drop_handler(event) -> None:
            original_drop(self.search_results_table, event)
            self._schedule_reorder_emit()

        return drop_handler

    def _schedule_reorder_emit(self) -> None:
        self._reorder_debounce_timer.start(50)

    def _process_pending_reorder(self) -> None:
        """Collect current row order and emit search_layers_reordered."""
        paths: list[str] = []
        for row in range(self.search_results_table.rowCount()):
            item = self.search_results_table.item(row, 1)
            if item is not None:
                path = item.data(Qt.ItemDataRole.UserRole)
                if path:
                    paths.append(path)
        if paths:
            self.search_layers_reordered.emit(paths)

    def _on_search_table_item_clicked(self, item) -> None:
        """Handle clicks on the search results table (visibility toggle, etc.)."""
        # Subclasses or the controller can connect to the table's itemClicked
        # signal directly; this slot is a hook for future extension.
        pass

    # ------------------------------------------------------------------ #
    # Public helpers                                                       #
    # ------------------------------------------------------------------ #

    def _set_search_results_table_visible_rows(self, n: int) -> None:
        """Resize the search results table to show exactly *n* rows."""
        row_h = self.search_results_table.verticalHeader().defaultSectionSize()
        header_h = self.search_results_table.horizontalHeader().height()
        self.search_results_table.setFixedHeight(header_h + row_h * n + 4)

    def update_results_summary(
        self,
        matches: int = 0,
        dem: int = 0,
        imagery: int = 0,
        crs: str = "-",
        latest: str = "-",
    ) -> None:
        """Update the summary label above the results table."""
        self.search_results_summary.setText(
            f"Matches: {matches} | DEM: {dem} | Imagery: {imagery} "
            f"| CRS: {crs} | Latest: {latest}"
        )

    def set_coordinates(self, lon: float, lat: float) -> None:
        """Populate the lon/lat spin boxes (e.g. from a map click)."""
        self.search_coord_lon.setValue(lon)
        self.search_coord_lat.setValue(lat)
