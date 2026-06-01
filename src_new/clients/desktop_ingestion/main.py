"""Entry point for the Desktop Ingestion Client.

This module provides the main entry point for launching the Desktop Ingestion
Client application. It initializes the PySide6 application, configures logging,
and displays the main window.

The ingestion client communicates exclusively with Server 1 (Ingestion Service
+ Tile Service) and does not include search or visualization features.

Usage:
    python -m src_new.clients.desktop_ingestion.main

Requirements: 7.1, 7.3, 7.5, 7.6
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from qtpy.QtWidgets import QApplication
from qtpy.QtGui import QIcon

from src_new.clients.desktop_ingestion.ui.main_window import MainWindow
from src_new.shared.config import settings


def configure_logging() -> None:
    """Configure logging for the ingestion client."""
    log_dir = Path.home() / "OfflineGIS" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "ingestion_client.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout),
        ],
    )

    logger = logging.getLogger(__name__)
    logger.info("Logging configured; log file: %s", log_file)


def main() -> int:
    """Main entry point for the Desktop Ingestion Client.

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    # Configure logging
    configure_logging()
    logger = logging.getLogger(__name__)

    logger.info("Starting Desktop Ingestion Client...")
    logger.info("Ingestion Service URL: %s", settings.ingestion_service_url)
    logger.info("Tile Service URL: %s", settings.tile_service_url)

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("resGIS")
    app.setOrganizationName("NTRO, Gov. of India")

    # Set application icon (taskbar, window title bar, dock/taskbar icon)
    _logo_path = Path(__file__).resolve().parent.parent.parent / "assets" / "resGIS_logo.png"
    if _logo_path.exists():
        app.setWindowIcon(QIcon(str(_logo_path)))

    # Create and show main window
    window = MainWindow()
    window.show()

    logger.info("Main window displayed")

    # Run event loop
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
