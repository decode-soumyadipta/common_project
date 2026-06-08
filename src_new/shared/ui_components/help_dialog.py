"""Help and Documentation dialog for resGIS.

Provides a structured, beautifully formatted Qt dialog displaying software details
and a concise user guide, eliminating web browser redirects.
"""
from __future__ import annotations

import logging

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from src_new.shared.config import settings

logger = logging.getLogger(__name__)

class HelpDialog(QDialog):
    """Modal Help and Documentation Dialog for resGIS."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("resGIS - Help & Documentation")
        self.setModal(True)
        self.setMinimumSize(550, 480)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        self._build_ui()
        logger.debug("HelpDialog initialized")

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 15)
        layout.setSpacing(15)

        # Title Header
        header = QLabel("resGIS")
        header.setStyleSheet("font-size: 24px; font-weight: bold; color: #1a365d;")
        sub_header = QLabel("developed by NTRO, Gov. of India")
        sub_header.setStyleSheet("font-size: 13px; color: #4a5568; font-style: italic;")

        header_layout = QVBoxLayout()
        header_layout.addWidget(header)
        header_layout.addWidget(sub_header)
        layout.addLayout(header_layout)

        # Tabs
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Tab 1: Software Details
        self.tabs.addTab(self._create_software_details_tab(), "Software Details")

        # Tab 2: User Workflow Guide
        self.tabs.addTab(self._create_user_guide_tab(), "User Guide")

        # Close Button
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _create_software_details_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        # Description
        desc_label = QLabel(
            "resGIS is an enterprise-grade, fully offline 3D Geographic Information System (GIS) "
            "designed for secure, localized spatial analysis. It supports terabyte-scale imagery and "
            "digital elevation models (DEM) without relying on external internet connectivity."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("font-size: 12px; color: #2d3748; line-height: 1.4;")
        layout.addWidget(desc_label)

        # Separator line
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #cbd5e0;")
        layout.addWidget(sep)

        # Info Grid
        info_html = (
            "<h3>System Architecture</h3>"
            "<table style='width: 100%; font-size: 11px; color: #2d3748; border-collapse: collapse;'>"
            "  <tr><td style='padding: 4px 0; font-weight: bold; width: 150px;'>Version:</td><td>1.0.0</td></tr>"
            "  <tr><td style='padding: 4px 0; font-weight: bold;'>License:</td><td>Proprietary — Government Use Only</td></tr>"
            f"  <tr><td style='padding: 4px 0; font-weight: bold;'>Deployment Topology:</td><td>{settings.deployment_topology}</td></tr>"
            f"  <tr><td style='padding: 4px 0; font-weight: bold;'>Ingestion Service:</td><td>{settings.ingestion_service_url}</td></tr>"
            f"  <tr><td style='padding: 4px 0; font-weight: bold;'>Tile Serving Service:</td><td>{settings.tile_service_url}</td></tr>"
            f"  <tr><td style='padding: 4px 0; font-weight: bold;'>Query Service:</td><td>{settings.query_service_url}</td></tr>"
            "</table>"
        )
        info_label = QLabel(info_html)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        layout.addStretch()

        # Copyright Footer
        footer = QLabel("© 2026 NTRO, Gov. of India. All rights reserved.")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet("font-size: 10px; color: #718096;")
        layout.addWidget(footer)

        return widget

    def _create_user_guide_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)

        guide_text = QTextBrowser()
        guide_text.setHtml(
            "<h2>User Workflow & Core Functionality</h2>"
            "<h3>1. Geospatial Data Ingestion</h3>"
            "<ul>"
            "  <li>Launch the <b>Ingestion Workspace</b> via <code>./start_ingestion_client.sh</code>.</li>"
            "  <li>Browse and select your geospatial rasters (GeoTIFFs or DEMs) and upload them to the secure server.</li>"
            "  <li>The system automatically processes, builds tile pyramids, and registers the datasets.</li>"
            "</ul>"
            "<h3>2. Layer Management & Search</h3>"
            "<ul>"
            "  <li>Launch the <b>Search & Visualization Workspace</b> via <code>./start_search_client.sh</code>.</li>"
            "  <li>Use the search sidebar coordinates panel to discover matching imagery/DEM datasets.</li>"
            "  <li>Toggle layer visibility or double-click items to fly directly to their bounding box.</li>"
            "</ul>"
            "<h3>3. Comparator & Swipe Mode</h3>"
            "<ul>"
            "  <li>Enable the <b>Comparator Mode</b> to visualize two layers side-by-side.</li>"
            "  <li>Drag the center swipe slider to compare fine spatial features between active rasters.</li>"
            "</ul>"
            "<h3>4. Geodetic Tools</h3>"
            "<ul>"
            "  <li>Use the measurement toolbar to calculate real-world distances, polygon areas, shadow height elevations, and elevation profiles.</li>"
            "  <li>Annotate findings with custom icons, text tags, lines, and bounding areas.</li>"
            "</ul>"
            "<h3>5. Session State & Exports</h3>"
            "<ul>"
            "  <li>All project configurations (camera viewport, layer overlays, stretch options) are saved automatically to <code>state.json</code>.</li>"
            "  <li>Export custom planning assets to standard <b>GeoPackages (GPKG)</b> or print formal high-resolution PDF map reports.</li>"
            "</ul>"
        )
        guide_text.setStyleSheet("border: none; background-color: transparent; font-size: 11px;")
        layout.addWidget(guide_text)

        return widget
