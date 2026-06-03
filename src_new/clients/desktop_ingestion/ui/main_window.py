"""Main window for the Desktop Ingestion Client.

This module provides the primary UI for the ingestion client, including:
- File upload dialog integration
- Ingestion monitoring panel
- Service health status display
- Toolbar with ingestion-specific actions

The ingestion client communicates exclusively with Server 1 (Ingestion Service
+ Tile Service) and does not include search or visualization features.

Requirements: 7.1, 7.3, 7.5, 7.6
"""
from __future__ import annotations

import logging
from pathlib import Path

from qtpy.QtCore import Qt, QTimer, QSize, QThread, Signal
from qtpy.QtGui import QIcon, QPixmap
from qtpy.QtWidgets import (
    QAction,
    QLabel,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QStatusBar,
    QToolBar,
    QWidget,
)

from src_new.clients.desktop_ingestion.api_client import IngestionApiClient
from src_new.clients.desktop_ingestion.ui.monitoring_panel import MonitoringPanel
from src_new.clients.desktop_ingestion.ui.upload_dialog import UploadDialog
from src_new.shared.config import settings

logger = logging.getLogger(__name__)


class HealthCheckWorker(QThread):
    """Background worker for querying service liveness/readiness.

    Prevents blocking the Qt GUI main thread during network request timeouts.
    """
    health_checked = Signal(bool, bool)  # ingestion_ok, tile_ok

    def __init__(self, api_client: IngestionApiClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.api_client = api_client

    def run(self) -> None:
        try:
            ingestion_ok = self.api_client.ingestion_service_ready()
        except Exception:
            ingestion_ok = False

        try:
            tile_ok = self.api_client.tile_service_ready()
        except Exception:
            tile_ok = False

        self.health_checked.emit(ingestion_ok, tile_ok)


class MainWindow(QMainWindow):
    """Main application window for the Desktop Ingestion Client.

    Provides the primary UI including:
    - Toolbar with upload and refresh actions
    - Monitoring panel for tracking ingestion progress
    - Status bar with service health indicators
    - Upload dialog for file selection

    The window communicates exclusively with Server 1 (Ingestion Service +
    Tile Service) via the ``IngestionApiClient``.

    Requirements: 7.1, 7.3, 7.5, 7.6
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the main window.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("resGIS - Data Ingestion (developed by NTRO, Gov. of India)")
        self.resize(1000, 700)

        # Apply resGIS logo as the window icon (title-bar corner, taskbar, dock)
        _logo = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "resGIS_logo.png"
        if _logo.exists():
            self.setWindowIcon(QIcon(str(_logo)))

        # Initialize API client
        self.api_client = IngestionApiClient()

        # Build UI components
        self._create_toolbar()
        self._create_central_widget()
        self._create_status_bar()

        # Start service health monitoring
        self._health_check_timer = QTimer(self)
        self._health_check_timer.timeout.connect(self._check_service_health)
        self._health_check_timer.start(10000)  # Check every 10 seconds
        self._check_service_health()  # Initial check

        logger.info("MainWindow initialized")

    # ------------------------------------------------------------------ UI Construction ------------------------------------------------------------------

    def _create_toolbar(self) -> None:
        """Create the main toolbar with ingestion actions."""
        toolbar = QToolBar("Main Toolbar", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

        # Upload action
        upload_action = QAction("Upload Files", self)
        upload_action.setToolTip("Open upload dialog to select files for ingestion")
        upload_action.triggered.connect(self._show_upload_dialog)
        toolbar.addAction(upload_action)

        toolbar.addSeparator()

        # Refresh action
        refresh_action = QAction("Refresh", self)
        refresh_action.setToolTip("Refresh ingestion status and asset list")
        refresh_action.triggered.connect(self._refresh_data)
        toolbar.addAction(refresh_action)

        toolbar.addSeparator()

        # About action
        about_action = QAction("About", self)
        about_action.setToolTip("About this application")
        about_action.triggered.connect(self._show_about)
        toolbar.addAction(about_action)

        # ── Right-aligned resGIS logo ────────────────────────────────────────
        _spacer = QWidget()
        _spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(_spacer)

        _logo_path = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "resGIS_logo.png"
        if _logo_path.exists():
            _logo_label = QLabel()
            _pix = QPixmap(str(_logo_path))
            
            # Tight zoom crop of the active logo area, giving extra breathing room on the right to prevent clipping the 'S'
            from qtpy.QtCore import QRect
            _pix = _pix.copy(QRect(128, 349, 800, 287))
            
            # Scale to a slightly taller height (34 px) for prominent zoom display
            _pix = _pix.scaledToHeight(34, Qt.TransformationMode.SmoothTransformation)
            _logo_label.setPixmap(_pix)
            _logo_label.setFixedSize(_pix.size())
            _logo_label.setToolTip("resGIS \u2014 developed by NTRO, Gov. of India")
            _logo_label.setStyleSheet("margin-left: 4px;")
            toolbar.addWidget(_logo_label)
            
            # Robust native spacer to shift the logo leftwards without triggering Qt's stylesheet margin layout bugs
            _right_margin_spacer = QWidget()
            _right_margin_spacer.setFixedWidth(20)
            toolbar.addWidget(_right_margin_spacer)

        self._toolbar = toolbar

    def _create_central_widget(self) -> None:
        """Create the central widget with monitoring panel."""
        # Create monitoring panel
        self.monitoring_panel = MonitoringPanel(self.api_client, self)

        # Wrap in scroll area
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.monitoring_panel)

        # Set as central widget
        self.setCentralWidget(scroll_area)

    def _create_status_bar(self) -> None:
        """Create the status bar with service health indicators."""
        status_bar = QStatusBar(self)
        self.setStatusBar(status_bar)

        # Service status indicators
        self._ingestion_status_label = QLabel("Ingestion Service: Checking...")
        self._ingestion_status_label.setStyleSheet("padding: 2px 8px;")
        status_bar.addWidget(self._ingestion_status_label)

        status_bar.addWidget(QLabel("|"))

        self._tile_status_label = QLabel("Tile Service: Checking...")
        self._tile_status_label.setStyleSheet("padding: 2px 8px;")
        status_bar.addWidget(self._tile_status_label)

        status_bar.addPermanentWidget(
            QLabel(f"Ingestion URL: {settings.ingestion_service_url}")
        )

    # ------------------------------------------------------------------ Actions ------------------------------------------------------------------

    def _show_upload_dialog(self) -> None:
        """Show the upload dialog and process selected files."""
        dialog = UploadDialog(self)
        if dialog.exec() == UploadDialog.DialogCode.Accepted:
            files = dialog.selected_files
            tags = dialog.metadata_tags
            description = dialog.metadata_description
            logger.info("Upload dialog accepted with %d files", len(files))

            # Pass files to monitoring panel for upload
            self.monitoring_panel.upload_files(files, tags, description)

    def _refresh_data(self) -> None:
        """Refresh ingestion status and asset list."""
        logger.info("Refreshing data...")
        self.monitoring_panel.refresh_all()
        self._check_service_health()

    def _show_settings(self) -> None:
        """Show settings dialog."""
        QMessageBox.information(
            self,
            "Settings",
            f"Ingestion Service: {settings.ingestion_service_url}\n"
            f"Tile Service: {settings.tile_service_url}\n\n"
            "To change these settings, edit the .env file in the project root.",
        )

    def _show_about(self) -> None:
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About resGIS - Data Ingestion",
            "<h3>resGIS - Data Ingestion Client</h3>"
            "<p>Version 1.0</p>"
            "<p>Desktop application developed by NTRO, Gov. of India, for uploading and managing geospatial data "
            "ingestion into the resGIS system.</p>"
            "<p><b>Features:</b></p>"
            "<ul>"
            "<li>Upload GeoTIFF, JPEG2000, and MBTiles files</li>"
            "<li>Monitor ingestion progress in real-time</li>"
            "<li>View uploaded asset catalog</li>"
            "<li>Service health monitoring</li>"
            "</ul>"
            "<p><b>Requirements:</b> 7.1, 7.3, 7.5, 7.6</p>",
        )

    # ------------------------------------------------------------------ Service Health Monitoring ------------------------------------------------------------------

    def _check_service_health(self) -> None:
        """Start background liveness checks for ingestion and tile services.

        Runs off the main thread to prevent the UI from blocking/flickering.
        """
        if hasattr(self, "_health_worker") and self._health_worker.isRunning():
            return

        self._health_worker = HealthCheckWorker(self.api_client, self)
        self._health_worker.health_checked.connect(self._on_health_checked)
        self._health_worker.start()

    def _on_health_checked(self, ingestion_ok: bool, tile_ok: bool) -> None:
        """Handle health check results and update the status bar."""
        # Update ingestion service status
        if ingestion_ok:
            self._ingestion_status_label.setText("Ingestion Service: ✓ Healthy")
            self._ingestion_status_label.setStyleSheet(
                "color: #2d7a2d; font-weight: 600; padding: 2px 8px;"
            )
        else:
            self._ingestion_status_label.setText("Ingestion Service: ✗ Unavailable")
            self._ingestion_status_label.setStyleSheet(
                "color: #c53030; font-weight: 600; padding: 2px 8px;"
            )

        # Update tile service status
        if tile_ok:
            self._tile_status_label.setText("Tile Service: ✓ Healthy")
            self._tile_status_label.setStyleSheet(
                "color: #2d7a2d; font-weight: 600; padding: 2px 8px;"
            )
        else:
            self._tile_status_label.setText("Tile Service: ✗ Unavailable")
            self._tile_status_label.setStyleSheet(
                "color: #c53030; font-weight: 600; padding: 2px 8px;"
            )


__all__ = ["MainWindow"]
