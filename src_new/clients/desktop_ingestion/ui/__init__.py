"""Desktop Ingestion Client UI package.

This package provides the PySide6 UI components for the Desktop Ingestion Client.

Modules:
    main_window: Main application window.
    upload_dialog: File upload dialog.
    monitoring_panel: Ingestion monitoring panel.

Requirements: 7.1, 7.3, 7.5, 7.6
"""
from __future__ import annotations

from src_new.clients.desktop_ingestion.ui.main_window import MainWindow
from src_new.clients.desktop_ingestion.ui.monitoring_panel import MonitoringPanel
from src_new.clients.desktop_ingestion.ui.upload_dialog import UploadDialog

__all__ = ["MainWindow", "MonitoringPanel", "UploadDialog"]
