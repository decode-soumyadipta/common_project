"""Desktop Ingestion Client package.

This package provides the PySide6-based desktop application for uploading and
managing geospatial data ingestion into the Offline GIS system.

The ingestion client communicates exclusively with Server 1 (Ingestion Service
+ Tile Service) and does not include search or visualization features.

Modules:
    api_client: HTTP client for communicating with the Ingestion Service.
    main: Entry point for launching the application.
    ui.main_window: Main application window.
    ui.upload_dialog: File upload dialog.
    ui.monitoring_panel: Ingestion monitoring panel.

Requirements: 7.1, 7.3, 7.5, 7.6
"""
from __future__ import annotations

from src_new.clients.desktop_ingestion.api_client import IngestionApiClient
from src_new.clients.desktop_ingestion.main import main

__all__ = ["IngestionApiClient", "main"]
