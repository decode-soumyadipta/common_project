from __future__ import annotations

import logging
from datetime import UTC
from pathlib import Path

from qtpy.QtCore import Qt
from qtpy.QtGui import QColor
from qtpy.QtWidgets import (
    QHeaderView,
    QListWidgetItem,
    QPushButton,
    QTableWidgetItem,
)

_logger = logging.getLogger(__name__)


class ControlPanelIngestMixin:
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
            except OSError:
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
            self.validation_status_label.setStyleSheet(
                """
                QLabel {
                    padding: 5px;
                    border-radius: 3px;
                    font-size: 11px;
                    font-weight: 600;
                    background: #d4edda;
                    color: #155724;
                }
            """
            )
        elif total_errors > 0:
            error_summary = f"✗ {total_errors} validation error(s):"
            for error in errors[:3]:  # Show first 3 errors
                error_summary += f"\n  • {error}"
            if len(errors) > 3:
                error_summary += f"\n  ... and {len(errors) - 3} more"

            self.validation_status_label.setText(error_summary)
            self.validation_status_label.setStyleSheet(
                """
                QLabel {
                    padding: 5px;
                    border-radius: 3px;
                    font-size: 11px;
                    font-weight: 600;
                    background: #f8d7da;
                    color: #721c24;
                }
            """
            )
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
                    # Don't add .prj to result_files, just mark as processed The ingestion system will handle auxiliary files automatically
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
                    _logger.debug(
                        "DEBUG: refresh_uploaded_assets - No assets returned from API"
                    )
                    return

                # Sort by ingest timestamp (most recent first) - API already returns in this order but we ensure it here for consistency
                sorted_assets = sorted(
                    assets, key=lambda a: a.get("created_at", ""), reverse=True
                )

                # Log the asset count for debugging
                _logger.debug(
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
                    delete_btn.setStyleSheet(
                        """
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
                    """
                    )

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
                error_item = QTableWidgetItem(f"Error: {e!s}")
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

        # Just refresh the uploaded assets without clearing caches Cache clearing will be handled by the controller when needed
        self.refresh_uploaded_assets()

    def _is_recent_asset(self, timestamp: str | None) -> bool:
        """Check if an asset was created recently (within last hour)."""
        if not timestamp:
            return False
        try:
            from datetime import datetime, timedelta

            # Parse ISO timestamp
            if timestamp.endswith("Z"):
                asset_time = datetime.fromisoformat(timestamp[:-1] + "+00:00")
            else:
                asset_time = datetime.fromisoformat(timestamp)

            # Make timezone-aware if needed
            if asset_time.tzinfo is None:
                asset_time = asset_time.replace(tzinfo=UTC)

            now = datetime.now(UTC)
            return (now - asset_time) < timedelta(hours=1)
        except Exception:
            return False

    def append_ingest_detail(self, message: str) -> None:
        self.ingest_details.append(message)
