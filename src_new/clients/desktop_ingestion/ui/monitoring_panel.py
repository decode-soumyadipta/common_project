"""Monitoring panel for the Desktop Ingestion Client.

This module provides a PySide6 widget that displays:
- Upload progress for multiple files (parallel multi-threaded)
- Ingestion status polling
- Uploaded asset catalog with metadata (tags, description)
- Real-time activity log

The panel communicates with the Ingestion Service via the
``IngestionApiClient`` to track upload and processing status.

Requirements: 7.1, 7.3, 7.5, 7.6
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from qtpy.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from qtpy.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src_new.clients.desktop_ingestion.api_client import (
    IngestionApiClient,
    UploadResponse,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- Parallel Upload Infrastructure ---------------------------------------------------------------------------


class _UploadSignals(QObject):
    """Signals emitted by a single file upload task.

    These are QObject-based because QRunnable cannot emit signals directly.
    """
    file_completed = Signal(str, str, str, str)  # file_path, raster_id, status, message
    error = Signal(str, str)  # file_path, error_message
    finished = Signal()  # emitted always (success or failure)


class SingleFileUploadTask(QRunnable):
    """QRunnable that uploads ONE file to the Ingestion Service.

    Designed to run in a QThreadPool so that multiple files upload in parallel
    without blocking the main Qt thread.  Includes one automatic retry on failure.
    """

    def __init__(
        self,
        api_client: IngestionApiClient,
        file_path: Path,
        tags: list[str],
        description: str = "",
    ) -> None:
        super().__init__()
        self.api_client = api_client
        self.file_path = file_path
        self.tags = tags
        self.description = description
        self.signals = _UploadSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        """Execute the upload with one retry on failure."""
        max_attempts = 2
        last_error: Optional[Exception] = None

        for attempt in range(1, max_attempts + 1):
            try:
                # Prepare metadata dict
                metadata: dict = {}
                if self.tags:
                    metadata["tags"] = self.tags
                if self.description:
                    metadata["description"] = self.description

                # Look for sidecar files (.prj, .j2w, .tfw, .jgw) next to raster
                for suffix in [".prj", ".j2w", ".tfw", ".jgw"]:
                    sidecar_path = self.file_path.with_suffix(suffix)
                    if sidecar_path.exists():
                        try:
                            metadata[f"sidecar_{suffix.replace('.', '')}"] = (
                                sidecar_path.read_text().strip()
                            )
                            logger.info(
                                "Found sidecar %s for %s", suffix, self.file_path.name
                            )
                        except Exception as exc:
                            logger.warning(
                                "Failed to read sidecar %s: %s", sidecar_path, exc
                            )

                response: UploadResponse = self.api_client.upload_file(
                    self.file_path, extra_metadata=metadata, timeout=600.0
                )

                self.signals.file_completed.emit(
                    str(self.file_path),
                    response.raster_id,
                    response.status,
                    response.message,
                )
                self.signals.finished.emit()
                return  # success — exit

            except Exception as exc:
                last_error = exc
                if attempt < max_attempts:
                    logger.warning(
                        "Upload attempt %d failed for %s: %s — retrying...",
                        attempt,
                        self.file_path.name,
                        exc,
                    )
                else:
                    logger.exception(
                        "Upload failed after %d attempts for %s",
                        max_attempts,
                        self.file_path,
                    )

        # All retries exhausted
        self.signals.error.emit(str(self.file_path), str(last_error))
        self.signals.finished.emit()


class MonitoringPanel(QWidget):
    """Monitoring panel for tracking ingestion progress and viewing uploaded assets.

    Provides:
    - Parallel upload progress tracking with real-time status updates
    - Ingestion status polling for processing files
    - Uploaded asset catalog with tags & description display
    - Activity log for debugging and monitoring

    Requirements: 7.1, 7.3, 7.5, 7.6
    """

    def __init__(
        self, api_client: IngestionApiClient, parent: QWidget | None = None
    ) -> None:
        """Initialize the monitoring panel.

        Args:
            api_client: API client for communicating with the Ingestion Service.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.api_client = api_client
        self._active_uploads: dict[str, str] = {}  # file_path -> raster_id
        self._suppress_check_signals = False

        # Parallel upload tracking
        self._upload_pool = QThreadPool.globalInstance()
        # Use at most 4 threads (or cpu_count, whichever is smaller)
        max_threads = min(4, os.cpu_count() or 2)
        self._upload_pool.setMaxThreadCount(max_threads)
        self._upload_total = 0
        self._uploaded_count = 0
        self._failed_count = 0
        self._pending_tasks = 0

        self._build_ui()

        # Start status polling timer
        self._status_poll_timer = QTimer(self)
        self._status_poll_timer.timeout.connect(self._poll_ingestion_status)
        self._status_poll_timer.start(5000)  # Poll every 5 seconds

        QTimer.singleShot(0, self.refresh_assets)

        logger.debug(
            "MonitoringPanel initialized with %d parallel upload threads",
            max_threads,
        )

    # ------------------------------------------------------------------ UI Construction ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Construct and lay out all child widgets."""
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        # Upload progress group
        upload_group = self._create_upload_progress_group()
        root_layout.addWidget(upload_group)

        # Uploaded assets group
        assets_group = self._create_uploaded_assets_group()
        root_layout.addWidget(assets_group)

        # Activity log group
        log_group = self._create_activity_log_group()
        root_layout.addWidget(log_group)

    def _create_upload_progress_group(self) -> QGroupBox:
        """Create the upload progress group box."""
        group = QGroupBox("Upload Progress")
        group.setStyleSheet(
            """
            QGroupBox {
                font-weight: 600;
                font-size: 13px;
                color: #2d3748;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            """
        )

        layout = QFormLayout(group)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(8)

        # Progress bar
        self.upload_progress_bar = QProgressBar()
        self.upload_progress_bar.setRange(0, 100)
        self.upload_progress_bar.setValue(0)
        self.upload_progress_bar.setFormat("%p% (%v/%m)")
        layout.addRow("Overall Progress:", self.upload_progress_bar)

        # Status label
        self.upload_status_label = QLabel("Idle")
        self.upload_status_label.setStyleSheet("color: #6b7a8d;")
        layout.addRow("Status:", self.upload_status_label)

        # Current file label
        self.current_file_label = QLabel("-")
        self.current_file_label.setStyleSheet("color: #6b7a8d;")
        layout.addRow("Current File:", self.current_file_label)

        # Counts label
        self.upload_counts_label = QLabel("Uploaded: 0 | Failed: 0")
        self.upload_counts_label.setStyleSheet("color: #6b7a8d;")
        layout.addRow("Counts:", self.upload_counts_label)

        return group

    def _create_uploaded_assets_group(self) -> QGroupBox:
        """Create the uploaded assets group box."""
        group = QGroupBox("Uploaded Assets")
        group.setStyleSheet(
            """
            QGroupBox {
                font-weight: 600;
                font-size: 13px;
                color: #2d3748;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            """
        )

        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(8)

        search_row = QHBoxLayout()
        self.assets_search_input = QLineEdit()
        self.assets_search_input.setPlaceholderText("Search assets...")
        self.assets_search_input.setStyleSheet(
            """
            QLineEdit {
                padding: 6px 10px;
                border: 1px solid #cbd5e0;
                border-radius: 4px;
                background-color: #ffffff;
                font-size: 12px;
                color: #2d3748;
            }
            QLineEdit:focus {
                border: 1px solid #3182ce;
                outline: none;
            }
            """
        )
        self.assets_search_input.textChanged.connect(self._apply_asset_filter)
        search_row.addWidget(self.assets_search_input)
        layout.addLayout(search_row)

        controls_row = QHBoxLayout()
        self.select_all_checkbox = QCheckBox("Select All")
        # Use clicked(bool) — not stateChanged — to get a reliable bool and avoid int-vs-enum comparison bugs in PySide6/PyQt6.
        self.select_all_checkbox.clicked.connect(self._on_select_all_clicked)
        controls_row.addWidget(self.select_all_checkbox)
        controls_row.addStretch()
        self.delete_selected_btn = QPushButton("Delete Selected")
        self.delete_selected_btn.setEnabled(False)
        self.delete_selected_btn.clicked.connect(self._delete_selected_assets)
        controls_row.addWidget(self.delete_selected_btn)
        layout.addLayout(controls_row)

        # Assets table — columns: checkbox | Raster ID | Tags | Description | Uploaded At
        self.assets_table = QTableWidget(0, 5)
        self.assets_table.setHorizontalHeaderLabels(
            ["", "Raster ID", "Tags", "Description", "Uploaded At"]
        )
        self.assets_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.assets_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.assets_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.assets_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        self.assets_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents
        )
        self.assets_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.assets_table.setSelectionMode(
            QTableWidget.SelectionMode.ExtendedSelection
        )
        self.assets_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.assets_table.setAlternatingRowColors(True)
        self.assets_table.setMinimumHeight(200)
        self.assets_table.itemSelectionChanged.connect(
            self._on_asset_selection_changed
        )
        self.assets_table.itemChanged.connect(self._on_table_item_changed)
        self.assets_table.cellClicked.connect(self._on_cell_clicked)
        layout.addWidget(self.assets_table)

        # Refresh button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        refresh_btn = QPushButton("Refresh Assets")
        refresh_btn.clicked.connect(self.refresh_assets)
        btn_row.addWidget(refresh_btn)
        layout.addLayout(btn_row)

        return group

    def _create_activity_log_group(self) -> QGroupBox:
        """Create the activity log group box."""
        group = QGroupBox("Activity Log")
        group.setStyleSheet(
            """
            QGroupBox {
                font-weight: 600;
                font-size: 13px;
                color: #2d3748;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            """
        )

        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(8)

        # Activity log text edit
        self.activity_log = QTextEdit()
        self.activity_log.setReadOnly(True)
        self.activity_log.setMaximumHeight(150)
        self.activity_log.setStyleSheet(
            """
            QTextEdit {
                background: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 11px;
                padding: 4px;
            }
            """
        )
        layout.addWidget(self.activity_log)

        # Clear log button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        clear_btn = QPushButton("Clear Log")
        clear_btn.clicked.connect(self.activity_log.clear)
        btn_row.addWidget(clear_btn)
        layout.addLayout(btn_row)

        return group

    # ------------------------------------------------------------------ Public API ------------------------------------------------------------------

    def upload_files(
        self, files: list[Path], tags: list[str], description: str = ""
    ) -> None:
        """Start uploading files to the Ingestion Service in parallel.

        Uses a QThreadPool to run multiple uploads concurrently without
        blocking the main Qt thread.

        Args:
            files: List of file paths to upload.
            tags: Optional metadata tags to attach to uploads.
            description: Optional description for the upload batch.
        """
        if not files:
            return

        self._log_activity(
            f"Starting parallel upload of {len(files)} file(s) "
            f"({self._upload_pool.maxThreadCount()} threads)..."
        )

        # Reset progress
        self._upload_total = len(files)
        self._uploaded_count = 0
        self._failed_count = 0
        self._pending_tasks = len(files)

        self.upload_progress_bar.setMaximum(len(files))
        self.upload_progress_bar.setValue(0)
        self.upload_status_label.setText("Uploading...")
        self.upload_status_label.setStyleSheet("color: #2b6cb0; font-weight: 600;")
        self.current_file_label.setText(f"0/{len(files)} dispatched")
        self._update_counts()

        # Dispatch each file as an independent runnable task
        for i, file_path in enumerate(files):
            task = SingleFileUploadTask(
                self.api_client, file_path, tags, description
            )
            task.signals.file_completed.connect(self._on_file_completed)
            task.signals.error.connect(self._on_upload_error)
            task.signals.finished.connect(self._on_task_finished)
            self._upload_pool.start(task)
            logger.debug("Dispatched upload task %d/%d: %s", i + 1, len(files), file_path.name)

        self.current_file_label.setText(f"{len(files)}/{len(files)} dispatched")

    def refresh_assets(self) -> None:
        """Refresh the uploaded assets table."""
        self._log_activity("Refreshing uploaded assets...")
        self._update_assets_table()

    def refresh_all(self) -> None:
        """Refresh all data (assets and status)."""
        self.refresh_assets()
        self._poll_ingestion_status()

    # ------------------------------------------------------------------ Private Helpers — Parallel Upload Callbacks ------------------------------------------------------------------

    def _on_file_completed(
        self, file_path: str, raster_id: str, status: str, message: str
    ) -> None:
        """Handle file upload completion.

        Args:
            file_path: Path to the uploaded file.
            raster_id: Raster ID assigned by the Ingestion Service.
            status: Upload status (processing, cataloged, failed).
            message: Status message from the service.
        """
        self._uploaded_count += 1
        self.upload_progress_bar.setValue(self._uploaded_count + self._failed_count)
        self._update_counts()
        self._log_activity(
            f"✓ Uploaded: {Path(file_path).name} → {raster_id} ({status})"
        )

        # Track active upload for status polling
        self._active_uploads[file_path] = raster_id

        # Refresh from server so latest appears at the top
        self.refresh_assets()

    def _on_upload_error(self, file_path: str, error_message: str) -> None:
        """Handle upload error.

        Args:
            file_path: Path to the file that failed to upload.
            error_message: Error message describing the failure.
        """
        self._failed_count += 1
        self.upload_progress_bar.setValue(self._uploaded_count + self._failed_count)
        self._update_counts()
        self._log_activity(f"✗ Failed: {Path(file_path).name} - {error_message}")

    def _on_task_finished(self) -> None:
        """Called when any upload task (success or fail) finishes.

        Checks whether all tasks are done and updates final status.
        """
        self._pending_tasks -= 1
        if self._pending_tasks <= 0:
            self._on_all_completed()

    def _on_all_completed(self) -> None:
        """Handle completion of all uploads."""
        if self._failed_count > 0:
            if self._uploaded_count == 0:
                self.upload_status_label.setText("Failed")
                self.upload_status_label.setStyleSheet("color: #c53030; font-weight: 600;")
            else:
                self.upload_status_label.setText("Completed with errors")
                self.upload_status_label.setStyleSheet("color: #b7791f; font-weight: 600;")
        else:
            self.upload_status_label.setText("Completed")
            self.upload_status_label.setStyleSheet("color: #2d7a2d; font-weight: 600;")
        self.current_file_label.setText("-")
        self._log_activity(
            f"Upload batch completed: {self._uploaded_count} uploaded, "
            f"{self._failed_count} failed"
        )

    def _update_counts(self) -> None:
        """Update the upload counts label."""
        self.upload_counts_label.setText(
            f"Uploaded: {self._uploaded_count} | Failed: {self._failed_count}"
        )

    def _poll_ingestion_status(self) -> None:
        """Poll the Ingestion Service for status updates on active uploads."""
        if not self._active_uploads:
            return

        for file_path, raster_id in list(self._active_uploads.items()):
            try:
                status = self.api_client.get_status(raster_id, timeout=5.0)

                # Remove from active uploads if completed or failed
                if status.progress >= 1.0 or status.error:
                    del self._active_uploads[file_path]
                    if status.error:
                        self._log_activity(
                            f"✗ Ingestion failed for {raster_id}: {status.error}"
                        )
                    else:
                        self._log_activity(f"✓ Ingestion completed for {raster_id}")

            except Exception as exc:
                logger.debug("Failed to poll status for %s: %s", raster_id, exc)

    # ------------------------------------------------------------------ Private Helpers — Assets Table ------------------------------------------------------------------

    def _update_assets_table(self) -> None:
        """Refresh the assets table with current data from the server."""
        try:
            assets = self.api_client.list_assets(timeout=10.0)
        except Exception as exc:
            logger.debug("Failed to fetch asset list: %s", exc)
            return

        self._suppress_check_signals = True
        self.assets_table.setRowCount(0)
        for asset in assets:
            raster_id = str(asset.get("raster_id") or "")
            tags = str(asset.get("tags") or "")
            description = str(asset.get("description") or "")
            upload_date = self._format_upload_date(str(asset.get("upload_date") or ""))

            row = self.assets_table.rowCount()
            self.assets_table.insertRow(row)

            check_item = QTableWidgetItem()
            check_item.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
            )
            check_item.setCheckState(Qt.CheckState.Unchecked)
            self.assets_table.setItem(row, 0, check_item)
            self.assets_table.setItem(row, 1, QTableWidgetItem(raster_id))
            self.assets_table.setItem(row, 2, QTableWidgetItem(tags))
            self.assets_table.setItem(row, 3, QTableWidgetItem(description))
            self.assets_table.setItem(
                row, 4, QTableWidgetItem(upload_date)
            )

        self._suppress_check_signals = False
        self._sync_select_all_checkbox()
        self._update_delete_button_state()
        self._apply_asset_filter(self.assets_search_input.text())

        if assets:
            self._log_activity(f"Loaded {len(assets)} cataloged assets")

    def _on_select_all_clicked(self, checked: bool) -> None:
        """Toggle all row checkboxes when the 'Select All' checkbox is clicked.

        Uses the clicked(bool) signal so we get a plain bool — no int-vs-enum
        comparison issues.  If not all rows are currently checked we always
        check all; otherwise we uncheck all.
        """
        if self._suppress_check_signals:
            return
        total = self.assets_table.rowCount()
        all_checked = all(
            self.assets_table.item(row, 0) is not None
            and self.assets_table.item(row, 0).checkState() == Qt.CheckState.Checked
            for row in range(total)
        ) if total > 0 else False
        self._set_all_asset_checks(not all_checked)
        # Keep the visual state consistent with what we just did.
        self._suppress_check_signals = True
        self.select_all_checkbox.setChecked(not all_checked)
        self._suppress_check_signals = False
        self._update_delete_button_state()

    def _set_all_asset_checks(self, checked: bool) -> None:
        self._suppress_check_signals = True
        for row in range(self.assets_table.rowCount()):
            item = self.assets_table.item(row, 0)
            if item is not None:
                item.setCheckState(
                    Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
                )
                # Ensure row highlight matches check state
                for col in range(self.assets_table.columnCount()):
                    cell_item = self.assets_table.item(row, col)
                    if cell_item:
                        cell_item.setSelected(checked)
        self._suppress_check_signals = False

    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        if self._suppress_check_signals:
            return
        if item.column() == 0:
            self._suppress_check_signals = True
            row = item.row()
            is_checked = item.checkState() == Qt.CheckState.Checked
            for col in range(self.assets_table.columnCount()):
                cell_item = self.assets_table.item(row, col)
                if cell_item:
                    cell_item.setSelected(is_checked)
            self._suppress_check_signals = False
            self._sync_select_all_checkbox()
            self._update_delete_button_state()

    def _on_cell_clicked(self, row: int, column: int) -> None:
        if column == 0:
            return
        item = self.assets_table.item(row, 0)
        if item:
            self._suppress_check_signals = True
            is_checked = item.checkState() == Qt.CheckState.Checked
            new_state = Qt.CheckState.Unchecked if is_checked else Qt.CheckState.Checked
            item.setCheckState(new_state)
            for col in range(self.assets_table.columnCount()):
                cell_item = self.assets_table.item(row, col)
                if cell_item:
                    cell_item.setSelected(new_state == Qt.CheckState.Checked)
            self._suppress_check_signals = False
            self._sync_select_all_checkbox()
            self._update_delete_button_state()

    def _on_asset_selection_changed(self) -> None:
        """Tick checkboxes for newly highlighted rows only.

        Only adds checks — never clears checks from rows that were already
        checked via the checkbox column or via _on_cell_clicked.  This avoids
        a circular signal loop between itemSelectionChanged and itemChanged.
        """
        if self._suppress_check_signals:
            return
        self._suppress_check_signals = True
        selected_rows = {
            index.row()
            for index in self.assets_table.selectionModel().selectedRows()
        }
        for row in selected_rows:
            item = self.assets_table.item(row, 0)
            if item and item.checkState() != Qt.CheckState.Checked:
                item.setCheckState(Qt.CheckState.Checked)
                # Sync row highlight to the new checked state
                for col in range(self.assets_table.columnCount()):
                    cell_item = self.assets_table.item(row, col)
                    if cell_item:
                        cell_item.setSelected(True)
        self._suppress_check_signals = False
        self._sync_select_all_checkbox()
        self._update_delete_button_state()

    def _sync_select_all_checkbox(self) -> None:
        """Sync the 'Select All' visual state to the current row checks.

        Simple 2-state: Checked only when EVERY row is checked, Unchecked
        otherwise.  No tristate — avoids int-vs-enum comparison bugs.
        """
        if self._suppress_check_signals:
            return
        total = self.assets_table.rowCount()
        self._suppress_check_signals = True
        if total == 0:
            self.select_all_checkbox.setChecked(False)
            self._suppress_check_signals = False
            return
        checked_count = sum(
            1
            for row in range(total)
            if self.assets_table.item(row, 0) is not None
            and self.assets_table.item(row, 0).checkState() == Qt.CheckState.Checked
        )
        self.select_all_checkbox.setChecked(checked_count == total)
        self._suppress_check_signals = False

    def _update_delete_button_state(self) -> None:
        has_checked = any(
            self.assets_table.item(row, 0)
            and self.assets_table.item(row, 0).checkState()
            == Qt.CheckState.Checked
            for row in range(self.assets_table.rowCount())
        )
        has_selected = bool(self.assets_table.selectionModel().selectedRows())
        self.delete_selected_btn.setEnabled(has_checked or has_selected)

    def _format_upload_date(self, raw_value: str) -> str:
        if not raw_value:
            return "-"
        try:
            normalized = raw_value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            ist = parsed.astimezone(timezone(timedelta(hours=5, minutes=30)))
            return ist.strftime("%d/%m/%Y %H:%M")
        except Exception:
            return raw_value

    def _apply_asset_filter(self, text: str) -> None:
        query = text.strip().lower()
        for row in range(self.assets_table.rowCount()):
            if not query:
                self.assets_table.setRowHidden(row, False)
                continue
            haystack_parts = []
            for col in range(1, 5):
                item = self.assets_table.item(row, col)
                if item:
                    haystack_parts.append(item.text())
            haystack = " ".join(haystack_parts).lower()
            self.assets_table.setRowHidden(row, query not in haystack)

    def _get_selected_raster_ids(self) -> list[str]:
        checked_ids: list[str] = []
        for row in range(self.assets_table.rowCount()):
            item = self.assets_table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                rid_item = self.assets_table.item(row, 1)
                if rid_item and rid_item.text():
                    checked_ids.append(rid_item.text())

        if checked_ids:
            return checked_ids

        selected_rows = self.assets_table.selectionModel().selectedRows()
        for model_index in selected_rows:
            rid_item = self.assets_table.item(model_index.row(), 1)
            if rid_item and rid_item.text():
                checked_ids.append(rid_item.text())

        return checked_ids

    def _delete_selected_assets(self) -> None:
        raster_ids = self._get_selected_raster_ids()
        if not raster_ids:
            return

        confirm = QMessageBox.question(
            self,
            "Delete Assets",
            f"Delete {len(raster_ids)} selected asset(s)? This removes them from the catalog.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            result = self.api_client.delete_assets(raster_ids, timeout=30.0)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Delete Failed",
                f"Failed to delete assets: {exc}",
            )
            return

        deleted = result.get("deleted", [])
        missing = result.get("missing", [])
        if deleted:
            self._log_activity(f"Deleted {len(deleted)} asset(s) from catalog")
        if missing:
            self._log_activity(f"Missing {len(missing)} asset(s) not found")

        self.refresh_assets()

    def _log_activity(self, message: str) -> None:
        """Append a message to the activity log.

        Args:
            message: Message to log.
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.activity_log.append(f"[{timestamp}] {message}")


__all__ = ["MonitoringPanel"]
