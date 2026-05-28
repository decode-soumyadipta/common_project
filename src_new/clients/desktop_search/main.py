"""Desktop Search Client - Main Entry Point

This module provides the main entry point for the desktop search client application.
It initializes the Qt application and launches the main window with full features
from the original implementation.

Usage:
    python -m src_new.clients.desktop_search.main
"""
from __future__ import annotations

import logging
import sys

# CRITICAL: Import QtWebEngineWidgets FIRST before QApplication
# This is required for proper OpenGL context sharing
from qtpy import QtWebEngineWidgets  # noqa: F401

from qtpy.QtWidgets import QApplication
from qtpy.QtCore import Qt

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


def main() -> int:
    """Main entry point for the desktop search client.
    
    Returns:
        Exit code (0 for success, non-zero for error)
    """
    try:
        # Set Qt attribute BEFORE creating QApplication
        QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
        
        # Create Qt application
        app = QApplication(sys.argv)
        app.setApplicationName("Distributed GIS - Search & Visualization Node")
        app.setOrganizationName("Offline GIS")
        
        logger.info("Starting Desktop Search Client...")
        
        # Import after QApplication is created
        from src_new.clients.desktop_search.main_window import MainWindow
        from src_new.clients.desktop_search.app_mode import DesktopAppMode
        
        # Create main window in CLIENT mode (Search, Viz, Analysis)
        window = MainWindow(app_mode=DesktopAppMode.CLIENT)
        window.setWindowTitle("Distributed GIS - Search & Visualization Node")
        window.show()
        
        logger.info("Desktop Search Client started successfully")
        
        # Run event loop
        return app.exec()
        
    except Exception as e:
        logger.error(f"Failed to start Desktop Search Client: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
