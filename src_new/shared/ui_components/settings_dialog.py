"""Settings dialog for the Offline GIS desktop applications.

Provides a PySide6 QDialog that exposes the most commonly adjusted
runtime settings. All default values are read from the centralized
``src_new.shared.config.settings`` object — no hardcoded strings or
URLs appear in this module.

Requirements: 7.6, 12.4
"""
from __future__ import annotations

import logging
from pathlib import Path

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src_new.shared.config import settings

logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    """Modal settings dialog for configuring service endpoints and paths.

    Displays the current values from ``src_new.shared.config.settings`` and
    allows the user to override them for the current session. Changes are
    **not** persisted to the ``.env`` file — they only affect the in-memory
    ``Settings`` instance returned by :meth:`get_updated_settings`.

    Attributes:
        _fields: Mapping of field name → QLineEdit / QSpinBox widget.

    Example::

        dialog = SettingsDialog(parent=main_window)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            updated = dialog.get_updated_settings()
            # apply updated settings to the running application …
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        # Holds references to input widgets keyed by Settings field name
        self._fields: dict[str, QLineEdit | QSpinBox] = {}

        self._build_ui()
        logger.debug("SettingsDialog initialised with current config values")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_updated_settings(self) -> dict[str, object]:
        """Return a dict of field-name → new value for all edited fields.

        Only fields whose values differ from the current ``settings`` object
        are included. Callers can use this to selectively update state.

        Returns:
            Dictionary mapping Settings field names to their new values.
        """
        updates: dict[str, object] = {}
        for field_name, widget in self._fields.items():
            if isinstance(widget, QSpinBox):
                new_val: object = widget.value()
            else:
                new_val = widget.text().strip()

            current_val = getattr(settings, field_name, None)
            if new_val != current_val and new_val != str(current_val):
                updates[field_name] = new_val

        return updates

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Construct and lay out all child widgets."""
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Scrollable content area ───────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 20, 24, 20)
        content_layout.setSpacing(16)

        # ── Service Endpoints group ───────────────────────────────────
        endpoints_group = self._make_group(
            "Service Endpoints",
            [
                ("ingestion_service_url", "Ingestion Service URL", str(settings.ingestion_service_url)),
                ("tile_service_url", "Tile Service URL", str(settings.tile_service_url)),
                ("query_service_url", "Query Service URL", str(settings.query_service_url)),
                ("titiler_base_url", "TiTiler Base URL", str(settings.titiler_base_url)),
                ("cesium_base_url", "CesiumJS Base URL", str(settings.cesium_base_url)),
            ],
        )
        content_layout.addWidget(endpoints_group)

        # ── Data Storage group ────────────────────────────────────────
        storage_group = self._make_group(
            "Data Storage",
            [
                ("data_root", "Data Root Directory", str(settings.data_root)),
                ("database_url", "Database URL", str(settings.database_url)),
            ],
            browse_fields={"data_root"},
        )
        content_layout.addWidget(storage_group)

        # ── Network group ─────────────────────────────────────────────
        network_group = self._make_group(
            "Network & Security",
            [
                ("api_host", "API Host", str(settings.api_host)),
                ("allowed_hosts", "Allowed Hosts (comma-separated)", str(settings.allowed_hosts)),
            ],
        )
        content_layout.addWidget(network_group)

        # ── Logging group ─────────────────────────────────────────────
        logging_group = self._make_group(
            "Logging",
            [
                ("log_level", "Log Level (DEBUG/INFO/WARNING/ERROR)", str(settings.log_level)),
                ("log_output_path", "Log Output Path (empty = stdout)", str(settings.log_output_path)),
            ],
        )
        content_layout.addWidget(logging_group)

        content_layout.addStretch()
        scroll.setWidget(content)
        root_layout.addWidget(scroll)

        # ── Buttons ───────────────────────────────────────────────────
        button_bar = QWidget()
        button_bar.setStyleSheet("border-top: 1px solid #e2e8f0;")
        bar_layout = QHBoxLayout(button_bar)
        bar_layout.setContentsMargins(24, 12, 24, 12)

        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self._reset_to_defaults)
        bar_layout.addWidget(reset_btn)
        bar_layout.addStretch()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        bar_layout.addWidget(buttons)

        root_layout.addWidget(button_bar)

    def _make_group(
        self,
        title: str,
        fields: list[tuple[str, str, str]],
        browse_fields: set[str] | None = None,
    ) -> QGroupBox:
        """Create a labelled group box containing a form of text fields.

        Args:
            title: Group box title.
            fields: List of (field_name, label_text, current_value) tuples.
            browse_fields: Set of field names that should show a Browse button.

        Returns:
            Configured QGroupBox widget.
        """
        group = QGroupBox(title)
        group.setStyleSheet(
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
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)
        form.setContentsMargins(12, 16, 12, 12)

        for field_name, label_text, current_value in fields:
            edit = QLineEdit(current_value)
            edit.setMinimumHeight(30)
            self._fields[field_name] = edit

            if browse_fields and field_name in browse_fields:
                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(6)
                row_layout.addWidget(edit)
                browse_btn = QPushButton("Browse…")
                browse_btn.setFixedWidth(72)
                browse_btn.clicked.connect(
                    lambda _checked=False, e=edit: self._browse_directory(e)
                )
                row_layout.addWidget(browse_btn)
                form.addRow(label_text + ":", row_widget)
            else:
                form.addRow(label_text + ":", edit)

        return group

    def _browse_directory(self, edit: QLineEdit) -> None:
        """Open a directory picker and populate *edit* with the chosen path."""
        start_dir = edit.text().strip() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(
            self, "Select Directory", start_dir
        )
        if chosen:
            edit.setText(chosen)

    def _reset_to_defaults(self) -> None:
        """Reset all fields to the values currently held in ``settings``."""
        defaults: dict[str, str] = {
            "ingestion_service_url": str(settings.ingestion_service_url),
            "tile_service_url": str(settings.tile_service_url),
            "query_service_url": str(settings.query_service_url),
            "titiler_base_url": str(settings.titiler_base_url),
            "cesium_base_url": str(settings.cesium_base_url),
            "data_root": str(settings.data_root),
            "database_url": str(settings.database_url),
            "api_host": str(settings.api_host),
            "allowed_hosts": str(settings.allowed_hosts),
            "log_level": str(settings.log_level),
            "log_output_path": str(settings.log_output_path),
        }
        for field_name, value in defaults.items():
            widget = self._fields.get(field_name)
            if isinstance(widget, QLineEdit):
                widget.setText(value)
        logger.debug("SettingsDialog fields reset to current config defaults")


__all__ = ["SettingsDialog"]
