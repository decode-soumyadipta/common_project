"""Upload dialog for the Desktop Ingestion Client.

Provides a PySide6 QDialog that allows the user to select one or more
geospatial files (GeoTIFF, JPEG2000, MBTiles) and submit them to the
Ingestion Service. All service URLs are read from the centralized
``src_new.shared.config.settings`` object — no hardcoded values.

Requirements: 7.1, 7.6
"""
from __future__ import annotations

import logging
from pathlib import Path

from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src_new.shared.config import settings

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- Supported file extensions (mirrors src_new/shared/constants.py) ---------------------------------------------------------------------------
_SUPPORTED_EXTENSIONS = (".tif", ".tiff", ".j2k", ".jp2", ".mbtiles")
_FILE_FILTER = (
    "Geospatial Files (*.tif *.tiff *.j2k *.jp2 *.mbtiles);;"
    "GeoTIFF (*.tif *.tiff);;"
    "JPEG2000 (*.j2k *.jp2);;"
    "MBTiles (*.mbtiles);;"
    "All Files (*)"
)


class UploadDialog(QDialog):
    """Modal dialog for selecting and submitting geospatial files for ingestion.

    The dialog collects a list of file paths and optional metadata tags from
    the user. It does **not** perform the upload itself — callers should read
    :attr:`selected_files` and :attr:`metadata_tags` after ``exec()`` returns
    ``Accepted`` and then call the API client.

    Signals:
        files_selected: Emitted when the user confirms the file selection.
            Carries the list of absolute file paths.

    Attributes:
        file_list: QListWidget showing the currently selected files.
        tags_edit: QLineEdit for optional comma-separated metadata tags.

    Example::

        dialog = UploadDialog(parent=main_window)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            for path in dialog.selected_files:
                api_client.upload_file(path, tags=dialog.metadata_tags)
    """

    # Emitted with the list of selected file paths when the user clicks Upload
    files_selected = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Upload Geospatial Files")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setMinimumHeight(420)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        self._build_ui()
        logger.debug(
            "UploadDialog initialised; target service: %s",
            settings.ingestion_service_url,
        )

    # ------------------------------------------------------------------ Public API ------------------------------------------------------------------

    @property
    def selected_files(self) -> list[Path]:
        """Return the list of file paths currently shown in the file list.

        Returns:
            List of :class:`pathlib.Path` objects for each selected file.
        """
        paths: list[Path] = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item is not None:
                paths.append(Path(item.data(Qt.ItemDataRole.UserRole)))
        return paths

    @property
    def metadata_tags(self) -> list[str]:
        """Return the comma-separated metadata tags as a list of strings.

        Returns:
            List of stripped, non-empty tag strings.
        """
        raw = self.tags_edit.text().strip()
        if not raw:
            return []
        return [t.strip() for t in raw.split(",") if t.strip()]

    @property
    def metadata_description(self) -> str:
        """Return the description text entered by the user.

        Returns:
            Stripped description string (may be empty).
        """
        return self.description_edit.toPlainText().strip()

    # ------------------------------------------------------------------ Private helpers ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Construct and lay out all child widgets."""
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 20, 20, 16)
        root_layout.setSpacing(14)

        # ── Header ────────────────────────────────────────────────────
        header = QLabel("<b>Upload Geospatial Files</b>")
        header.setStyleSheet("font-size: 16px; color: #1a2a3a;")
        root_layout.addWidget(header)

        service_label = QLabel(
            f"<small>Ingestion Service: {settings.ingestion_service_url}</small>"
        )
        service_label.setStyleSheet("color: #9aa5b4;")
        root_layout.addWidget(service_label)

        # ── File selection group ──────────────────────────────────────
        file_group = QGroupBox("Selected Files")
        file_group.setStyleSheet(
            """
            QGroupBox {
                font-weight: 600;
                font-size: 12px;
                color: #2d3748;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            """
        )
        file_group_layout = QVBoxLayout(file_group)
        file_group_layout.setContentsMargins(12, 16, 12, 12)
        file_group_layout.setSpacing(8)

        self.file_list = QListWidget()
        self.file_list.setMinimumHeight(160)
        self.file_list.setAlternatingRowColors(True)
        self.file_list.setSelectionMode(
            QListWidget.SelectionMode.ExtendedSelection
        )
        file_group_layout.addWidget(self.file_list)

        # File action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        add_btn = QPushButton("Add Files…")
        add_btn.clicked.connect(self._add_files)
        btn_row.addWidget(add_btn)

        add_dir_btn = QPushButton("Add Directory…")
        add_dir_btn.clicked.connect(self._add_directory)
        btn_row.addWidget(add_dir_btn)

        btn_row.addStretch()

        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._remove_selected)
        btn_row.addWidget(remove_btn)

        clear_btn = QPushButton("Clear All")
        clear_btn.clicked.connect(self.file_list.clear)
        btn_row.addWidget(clear_btn)

        file_group_layout.addLayout(btn_row)
        root_layout.addWidget(file_group)

        # ── Metadata group ────────────────────────────────────────────
        meta_group = QGroupBox("Optional Metadata")
        meta_group.setStyleSheet(file_group.styleSheet())
        meta_form = QFormLayout(meta_group)
        meta_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        meta_form.setSpacing(8)
        meta_form.setContentsMargins(12, 16, 12, 12)

        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText(
            "e.g. survey-2024, zone-A, dem  (comma-separated)"
        )
        self.tags_edit.setMinimumHeight(30)
        meta_form.addRow("Tags:", self.tags_edit)

        self.description_edit = QTextEdit()
        self.description_edit.setPlaceholderText(
            "Optional description for this batch upload…"
        )
        self.description_edit.setMaximumHeight(72)
        meta_form.addRow("Description:", self.description_edit)

        root_layout.addWidget(meta_group)

        # ── File count label ──────────────────────────────────────────
        self._count_label = QLabel("No files selected.")
        self._count_label.setStyleSheet("color: #6b7a8d; font-size: 11px;")
        root_layout.addWidget(self._count_label)
        self.file_list.model().rowsInserted.connect(self._update_count)
        self.file_list.model().rowsRemoved.connect(self._update_count)

        # ── Buttons ───────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Upload")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root_layout.addWidget(buttons)

    def _add_files(self) -> None:
        """Open a file picker and add the chosen files to the list."""
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Geospatial Files",
            str(Path.home()),
            _FILE_FILTER,
        )
        for path_str in paths:
            self._add_path(Path(path_str))

    def _add_directory(self) -> None:
        """Recursively add all supported files from a chosen directory."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Directory", str(Path.home())
        )
        if not directory:
            return
        dir_path = Path(directory)
        added = 0
        for ext in _SUPPORTED_EXTENSIONS:
            for file_path in dir_path.rglob(f"*{ext}"):
                self._add_path(file_path)
                added += 1
        logger.debug("Added %d files from directory: %s", added, directory)

    def _add_path(self, path: Path) -> None:
        """Add a single file path to the list widget (no duplicates)."""
        path_str = str(path.resolve())
        # Avoid duplicates
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == path_str:
                return
        item = QListWidgetItem(path.name)
        item.setData(Qt.ItemDataRole.UserRole, path_str)
        item.setToolTip(path_str)
        self.file_list.addItem(item)

    def _remove_selected(self) -> None:
        """Remove all currently selected items from the file list."""
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))

    def _update_count(self) -> None:
        """Refresh the file count label."""
        count = self.file_list.count()
        if count == 0:
            self._count_label.setText("No files selected.")
        elif count == 1:
            self._count_label.setText("1 file selected.")
        else:
            self._count_label.setText(f"{count} files selected.")

    def _on_accept(self) -> None:
        """Validate that at least one file is selected before accepting."""
        if self.file_list.count() == 0:
            self._count_label.setText(
                "⚠ Please add at least one file before uploading."
            )
            self._count_label.setStyleSheet("color: #e53e3e; font-size: 11px;")
            return
        files = self.selected_files
        logger.info(
            "UploadDialog accepted with %d file(s): %s",
            len(files),
            [str(f) for f in files],
        )
        self.files_selected.emit([str(f) for f in files])
        self.accept()


__all__ = ["UploadDialog"]
