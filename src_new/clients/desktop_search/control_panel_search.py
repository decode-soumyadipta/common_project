from __future__ import annotations

import logging
from datetime import datetime

from qtpy.QtCore import QPointF, QSize, Qt
from qtpy.QtGui import QBrush, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from qtpy.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QWidget,
)

from typing import TYPE_CHECKING, Any, cast
if TYPE_CHECKING:
    from qtpy.QtCore import QTimer
    from qtpy.QtWidgets import QLabel

_logger = logging.getLogger(__name__)


class ControlPanelSearchMixin:
    # Type hints for Pyright static analysis
    search_results_table: QTableWidget
    search_results_summary: QLabel
    show_all_btn: QToolButton
    vector_layers_table: QTableWidget
    _reorder_debounce_timer: QTimer
    _pending_reorder_data: list | None
    
    # Signals (declared on the main class mixing this in)
    asset_focus_requested: Any
    search_result_visibility_toggled: Any
    search_results_visibility_batch_toggled: Any
    search_layer_delete_requested: Any
    vector_layer_visibility_toggled: Any
    vector_layer_delete_requested: Any
    search_layers_reordered: Any
    def _create_eye_icon(self, is_visible: bool, size: int = 16, color_hex: str = "#444444") -> QIcon:
        """Create a professional vector-drawn eye icon (and slashed eye for hidden state)."""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        color = QColor(color_hex)
        
        w = size * 0.85
        h = size * 0.45
        cx = size / 2.0
        cy = size / 2.0
        
        path = QPainterPath()
        path.moveTo(cx - w/2.0, cy)
        path.quadTo(cx, cy - h, cx + w/2.0, cy)
        path.quadTo(cx, cy + h, cx - w/2.0, cy)
        
        pen = QPen(color, 1.25)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawPath(path)
        
        # Iris
        iris_radius = size * 0.18
        painter.setBrush(color)
        painter.drawEllipse(QPointF(cx, cy), iris_radius, iris_radius)
        
        # Pupil/Highlight if visible
        if is_visible:
            painter.setBrush(Qt.GlobalColor.white)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(cx - iris_radius*0.3, cy - iris_radius*0.3), iris_radius*0.3, iris_radius*0.3)
        
        # Slashed line if hidden
        if not is_visible:
            slash_pen = QPen(QColor("#d32f2f"), 1.5)
            slash_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(slash_pen)
            painter.drawLine(
                int(cx - w/2.0 + 1), int(cy - h/2.0 - 1),
                int(cx + w/2.0 - 1), int(cy + h/2.0 + 1)
            )
            
        painter.end()
        return QIcon(pixmap)

    def _on_search_table_item_clicked(self, item: QTableWidgetItem) -> None:
        row = item.row()
        # Focus on click for any data column (0-3), ignoring action buttons (4, 5)
        if item.column() < 4:
            file_item = self.search_results_table.item(row, 1)
            if file_item is not None:
                file_path = file_item.data(Qt.ItemDataRole.UserRole)
                if file_path:
                    self.asset_focus_requested.emit(file_path)

    def _calculate_all_visible_state(self, assets: list[dict], visibility_map: dict[str, bool]) -> bool:
        if not assets:
            return False
        dem_vis = []
        img_vis = []
        for asset in assets:
            path = str(asset.get("file_path") or "").replace("\\", "/")
            kind = str(asset.get("kind") or "").lower()
            is_visible = visibility_map.get(path, False)
            if kind == "dem":
                dem_vis.append(is_visible)
            else:
                img_vis.append(is_visible)
        if img_vis and not all(img_vis):
            return False
        if dem_vis and not any(dem_vis):
            return False
        return True

    def _sort_and_order_assets(self, assets: list[dict]) -> list[dict]:
        # Sort assets: Imagery first (top of list), DEM last (bottom of list)
        def sort_key(asset):
            kind = str(asset.get("kind") or "").lower()
            created_at = self._search_created_at_sort_key(asset.get("created_at"))
            is_dem = 1 if kind == "dem" else 0
            return (is_dem, -created_at)

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
        return [assets_by_path[path] for path in ordered_paths] + remaining_assets

    def _update_search_summary(self, sorted_assets: list[dict], visibility_map: dict[str, bool]) -> None:
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
            if visibility_map.get(str(asset.get("file_path") or "").replace("\\", "/"), False)
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

    def _try_update_in_place(self, sorted_assets: list[dict], visibility_map: dict[str, bool]) -> bool:
        if self.search_results_table.rowCount() != len(sorted_assets):
            return False
        for r, asset in enumerate(sorted_assets):
            path = str(asset.get("file_path") or "").replace("\\", "/")
            item = self.search_results_table.item(r, 1)
            if not item or item.data(Qt.ItemDataRole.UserRole) != path:
                return False

        # Update buttons in-place
        for r, asset in enumerate(sorted_assets):
            path = str(asset.get("file_path") or "").replace("\\", "/")
            is_visible = visibility_map.get(path, False)
            container = self.search_results_table.cellWidget(r, 4)
            if container:
                btn = container.findChild(QPushButton)
                if btn:
                    btn.blockSignals(True)
                    btn.setIcon(self._create_eye_icon(is_visible))
                    btn.setIconSize(QSize(16, 16))
                    btn.setToolTip("Hide from map" if is_visible else "Show on map")
                    btn.setProperty("is_visible", is_visible)
                    btn.blockSignals(False)
        # Synchronize registry visibility state
        for path in self._layer_order_registry:
            if path in visibility_map:
                self._layer_order_registry[path]["is_visible"] = visibility_map[path]

        # Update header show_all_btn state
        all_visible = self._calculate_all_visible_state(sorted_assets, visibility_map)
        self._show_all_visible_state = all_visible
        self.show_all_btn.setIcon(self._create_eye_icon(all_visible))
        self.show_all_btn.setIconSize(QSize(14, 14))
        self.show_all_btn.setToolTip("Hide all results from map" if all_visible else "Show all results on map")
        return True

    def _create_search_toggle_button(self, is_visible: bool, file_path: str, normalized_path: str, visibility_map: dict[str, bool]) -> QPushButton:
        toggle_button = QPushButton()
        toggle_button.setIcon(self._create_eye_icon(is_visible))
        toggle_button.setIconSize(QSize(16, 16))
        toggle_button.setObjectName("searchVisibilityToggle")
        toggle_button.setToolTip("Hide from map" if is_visible else "Show on map")
        toggle_button.setFixedSize(32, 24)
        toggle_button.setStyleSheet(
            """
            QPushButton {
                background: transparent;
                border: 1px solid #d0d0d0;
                border-radius: 3px;
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
        """
        )

        if not file_path:
            toggle_button.setEnabled(False)
            _logger.debug("  Button disabled (no file path)")
        else:
            toggle_button.setProperty("is_visible", is_visible)
            toggle_button.setProperty("file_path", normalized_path)

            _logger.debug(
                f"  Button created: is_visible={is_visible}, path={normalized_path}"
            )

            def make_toggle_handler(btn, path):
                def handler():
                    current_visible = btn.property("is_visible")
                    new_visible = not current_visible
                    _logger.debug("\nDEBUG: Toggle button clicked!")
                    _logger.debug(f"  path: {path}")
                    _logger.debug(f"  current_visible: {current_visible}")
                    _logger.debug(f"  new_visible: {new_visible}")
                    # Update button immediately for responsive feel
                    btn.setIcon(self._create_eye_icon(new_visible))
                    btn.setToolTip(
                        "Hide from map" if new_visible else "Show on map"
                    )
                    btn.setProperty("is_visible", new_visible)
                    # Emit signal to update map
                    _logger.debug(
                        f"  Emitting signal: search_result_visibility_toggled({path}, {new_visible})"
                    )
                    self.search_result_visibility_toggled.emit(path, new_visible)

                    # Update header show_all_btn state immediately
                    temp_vis_map = {}
                    table = self.search_results_table
                    temp_assets = []
                    for r in range(table.rowCount()):
                        row_container = table.cellWidget(r, 4)
                        if row_container:
                            row_btn = row_container.findChild(QPushButton)
                            if row_btn:
                                row_path = row_btn.property("file_path")
                                row_is_visible = new_visible if row_path == path else bool(row_btn.property("is_visible"))
                                temp_vis_map[row_path] = row_is_visible
                                kind_item = table.item(r, 2)
                                row_kind = kind_item.text().lower() if kind_item is not None else ""
                                temp_assets.append({"file_path": row_path, "kind": row_kind})
                                
                    all_visible = self._calculate_all_visible_state(temp_assets, temp_vis_map)
                    self._show_all_visible_state = all_visible
                    self.show_all_btn.setIcon(self._create_eye_icon(all_visible))
                    self.show_all_btn.setIconSize(QSize(14, 14))
                    self.show_all_btn.setToolTip("Hide all results from map" if all_visible else "Show all results on map")

                return handler

            toggle_button.clicked.connect(
                make_toggle_handler(toggle_button, normalized_path)
            )
        return toggle_button

    def update_search_results(
        self, assets: list[dict], visibility_by_path: dict[str, bool] | None = None
    ) -> None:
        """Update search results table with proper ordering: Imagery first (top), then DEM (bottom)."""
        visibility_map = visibility_by_path or {}
        sorted_assets = self._sort_and_order_assets(assets)
        self._update_search_summary(sorted_assets, visibility_map)

        if self._try_update_in_place(sorted_assets, visibility_map):
            return

        self.search_results_table.setRowCount(0)
        self.search_results_table.setSortingEnabled(False)
        self._ensure_search_results_header()

        # Preserve existing metadata and visibility while updating orders
        new_registry = {}
        for idx, asset in enumerate(sorted_assets):
            path = str(asset.get("file_path") or "").replace("\\", "/")
            if not path:
                continue

            if path in self._layer_order_registry:
                entry = self._layer_order_registry[path].copy()
                entry["order"] = idx
                if path in visibility_map:
                    entry["is_visible"] = visibility_map[path]
                new_registry[path] = entry
            else:
                new_registry[path] = {
                    "file_name": str(asset.get("file_name") or "-"),
                    "kind": str(asset.get("kind") or "-"),
                    "crs": str(asset.get("crs") or "-"),
                    "created_at": self._format_search_created_at(asset.get("created_at")),
                    "is_visible": visibility_map.get(path, False),
                    "order": idx,
                }
        self._layer_order_registry = new_registry

        _logger.debug("DEBUG: Sorted assets order:")
        for i, asset in enumerate(sorted_assets):
            kind = str(asset.get("kind") or "").upper()
            file_name = str(asset.get("file_name") or "-")
            _logger.debug(f"  {i + 1}. {kind}: {file_name}")

        for asset in sorted_assets:
            row = self.search_results_table.rowCount()
            self.search_results_table.insertRow(row)

            file_name = str(asset.get("file_name") or "-")
            kind = str(asset.get("kind") or "-").upper()
            crs = str(asset.get("crs") or "-")
            file_path = str(asset.get("file_path") or "")

            normalized_path = file_path.replace("\\", "/")
            is_visible = visibility_map.get(normalized_path, False)

            _logger.debug(f"DEBUG: Creating row {row} for {kind} - {file_name}")

            toggle_button = self._create_search_toggle_button(is_visible, file_path, normalized_path, visibility_map)

            # Add drag handle in first column
            drag_handle_item = QTableWidgetItem("⋮⋮")
            drag_handle_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            drag_handle_item.setToolTip(f"Drag to reorder (Layer {row + 1})")
            drag_handle_item.setFlags(
                cast(
                    Any,
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsDragEnabled
                    | Qt.ItemFlag.ItemIsDropEnabled,
                )
            )
            drag_handle_item.setForeground(
                QBrush(QColor(102, 102, 102))
            )

            file_item = QTableWidgetItem(file_name)
            file_item.setData(
                Qt.ItemDataRole.UserRole, normalized_path
            )
            file_item.setForeground(QBrush(QColor(0, 0, 0)))
            file_item.setFlags(
                cast(
                    Any,
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsDragEnabled
                    | Qt.ItemFlag.ItemIsDropEnabled,
                )
            )

            kind_item = QTableWidgetItem(kind)
            kind_item.setForeground(QBrush(QColor(0, 0, 0)))
            kind_item.setFlags(
                cast(
                    Any,
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsDragEnabled
                    | Qt.ItemFlag.ItemIsDropEnabled,
                )
            )

            crs_item = QTableWidgetItem(crs)
            crs_item.setForeground(QBrush(QColor(0, 0, 0)))
            crs_item.setFlags(
                cast(
                    Any,
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsDragEnabled
                    | Qt.ItemFlag.ItemIsDropEnabled,
                )
            )

            self.search_results_table.setItem(row, 0, drag_handle_item)
            self.search_results_table.setItem(row, 1, file_item)
            self.search_results_table.setItem(row, 2, kind_item)
            self.search_results_table.setItem(row, 3, crs_item)
            toggle_container = QWidget()
            toggle_layout = QHBoxLayout(toggle_container)
            toggle_layout.setContentsMargins(0, 0, 0, 0)
            toggle_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            toggle_layout.addWidget(toggle_button)
            self.search_results_table.setCellWidget(row, 4, toggle_container)

            # Red delete button (QGIS style)
            delete_btn = QPushButton("\u2715")
            delete_btn.setToolTip(f"Remove layer: {file_name}")
            delete_btn.setFixedSize(18, 18)
            delete_btn.setStyleSheet(
                """
                QPushButton {
                    background: transparent;
                    border: none;
                    color: #cc0000;
                    font-weight: bold;
                    font-size: 13px;
                    margin: 0px;
                    padding: 0px;
                }
                QPushButton:hover {
                    color: #ff3333;
                }
                QPushButton:pressed {
                    color: #990000;
                }
            """
            )
            delete_btn.clicked.connect(
                lambda checked, p=normalized_path: self.search_layer_delete_requested.emit(p)
            )
            
            delete_container = QWidget()
            delete_layout = QHBoxLayout(delete_container)
            delete_layout.setContentsMargins(0, 0, 0, 0)
            delete_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            delete_layout.addWidget(delete_btn)
            self.search_results_table.setCellWidget(row, 5, delete_container)

            for _col_idx, item in [
                (1, file_item),
                (2, kind_item),
                (3, crs_item),
            ]:
                if item:
                    item.setData(
                        Qt.ItemDataRole.ForegroundRole, QBrush(QColor(0, 0, 0))
                    )

            _logger.debug(
                f"DEBUG: Created table items for row {row}: file={file_name}, kind={kind}, crs={crs}, path={normalized_path}"
            )

        all_visible = self._calculate_all_visible_state(sorted_assets, visibility_map)
        self._show_all_visible_state = all_visible
        self.show_all_btn.setIcon(self._create_eye_icon(all_visible))
        self.show_all_btn.setIconSize(QSize(14, 14))
        self.show_all_btn.setToolTip("Hide all results from map" if all_visible else "Show all results on map")

        _logger.debug(
            f"\nDEBUG: Search results table populated with {self.search_results_table.rowCount()} rows"
        )
        _logger.debug(f"DEBUG: update_search_results completed\n{'=' * 80}\n")

    def update_vector_layers(self, layers: list[dict]) -> None:
        self.vector_layers_table.setRowCount(0)
        self._ensure_vector_layers_header()

        for layer in layers:
            row = self.vector_layers_table.rowCount()
            self.vector_layers_table.insertRow(row)

            label = str(layer.get("label") or "Vector")
            source = str(layer.get("source") or "-")
            layer_key = str(layer.get("layer_key") or "")
            is_visible = bool(layer.get("is_visible", True))

            name_item = QTableWidgetItem(label)
            name_item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            self.vector_layers_table.setItem(row, 0, name_item)

            source_item = QTableWidgetItem(source)
            source_item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            self.vector_layers_table.setItem(row, 1, source_item)

            visibility_button = QPushButton()
            visibility_button.setIcon(self._create_eye_icon(is_visible))
            visibility_button.setIconSize(QSize(16, 16))
            visibility_button.setObjectName("searchVisibilityToggle")
            visibility_button.setToolTip(
                "Hide from map" if is_visible else "Show on map"
            )
            visibility_button.setFixedSize(32, 24)
            visibility_button.setStyleSheet(
                """
                QPushButton {
                    background: transparent;
                    border: 1px solid #d0d0d0;
                    border-radius: 3px;
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
                """
            )
            visibility_button.setProperty("is_visible", is_visible)
            visibility_button.setProperty("layer_key", layer_key)

            def make_toggle_handler(btn, key):
                def handler():
                    current_visible = btn.property("is_visible")
                    new_visible = not current_visible
                    btn.setIcon(self._create_eye_icon(new_visible))
                    btn.setToolTip(
                        "Hide from map" if new_visible else "Show on map"
                    )
                    btn.setProperty("is_visible", new_visible)
                    self.vector_layer_visibility_toggled.emit(key, new_visible)

                return handler

            visibility_button.clicked.connect(
                make_toggle_handler(visibility_button, layer_key)
            )
            
            toggle_container = QWidget()
            toggle_layout = QHBoxLayout(toggle_container)
            toggle_layout.setContentsMargins(0, 0, 0, 0)
            toggle_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            toggle_layout.addWidget(visibility_button)
            self.vector_layers_table.setCellWidget(row, 2, toggle_container)

            delete_button = QPushButton("\u2715")  # Multiplication X / Close cross
            delete_button.setObjectName("vectorDeleteButton")
            delete_button.setToolTip(f"Remove layer: {label}")
            delete_button.setFixedSize(18, 18)
            delete_button.setStyleSheet(
                """
                QPushButton#vectorDeleteButton {
                    background: transparent;
                    border: none;
                    color: #cc0000;
                    font-weight: bold;
                    font-size: 13px;
                    margin: 0px;
                    padding: 0px;
                }
                QPushButton#vectorDeleteButton:hover {
                    color: #ff3333;
                }
                QPushButton#vectorDeleteButton:pressed {
                    color: #990000;
                }
            """
            )
            delete_button.setProperty("layer_key", layer_key)
            delete_button.clicked.connect(
                lambda checked=False, key=layer_key: (
                    self.vector_layer_delete_requested.emit(key)
                )
            )
            
            delete_container = QWidget()
            delete_layout = QHBoxLayout(delete_container)
            delete_layout.setContentsMargins(0, 0, 0, 0)
            delete_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            delete_layout.addWidget(delete_button)
            self.vector_layers_table.setCellWidget(row, 3, delete_container)

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
        labels = ["⋮⋮", "File", "Kind", "CRS", "", "Delete"]
        if self.search_results_table.columnCount() != len(labels):
            self.search_results_table.setColumnCount(len(labels))
        self.search_results_table.setHorizontalHeaderLabels(labels)
        self.search_results_table.horizontalHeader().setVisible(True)

    def _setup_show_all_button(self) -> None:
        header = self.search_results_table.horizontalHeader()
        self.show_all_btn = QToolButton(header)
        self.show_all_btn.setIcon(self._create_eye_icon(False))
        self.show_all_btn.setIconSize(QSize(14, 14))
        self.show_all_btn.setToolTip("Show all results on map")
        self.show_all_btn.setFixedSize(20, 20)
        self.show_all_btn.setStyleSheet(
            """
            QToolButton {
                background: #f0f0f0;
                border: 1px solid #0066cc;
                border-radius: 3px;
                color: #0066cc;
                font-weight: bold;
                padding: 0px;
            }
            QToolButton:hover {
                background: #e0f0ff;
            }
            QToolButton:pressed {
                background: #cce5ff;
            }
            """
        )
        
        self._show_all_visible_state = False
        self.show_all_btn.clicked.connect(self._on_show_all_clicked)
        
        header.geometriesChanged.connect(self._update_show_all_button_geometry)
        header.sectionResized.connect(lambda idx, old, new: self._update_show_all_button_geometry())
        self._update_show_all_button_geometry()

    def _update_show_all_button_geometry(self) -> None:
        if not hasattr(self, "show_all_btn") or self.show_all_btn is None:
            return
        header = self.search_results_table.horizontalHeader()
        col_idx = 4
        if col_idx >= header.count():
            return
            
        x = header.sectionPosition(col_idx)
        w = header.sectionSize(col_idx)
        h = header.height()
        
        btn_w = 20
        btn_h = 20
        btn_x = x + (w - btn_w) // 2
        btn_y = (h - btn_h) // 2
        
        self.show_all_btn.setGeometry(btn_x, btn_y, btn_w, btn_h)

    def _on_show_all_clicked(self) -> None:
        self._show_all_visible_state = not self._show_all_visible_state
        self.show_all_btn.setIcon(self._create_eye_icon(self._show_all_visible_state))
        self.show_all_btn.setIconSize(QSize(14, 14))
        
        file_paths = []
        table = self.search_results_table
        for row in range(table.rowCount()):
            item = table.item(row, 1)
            if item:
                path = item.data(Qt.ItemDataRole.UserRole)
                if path:
                    file_paths.append(path)
                    
        for row in range(table.rowCount()):
            container = table.cellWidget(row, 4)
            if container:
                btn = container.findChild(QPushButton)
                if btn:
                    btn.setIcon(self._create_eye_icon(self._show_all_visible_state))
                    btn.setIconSize(QSize(16, 16))
                    btn.setToolTip("Hide from map" if self._show_all_visible_state else "Show on map")
                    btn.setProperty("is_visible", self._show_all_visible_state)
                    
        if file_paths:
            self.search_results_visibility_batch_toggled.emit(file_paths, self._show_all_visible_state)

    def _ensure_vector_layers_header(self) -> None:
        labels = ["Name", "Source", "View", "Delete"]
        if self.vector_layers_table.columnCount() != len(labels):
            self.vector_layers_table.setColumnCount(len(labels))
        self.vector_layers_table.setHorizontalHeaderLabels(labels)
        self.vector_layers_table.horizontalHeader().setVisible(True)

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
        parsed = ControlPanelSearchMixin._parse_search_created_at(value)
        if parsed is None:
            return 0.0
        try:
            return parsed.timestamp()
        except Exception:
            return 0.0

    @staticmethod
    def _format_asset_created_at(value: object) -> str:
        return ControlPanelSearchMixin._format_search_created_at(value)

    @staticmethod
    def _format_asset_cell_size(resolution_x: object, resolution_y: object) -> str:
        try:
            x_value = float(str(resolution_x))
            y_value = float(str(resolution_y))
        except (TypeError, ValueError):
            return "-"
        return f"{x_value:.4f} × {y_value:.4f}"

    @staticmethod
    def _format_asset_dimensions(width: object, height: object) -> str:
        try:
            width_value = int(float(str(width)))
            height_value = int(float(str(height)))
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
            _logger.debug(f"\n{'=' * 80}")
            _logger.debug(
                f"DEBUG: START DRAG - capturing ALL {table.rowCount()} rows NOW (earliest moment)!"
            )
            _logger.debug(f"{'=' * 80}\n")

            # Clear previous capture
            self._drag_captured_data = []

            # Capture ALL rows (not just selected ones)
            for i in range(table.rowCount()):
                # Get all table items for this row
                file_item = table.item(i, 1)
                kind_item = table.item(i, 2)
                crs_item = table.item(i, 3)

                # Capture visibility button state
                visibility_widget = table.cellWidget(i, 4)
                is_visible = True
                if visibility_widget:
                    visibility_button = visibility_widget.findChild(QPushButton)
                    if not visibility_button:
                        visibility_button = visibility_widget
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

                    if file_path and file_name:
                        row_data = {
                            "file_name": file_name,
                            "file_path": file_path,
                            "kind": kind,
                            "crs": crs,
                            "created_at": "-",
                            "is_visible": is_visible,
                            "original_row": i,
                        }
                        self._drag_captured_data.append(row_data)
                        _logger.debug(
                            f"DEBUG: Captured row {i}: {file_name} - {file_path} (visible={is_visible})"
                        )
                    else:
                        _logger.debug(f"WARNING: Row {i} missing file_path or file_name")
                else:
                    _logger.debug(f"WARNING: Row {i} has no file_item")

            _logger.debug(f"DEBUG: Captured {len(self._drag_captured_data)} rows at START DRAG")
            _logger.debug(f"{'=' * 80}\n")

            selected_rows = (
                table.selectionModel().selectedRows() if table.selectionModel() else []
            )
            if selected_rows:
                self._drag_source_row = selected_rows[0].row()
            else:
                self._drag_source_row = table.currentRow()
            _logger.debug(f"DEBUG: Drag source row = {self._drag_source_row}")

            # Call original handler to start the drag
            original_start_drag(supported_actions)

        def custom_drag_enter(event):
            # Just pass through - data already captured in startDrag
            _logger.debug(
                f"DEBUG: Drag enter - using {len(self._drag_captured_data)} pre-captured rows from startDrag"
            )
            original_drag_enter(event)

        def custom_drag_move(event):
            # Smooth auto-scrolling during drag operations
            pos = event.pos()
            margin = 35
            viewport = table.viewport()
            scrollbar = table.verticalScrollBar()
            if viewport and scrollbar and scrollbar.isVisible():
                val = scrollbar.value()
                vh = viewport.height()
                if pos.y() < margin and val > scrollbar.minimum():
                    # Progressive speed: faster the closer to the edge
                    step = max(4, int(8 * (1.0 - pos.y() / margin)))
                    scrollbar.setValue(max(scrollbar.minimum(), val - step))
                elif pos.y() > vh - margin and val < scrollbar.maximum():
                    over = pos.y() - (vh - margin)
                    step = max(4, int(8 * (over / margin)))
                    scrollbar.setValue(min(scrollbar.maximum(), val + step))
            original_drag_move(event)

        def custom_drop_event(event):
            _logger.debug(f"\n{'=' * 80}")
            _logger.debug(
                f"DEBUG: Drop event - using {len(self._drag_captured_data)} pre-captured rows"
            )
            _logger.debug(f"{'=' * 80}\n")

            if not self._drag_captured_data:
                _logger.debug("ERROR: No captured data available for reordering!")
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

            _logger.debug(
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
            _logger.debug("DEBUG: Drop completed, triggering reorder handler")
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
        _logger.debug(f"\n{'=' * 80}")
        _logger.debug("DEBUG: _on_search_results_reordered_with_data called!")
        _logger.debug(f"{'=' * 80}\n")
        try:
            table = self.search_results_table
            if table.rowCount() == 0:
                _logger.debug("DEBUG: Table is empty, returning")
                return

            _logger.debug(f"DEBUG: Table has {table.rowCount()} rows")
            _logger.debug(f"DEBUG: Using {len(pre_drop_row_data)} pre-captured rows")

            if not pre_drop_row_data:
                _logger.debug(
                    "ERROR: No pre-drop data provided! Cannot reconstruct layer order."
                )
                return

            if forced_order is not None:
                _logger.debug(f"DEBUG: Using forced order with {len(forced_order)} rows")
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
                    _logger.debug(
                        f"  Row {i} rebuilt: {row_data['file_name']} ({row_data['kind']}) visible={row_data.get('is_visible', True)}"
                    )
                table.viewport().update()
                self._force_table_text_colors(table)
                _logger.debug(f"DEBUG: Extracted {len(reordered_layers)} layers")

                if len(reordered_layers) == 0:
                    _logger.debug("ERROR: No layers extracted! Cannot proceed with reordering.")
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
                _logger.debug("DEBUG: Starting debounce timer (150ms)")
                self._reorder_debounce_timer.start(150)
                _logger.debug("DEBUG: _on_search_results_reordered_with_data completed\n")
                return

            # Build a map of file_path -> full row data (use file_path as key for uniqueness)
            data_by_filepath = {}
            for row_data in pre_drop_row_data:
                data_by_filepath[row_data["file_path"]] = row_data

            _logger.debug(f"DEBUG: Data map has {len(data_by_filepath)} unique file paths")

            # Try to extract the new order from existing table items after Qt's drop
            current_order = []
            table_corrupted = False

            for i in range(table.rowCount()):
                file_item = table.item(i, 1)
                if file_item:
                    file_path = file_item.data(Qt.ItemDataRole.UserRole)
                    if file_path and file_path in data_by_filepath:
                        current_order.append(file_path)
                        _logger.debug(f"  Row {i} has valid file_path: {file_path}")
                    else:
                        _logger.debug(f"  Row {i} has invalid/missing file_path: {file_path}")
                        table_corrupted = True
                        break
                else:
                    _logger.debug(f"  Row {i} has no file_item")
                    table_corrupted = True
                    break

            # If Qt corrupted the table or we couldn't extract proper order, rebuild completely
            if table_corrupted or len(current_order) != len(pre_drop_row_data):
                _logger.debug(
                    f"  Table corrupted or incomplete: extracted {len(current_order)} paths but expected {len(pre_drop_row_data)}"
                )
                _logger.debug(
                    "  Rebuilding table completely from pre-drop data in current order"
                )

                # Get the current row order by examining which rows are where Qt moves rows but may clear data, so we need to infer the new order
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
                    _logger.debug("  Could not determine new order, using original order")
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

                    _logger.debug(
                        f"  Row {i} rebuilt: {row_data['file_name']} ({row_data['kind']}) visible={row_data.get('is_visible', True)}"
                    )

                _logger.debug(f"DEBUG: Table rebuilt with {len(reordered_layers)} rows")

            else:
                # Table items are intact, just update them to ensure consistency
                _logger.debug(f"  Table intact: processing {len(current_order)} rows normally")

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

                    _logger.debug(
                        f"  Row {i} updated: {row_data['file_name']} ({row_data['kind']}) visible={row_data.get('is_visible', True)}"
                    )

            # Force table update to apply all changes
            table.viewport().update()

            # CRITICAL: Force text color refresh after table operations
            self._force_table_text_colors(table)

            _logger.debug(f"DEBUG: Extracted {len(reordered_layers)} layers")

            if len(reordered_layers) == 0:
                _logger.debug("ERROR: No layers extracted! Cannot proceed with reordering.")
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
            _logger.debug("DEBUG: Starting debounce timer (150ms)")
            self._reorder_debounce_timer.start(150)  # 150ms debounce
            _logger.debug("DEBUG: _on_search_results_reordered_with_data completed\n")

        except Exception as e:
            _logger.debug(f"ERROR: Failed to handle search results reordering: {e}")
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
            cast(
                Any,
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsDragEnabled
                | Qt.ItemFlag.ItemIsDropEnabled,
            )
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
            cast(
                Any,
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsDragEnabled
                | Qt.ItemFlag.ItemIsDropEnabled,
            )
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
            cast(
                Any,
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsDragEnabled
                | Qt.ItemFlag.ItemIsDropEnabled,
            )
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
            cast(
                Any,
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsDragEnabled
                | Qt.ItemFlag.ItemIsDropEnabled,
            )
        )
        table.setItem(row_index, 3, crs_item)

        # Visibility button (column 4)
        is_visible = row_data.get("is_visible", True)
        visibility_button = QPushButton()
        visibility_button.setIcon(self._create_eye_icon(is_visible))
        visibility_button.setIconSize(QSize(16, 16))
        visibility_button.setObjectName("searchVisibilityToggle")
        visibility_button.setToolTip("Hide from map" if is_visible else "Show on map")
        visibility_button.setFixedSize(32, 24)
        visibility_button.setStyleSheet(
            """
            QPushButton {
                background: transparent;
                border: 1px solid #d0d0d0;
                border-radius: 3px;
                padding: 0px;
            }
            QPushButton:hover {
                background: #f0f0f0;
                border: 1px solid #0066cc;
            }
            QPushButton:pressed {
                background: #e0e0e0;
            }
        """
        )
        visibility_button.setProperty("is_visible", is_visible)
        visibility_button.setProperty("file_path", row_data["file_path"])

        # Connect the click handler
        def make_toggle_handler(btn, path):
            def handler():
                current_visible = btn.property("is_visible")
                new_visible = not current_visible
                btn.setIcon(self._create_eye_icon(new_visible))
                btn.setToolTip("Hide from map" if new_visible else "Show on map")
                btn.setProperty("is_visible", new_visible)
                # Emit signal to update map
                self.search_result_visibility_toggled.emit(path, new_visible)

            return handler

        visibility_button.clicked.connect(
            make_toggle_handler(visibility_button, row_data["file_path"])
        )
        
        toggle_container = QWidget()
        toggle_layout = QHBoxLayout(toggle_container)
        toggle_layout.setContentsMargins(0, 0, 0, 0)
        toggle_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        toggle_layout.addWidget(visibility_button)
        table.setCellWidget(row_index, 4, toggle_container)

        # Red delete button (QGIS style) (column 5)
        delete_btn = QPushButton("\u2715")  # Multiplication X / Close cross
        delete_btn.setToolTip(f"Remove layer: {row_data['file_name']}")
        delete_btn.setFixedSize(18, 18)
        delete_btn.setStyleSheet(
            """
            QPushButton {
                background: transparent;
                border: none;
                color: #cc0000;
                font-weight: bold;
                font-size: 13px;
                margin: 0px;
                padding: 0px;
            }
            QPushButton:hover {
                color: #ff3333;
            }
            QPushButton:pressed {
                color: #990000;
            }
        """
        )
        
        path = str(row_data["file_path"]).replace("\\", "/")
        delete_btn.clicked.connect(
            lambda checked, p=path: self.search_layer_delete_requested.emit(p)
        )
        
        delete_container = QWidget()
        delete_layout = QHBoxLayout(delete_container)
        delete_layout.setContentsMargins(0, 0, 0, 0)
        delete_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        delete_layout.addWidget(delete_btn)
        table.setCellWidget(row_index, 5, delete_container)

    def _create_row_visibility_button(self, row_index: int, row_data: dict, table: QTableWidget) -> QPushButton:
        is_visible = row_data.get("is_visible", True)
        toggle_button = QPushButton()
        toggle_button.setIcon(self._create_eye_icon(is_visible))
        toggle_button.setIconSize(QSize(16, 16))
        toggle_button.setObjectName("searchVisibilityToggle")
        toggle_button.setToolTip("Hide from map" if is_visible else "Show on map")
        toggle_button.setFixedSize(32, 24)
        toggle_button.setStyleSheet(
            """
            QPushButton {
                background: transparent;
                border: 1px solid #d0d0d0;
                border-radius: 3px;
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
        """
        )
        toggle_button.setProperty("is_visible", is_visible)
        toggle_button.setProperty("file_path", row_data["file_path"])

        def make_toggle_handler(btn, path):
            def handler():
                current_visible = btn.property("is_visible")
                new_visible = not current_visible
                btn.setIcon(self._create_eye_icon(new_visible))
                btn.setToolTip("Hide from map" if new_visible else "Show on map")
                btn.setProperty("is_visible", new_visible)
                self.search_result_visibility_toggled.emit(path, new_visible)
            return handler

        toggle_button.clicked.connect(
            make_toggle_handler(toggle_button, row_data["file_path"])
        )
        return toggle_button

    def _create_row_delete_button(self, row_data: dict) -> QPushButton:
        delete_btn = QPushButton("\u2715")
        delete_btn.setToolTip(f"Remove layer: {row_data['file_name']}")
        delete_btn.setFixedSize(18, 18)
        delete_btn.setStyleSheet(
            """
            QPushButton {
                background: transparent;
                border: none;
                color: #cc0000;
                font-weight: bold;
                font-size: 13px;
                margin: 0px;
                padding: 0px;
            }
            QPushButton:hover {
                color: #ff3333;
            }
            QPushButton:pressed {
                color: #990000;
            }
        """
        )
        path = str(row_data["file_path"]).replace("\\", "/")
        delete_btn.clicked.connect(
            lambda checked, p=path: self.search_layer_delete_requested.emit(p)
        )
        return delete_btn

    def _update_table_row(
        self, table: QTableWidget, row_index: int, row_data: dict
    ) -> None:
        """Update an existing table row with correct data and formatting."""
        # Update existing items (they should be intact)
        file_item = table.item(row_index, 1)
        kind_item = table.item(row_index, 2)
        crs_item = table.item(row_index, 3)

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

        # Update or recreate visibility button (column 4)
        visibility_widget = table.cellWidget(row_index, 4)
        if not visibility_widget:
            toggle_button = self._create_row_visibility_button(row_index, row_data, table)
            toggle_container = QWidget()
            toggle_layout = QHBoxLayout(toggle_container)
            toggle_layout.setContentsMargins(0, 0, 0, 0)
            toggle_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            toggle_layout.addWidget(toggle_button)
            table.setCellWidget(row_index, 4, toggle_container)
        else:
            visibility_button = visibility_widget.findChild(QPushButton)
            if not visibility_button and isinstance(visibility_widget, QPushButton):
                visibility_button = visibility_widget
            if isinstance(visibility_button, QPushButton):
                is_visible = row_data.get("is_visible", True)
                visibility_button.setIcon(self._create_eye_icon(is_visible))
                visibility_button.setIconSize(QSize(16, 16))
                visibility_button.setProperty("is_visible", is_visible)
                visibility_button.setProperty("file_path", row_data["file_path"])

        # Update or recreate delete button (column 5)
        delete_container = table.cellWidget(row_index, 5)
        if not delete_container:
            delete_btn = self._create_row_delete_button(row_data)
            delete_container = QWidget()
            delete_layout = QHBoxLayout(delete_container)
            delete_layout.setContentsMargins(0, 0, 0, 0)
            delete_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            delete_layout.addWidget(delete_btn)
            table.setCellWidget(row_index, 5, delete_container)

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
            _logger.debug(f"WARNING: Failed to force table text colors: {e}")

    def _process_pending_reorder(self) -> None:
        """Process the pending reorder operation after debounce delay."""
        _logger.debug(f"\n{'=' * 80}")
        _logger.debug("DEBUG: _process_pending_reorder called!")
        _logger.debug(f"  _pending_reorder_data: {self._pending_reorder_data}")
        _logger.debug(f"{'=' * 80}\n")

        if self._pending_reorder_data is None:
            _logger.debug("DEBUG: No pending reorder data, returning")
            return

        try:
            # Emit signal to controller for real-time globe layer reordering
            if hasattr(self, "search_layers_reordered"):
                _logger.debug(
                    f"DEBUG: Emitting search_layers_reordered signal with {len(self._pending_reorder_data)} layers"
                )
                self.search_layers_reordered.emit(self._pending_reorder_data)
                _logger.debug("DEBUG: Signal emitted successfully")
            else:
                _logger.debug("ERROR: search_layers_reordered signal not found!")

            self._pending_reorder_data = None
            _logger.debug("DEBUG: _process_pending_reorder completed\n")

        except Exception as e:
            _logger.debug(f"ERROR: Failed to process pending reorder: {e}")
            import traceback

            traceback.print_exc()
