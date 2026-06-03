"""About dialog for the Offline GIS desktop applications.

Provides a PySide6 QDialog that displays application metadata, version
information, and deployment topology. All configurable values are read
from ``src_new.shared.config.settings`` — no hardcoded strings.

Requirements: 7.6, 12.4
"""
from __future__ import annotations

import logging

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from src_new.shared.config import settings

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- Application metadata constants ---------------------------------------------------------------------------
_APP_NAME = "resGIS"
_APP_VERSION = "1.0.0"
_APP_DESCRIPTION = (
    "A modular, offline geospatial platform for processing and visualising "
    "terabyte-scale aerial imagery and digital elevation models, developed by NTRO, Gov. of India."
)
_COPYRIGHT = "© 2026 NTRO, Gov. of India"
_LICENSE = "Proprietary — Government Use Only"


class AboutDialog(QDialog):
    """Modal about dialog showing application metadata and deployment info.

    Reads service URLs and deployment topology from the centralized
    ``src_new.shared.config.settings`` object so the displayed information
    always reflects the current environment configuration.

    Example::

        dialog = AboutDialog(parent=main_window)
        dialog.exec()
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"About {_APP_NAME}")
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        self._build_ui()
        logger.debug("AboutDialog initialised")

    # ------------------------------------------------------------------ Private helpers ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Construct and lay out all child widgets."""
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(32, 28, 32, 20)
        root_layout.setSpacing(12)

        # ── App name & version ────────────────────────────────────────
        name_label = QLabel(f"<b>{_APP_NAME}</b>")
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setStyleSheet("font-size: 22px; color: #1a2a3a;")
        root_layout.addWidget(name_label)

        version_label = QLabel(f"Version {_APP_VERSION}")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet("font-size: 13px; color: #6b7a8d;")
        root_layout.addWidget(version_label)

        # ── Description ───────────────────────────────────────────────
        desc_label = QLabel(_APP_DESCRIPTION)
        desc_label.setWordWrap(True)
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setStyleSheet("font-size: 12px; color: #4a5568; margin-top: 4px;")
        root_layout.addWidget(desc_label)

        # ── Separator ─────────────────────────────────────────────────
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #e2e8f0; margin: 4px 0;")
        root_layout.addWidget(sep)

        # ── Deployment info (from config — no hardcoded values) ───────
        topology = settings.deployment_topology
        ingestion_url = settings.ingestion_service_url
        tile_url = settings.tile_service_url
        query_url = settings.query_service_url

        deployment_html = (
            f"<b>Deployment Topology:</b> {topology}<br>"
            f"<b>Ingestion Service:</b> {ingestion_url}<br>"
            f"<b>Tile Service:</b> {tile_url}<br>"
            f"<b>Query Service:</b> {query_url}"
        )
        deployment_label = QLabel(deployment_html)
        deployment_label.setWordWrap(True)
        deployment_label.setStyleSheet(
            "font-size: 11px; color: #4a5568; "
            "background: #f7fafc; border: 1px solid #e2e8f0; "
            "border-radius: 6px; padding: 10px;"
        )
        root_layout.addWidget(deployment_label)

        # ── Copyright & license ───────────────────────────────────────
        footer_label = QLabel(f"{_COPYRIGHT}<br><small>{_LICENSE}</small>")
        footer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer_label.setWordWrap(True)
        footer_label.setStyleSheet("font-size: 11px; color: #9aa5b4; margin-top: 4px;")
        root_layout.addWidget(footer_label)

        # ── Close button ──────────────────────────────────────────────
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root_layout.addWidget(buttons)


__all__ = ["AboutDialog"]
