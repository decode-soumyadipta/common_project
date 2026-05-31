from __future__ import annotations

from datetime import datetime

from qtpy.QtCore import Qt
from qtpy.QtGui import QColor, QBrush
from qtpy.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)


class ControlPanelSearchMixin:
    def _on_search_table_item_clicked(self, item: QTableWidgetItem) -> None:
        row = item.row()
        # Focus on click for any data column (0-3), ignoring action buttons (4, 5)
        if item.column() < 4:
            file_path = self.search_results_table.item(row, 1).data(Qt.ItemDataRole.UserRole)
            if file_path:
                self.asset_focus_requested.emit(file_path)

    def update_search_results(
        self, assets: list[dict], visibility_by_path: dict[str, bool] | None = None
    ) -> None:
        """Update search results table with proper ordering: Imagery first (top), then DEM (bottom)."""
        print(f"\n{'=' * 80}")
        print(f"DEBUG: update_search_results called with {len(assets)} assets")
        if visibility_by_path:
            print(f"DEBUG: Visibility map provided: {visibility_by_path}")
        else:
            print("DEBUG: No visibility map provided")
        print(f"{'=' * 80}\n")

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

        # Check if we can perform an in-place update of visibility to avoid table flicker
        can_update_in_place = False
        if self.search_results_table.rowCount() == len(sorted_assets):
            can_update_in_place = True
            for r, asset in enumerate(sorted_assets):
                path = str(asset.get("file_path") or "").replace("\\", "/")
                item = self.search_results_table.item(r, 1)
                if not item or item.data(Qt.ItemDataRole.UserRole) != path:
                    can_update_in_place = False
                    break

        if can_update_in_place:
            print("DEBUG: Performing in-place update of search results table")
            # Update summary text
            self.search_results_summary.setText(
                f"Matches: {total_matches} | DEM: {dem_count} | Imagery: {imagery_count} | Visible: {visible_count} | CRS: {crs_summary} | Latest: {latest_date}"
            )
            # Update buttons in-place
            for r, asset in enumerate(sorted_assets):
                path = str(asset.get("file_path") or "").replace("\\", "/")
                is_visible = visibility_map.get(path, False)
                container = self.search_results_table.cellWidget(r, 4)
                if container:
                    btn = container.findChild(QPushButton)
                    if btn:
                        btn.blockSignals(True)
                        btn.setText("👁" if is_visible else "👁‍🗨")
                        btn.setToolTip("Hide from map" if is_visible else "Show on map")
                        btn.setProperty("is_visible", is_visible)
                        btn.blockSignals(False)
            # Synchronize registry visibility state
            for path in self._layer_order_registry:
                if path in visibility_map:
                    self._layer_order_registry[path]["is_visible"] = visibility_map[path]
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
                # Existing entry: preserve its metadata and specific visibility unless overridden
                entry = self._layer_order_registry[path].copy()
                entry["order"] = idx
                if path in visibility_map:
                    entry["is_visible"] = visibility_map[path]
                new_registry[path] = entry
            else:
                # New entry: use provided visibility or default to False
                new_registry[path] = {
                    "file_name": str(asset.get("file_name") or "-"),
                    "kind": str(asset.get("kind") or "-"),
                    "crs": str(asset.get("crs") or "-"),
                    "created_at": self._format_search_created_at(asset.get("created_at")),
                    "is_visible": visibility_map.get(path, False),
                    "order": idx,
                }
        self._layer_order_registry = new_registry

        print("DEBUG: Sorted assets order:")
        for i, asset in enumerate(sorted_assets):
            kind = str(asset.get("kind") or "").upper()
            file_name = str(asset.get("file_name") or "-")
            print(f"  {i + 1}. {kind}: {file_name}")

        for asset in sorted_assets:
            row = self.search_results_table.rowCount()
            self.search_results_table.insertRow(row)

            file_name = str(asset.get("file_name") or "-")
            kind = str(asset.get("kind") or "-").upper()
            crs = str(asset.get("crs") or "-")
            file_path = str(asset.get("file_path") or "")

            # Normalize path for lookup (match controller's normalization)
            normalized_path = file_path.replace("\\", "/")
            is_visible = visibility_map.get(normalized_path, False)

            print(f"DEBUG: Creating row {row} for {kind} - {file_name}")

            # Create visibility toggle button with eye icons
            toggle_button = QPushButton(
                "👁" if is_visible else "👁‍🗨"
            )  # Eye / Eye with speech bubble (crossed)
            toggle_button.setObjectName("searchVisibilityToggle")
            toggle_button.setToolTip("Hide from map" if is_visible else "Show on map")
            toggle_button.setFixedSize(32, 24)
            toggle_button.setStyleSheet(
                """
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
            """
            )

            if not file_path:
                toggle_button.setEnabled(False)
                print("  Button disabled (no file path)")
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
                        print("\nDEBUG: Toggle button clicked!")
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

            self.search_results_table.setItem(row, 0, drag_handle_item)
            self.search_results_table.setItem(row, 1, file_item)
            self.search_results_table.setItem(row, 2, kind_item)
            self.search_results_table.setItem(row, 3, crs_item)
            toggle_container = QWidget()
            toggle_layout = QHBoxLayout(toggle_container)
            toggle_layout.setContentsMargins(0, 0, 0, 0)
            toggle_layout.setAlignment(Qt.AlignCenter)
            toggle_layout.addWidget(toggle_button)
            self.search_results_table.setCellWidget(row, 4, toggle_container)

            # Red delete button (QGIS style)
            delete_btn = QPushButton("\u2715")  # Multiplication X / Close cross
            delete_btn.setToolTip(f"Remove layer: {file_name}")
            delete_btn.setFixedSize(24, 24)
            delete_btn.setStyleSheet(
                """
                QPushButton {
                    background-color: #ffe5e5;
                    border: 1px solid #ff9999;
                    border-radius: 4px;
                    color: #cc0000;
                    font-weight: bold;
                    font-size: 14px;
                    padding: 0px;
                }
                QPushButton:hover {
                    background-color: #ffcccc;
                    border: 1px solid #ff4d4d;
                }
                QPushButton:pressed {
                    background-color: #ff9999;
                }
            """
            )
            delete_btn.setText("\u2715")  # Multiplication X / Close cross - feels like a delete icon
            
            # Using a custom icon if possible, but Unicode \u2715 is a safe red 'x' 
            # as often seen in QGIS for 'Remove Layer'
            
            delete_btn.clicked.connect(
                lambda checked, p=normalized_path: self.search_layer_delete_requested.emit(p)
            )
            
            delete_container = QWidget()
            delete_layout = QHBoxLayout(delete_container)
            delete_layout.setContentsMargins(0, 0, 0, 0)
            delete_layout.setAlignment(Qt.AlignCenter)
            delete_layout.addWidget(delete_btn)
            self.search_results_table.setCellWidget(row, 5, delete_container)

            # Force text color update after setting items (workaround for Qt palette issues)
            for col_idx, item in [
                (1, file_item),
                (2, kind_item),
                (3, crs_item),
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

            visibility_button = QPushButton("👁" if is_visible else "👁‍🗨")
            visibility_button.setObjectName("searchVisibilityToggle")
            visibility_button.setToolTip(
                "Hide from map" if is_visible else "Show on map"
            )
            visibility_button.setFixedSize(32, 24)
            visibility_button.setProperty("is_visible", is_visible)
            visibility_button.setProperty("layer_key", layer_key)

            def make_toggle_handler(btn, key):
                def handler():
                    current_visible = btn.property("is_visible")
                    new_visible = not current_visible
                    btn.setText("👁" if new_visible else "👁‍🗨")
                    btn.setToolTip(
                        "Hide from map" if new_visible else "Show on map"
                    )
                    btn.setProperty("is_visible", new_visible)
                    self.vector_layer_visibility_toggled.emit(key, new_visible)

                return handler

            visibility_button.clicked.connect(
                make_toggle_handler(visibility_button, layer_key)
            )
            self.vector_layers_table.setCellWidget(row, 2, visibility_button)

            delete_button = QPushButton("\u2715")  # Multiplication X / Close cross
            delete_button.setObjectName("vectorDeleteButton")
            delete_button.setToolTip(f"Remove layer: {label}")
            delete_button.setFixedSize(24, 24)
            delete_button.setStyleSheet(
                """
                QPushButton#vectorDeleteButton {
                    background-color: #ffe5e5;
                    border: 1px solid #ff9999;
                    border-radius: 4px;
                    color: #cc0000;
                    font-weight: bold;
                    font-size: 14px;
                    padding: 0px;
                }
                QPushButton#vectorDeleteButton:hover {
                    background-color: #ffcccc;
                    border: 1px solid #ff4d4d;
                }
                QPushButton#vectorDeleteButton:pressed {
                    background-color: #ff9999;
                }
            """
            )
            delete_button.setProperty("layer_key", layer_key)
            delete_button.clicked.connect(
                lambda checked=False, key=layer_key: (
                    self.vector_layer_delete_requested.emit(key)
                )
            )
            self.vector_layers_table.setCellWidget(row, 3, delete_button)

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
        labels = ["⋮⋮", "File", "Kind", "CRS", "View", "Delete"]
        if self.search_results_table.columnCount() != len(labels):
            self.search_results_table.setColumnCount(len(labels))
        self.search_results_table.setHorizontalHeaderLabels(labels)
        self.search_results_table.horizontalHeader().setVisible(True)

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
        formatted = ControlPanelSearchMixin._format_search_created_at(value)
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
            print("DEBUG: Drop completed, triggering reorder handler")
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
        print("DEBUG: _on_search_results_reordered_with_data called!")
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
                print("DEBUG: Starting debounce timer (150ms)")
                self._reorder_debounce_timer.start(150)
                print("DEBUG: _on_search_results_reordered_with_data completed\n")
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
                    "  Rebuilding table completely from pre-drop data in current order"
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
                    print("  Could not determine new order, using original order")
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
            print("DEBUG: Starting debounce timer (150ms)")
            self._reorder_debounce_timer.start(150)  # 150ms debounce
            print("DEBUG: _on_search_results_reordered_with_data completed\n")

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

        # Visibility button (column 4)
        is_visible = row_data.get("is_visible", True)
        visibility_button = QPushButton("👁" if is_visible else "👁‍🗨")
        visibility_button.setObjectName("searchVisibilityToggle")
        visibility_button.setToolTip("Hide from map" if is_visible else "Show on map")
        visibility_button.setFixedSize(32, 24)
        visibility_button.setStyleSheet(
            """
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
        """
        )
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
        
        toggle_container = QWidget()
        toggle_layout = QHBoxLayout(toggle_container)
        toggle_layout.setContentsMargins(0, 0, 0, 0)
        toggle_layout.setAlignment(Qt.AlignCenter)
        toggle_layout.addWidget(visibility_button)
        table.setCellWidget(row_index, 4, toggle_container)

        # Red delete button (QGIS style) (column 5)
        delete_btn = QPushButton("\u2715")  # Multiplication X / Close cross
        delete_btn.setToolTip(f"Remove layer: {row_data['file_name']}")
        delete_btn.setFixedSize(24, 24)
        delete_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #ffe5e5;
                border: 1px solid #ff9999;
                border-radius: 4px;
                color: #cc0000;
                font-weight: bold;
                font-size: 14px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #ffcccc;
                border: 1px solid #ff4d4d;
            }
            QPushButton:pressed {
                background-color: #ff9999;
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
        delete_layout.setAlignment(Qt.AlignCenter)
        delete_layout.addWidget(delete_btn)
        table.setCellWidget(row_index, 5, delete_container)

    def _update_table_row(
        self, table: QTableWidget, row_index: int, row_data: dict
    ) -> None:
        """Update an existing table row with correct data and formatting."""
        # Update existing items (they should be intact)
        file_item = table.item(row_index, 1)
        kind_item = table.item(row_index, 2)
        crs_item = table.item(row_index, 3)
        # NOTE: column 4 is a cellWidget (visibility toggle), not a QTableWidgetItem

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
            # Recreate if missing (Qt drag-drop often clears cell widgets)
            is_visible = row_data.get("is_visible", True)
            toggle_button = QPushButton("👁" if is_visible else "👁‍🗨")
            toggle_button.setObjectName("searchVisibilityToggle")
            toggle_button.setToolTip("Hide from map" if is_visible else "Show on map")
            toggle_button.setFixedSize(32, 24)
            toggle_button.setStyleSheet(
                """
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
            """
            )
            toggle_button.setProperty("is_visible", is_visible)
            toggle_button.setProperty("file_path", row_data["file_path"])

            def make_toggle_handler(btn, path):
                def handler():
                    current_visible = btn.property("is_visible")
                    new_visible = not current_visible
                    btn.setText("👁" if new_visible else "👁‍🗨")
                    btn.setToolTip("Hide from map" if new_visible else "Show on map")
                    btn.setProperty("is_visible", new_visible)
                    self.search_result_visibility_toggled.emit(path, new_visible)
                return handler

            toggle_button.clicked.connect(
                make_toggle_handler(toggle_button, row_data["file_path"])
            )

            toggle_container = QWidget()
            toggle_layout = QHBoxLayout(toggle_container)
            toggle_layout.setContentsMargins(0, 0, 0, 0)
            toggle_layout.setAlignment(Qt.AlignCenter)
            toggle_layout.addWidget(toggle_button)
            table.setCellWidget(row_index, 4, toggle_container)
        else:
            visibility_button = visibility_widget.findChild(QPushButton)
            if not visibility_button:
                visibility_button = visibility_widget
            is_visible = row_data.get("is_visible", True)
            visibility_button.setText("👁" if is_visible else "👁‍🗨")
            visibility_button.setProperty("is_visible", is_visible)
            visibility_button.setProperty("file_path", row_data["file_path"])

        # Update or recreate delete button (column 5)
        delete_container = table.cellWidget(row_index, 5)
        if not delete_container:
            # Recreate if missing (Qt drag-drop often clears cell widgets)
            delete_btn = QPushButton("\u2715")
            delete_btn.setToolTip(f"Remove layer: {row_data['file_name']}")
            delete_btn.setFixedSize(24, 24)
            delete_btn.setStyleSheet(
                """
                QPushButton {
                    background-color: #ffe5e5;
                    border: 1px solid #ff9999;
                    border-radius: 4px;
                    color: #cc0000;
                    font-weight: bold;
                    font-size: 14px;
                    padding: 0px;
                }
                QPushButton:hover {
                    background-color: #ffcccc;
                    border: 1px solid #ff4d4d;
                }
                QPushButton:pressed {
                    background-color: #ff9999;
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
            delete_layout.setAlignment(Qt.AlignCenter)
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
            print(f"WARNING: Failed to force table text colors: {e}")

    def _process_pending_reorder(self) -> None:
        """Process the pending reorder operation after debounce delay."""
        print(f"\n{'=' * 80}")
        print("DEBUG: _process_pending_reorder called!")
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
                print("DEBUG: Signal emitted successfully")
            else:
                print("ERROR: search_layers_reordered signal not found!")

            self._pending_reorder_data = None
            print("DEBUG: _process_pending_reorder completed\n")

        except Exception as e:
            print(f"ERROR: Failed to process pending reorder: {e}")
            import traceback

            traceback.print_exc()
