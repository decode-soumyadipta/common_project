"""Main Window for Desktop Search Client

Provides the primary UI for the geospatial search application including:
- Search panel for spatial queries
- Web view for CesiumJS 3D/2D map display
- Integration with Query and Tile services

Migrated from src/client_desktop/backend/main_window.py
Requirements: 7.2, 7.6
"""
from __future__ import annotations

import logging
from pathlib import Path

from qtpy.QtCore import Qt, QUrl
from qtpy.QtGui import QAction
from qtpy.QtWebEngineWidgets import QWebEngineView
from qtpy.QtWidgets import (
    QMainWindow,
    QSplitter,
    QMessageBox,
)

from src_new.clients.desktop_search.ui.search_panel import SearchPanel
from src_new.clients.desktop_search.api_client import SearchApiClient
from src_new.shared.config import settings

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window for the Desktop Search Client.
    
    Provides:
    - Search panel for spatial queries (point, bbox)
    - CesiumJS-based 3D/2D map visualization
    - Integration with Query Service and Tile Service
    """
    
    def __init__(self):
        """Initialize the main window."""
        super().__init__()
        
        self.setWindowTitle("Geospatial Search Client")
        self.resize(1400, 900)
        
        # Initialize API client
        self.api_client = SearchApiClient(
            query_service_url=settings.query_service_url,
            tile_service_url=settings.tile_service_url
        )
        
        # Create UI components
        self._create_menu_bar()
        self._create_central_widget()
        self._create_status_bar()
        
        # Load web view
        self._load_cesium_view()
        
        logger.info("Main window initialized")
    
    def _create_menu_bar(self):
        """Create the application menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _create_central_widget(self):
        """Create the central widget with search panel and map view."""
        # Create search panel
        self.search_panel = SearchPanel(self)
        
        # Create web view for CesiumJS
        self.web_view = QWebEngineView(self)
        
        # Create horizontal splitter
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self.search_panel)
        splitter.addWidget(self.web_view)
        splitter.setSizes([400, 1000])
        
        self.setCentralWidget(splitter)
        
        # Connect search panel signals
        self.search_panel.point_search_requested.connect(self._on_point_search)
        self.search_panel.polygon_search_requested.connect(self._on_polygon_search)
    
    def _create_status_bar(self):
        """Create the status bar."""
        self.statusBar().showMessage("Ready")
    
    def _load_cesium_view(self):
        """Load the CesiumJS web view."""
        # Find the web assets directory
        web_assets_dir = Path(__file__).parent.parent / "web_assets"
        index_html = web_assets_dir / "index.html"
        
        if not index_html.exists():
            logger.error(f"index.html not found at {index_html}")
            QMessageBox.critical(
                self,
                "Error",
                f"Web assets not found at {web_assets_dir}\n\n"
                "The CesiumJS frontend files are missing."
            )
            return
        
        # Load the HTML file
        url = QUrl.fromLocalFile(str(index_html.resolve()))
        self.web_view.setUrl(url)
        
        logger.info(f"Loading CesiumJS from {index_html}")
    
    def _on_point_search(self, lon: float, lat: float, buffer_m: int):
        """Handle point search request.
        
        Args:
            lon: Longitude coordinate
            lat: Latitude coordinate
            buffer_m: Buffer radius in meters
        """
        logger.info(f"Point search: lon={lon}, lat={lat}, buffer={buffer_m}m")
        
        try:
            # Query the service
            results = self.api_client.query_point(lon, lat)
            
            if results:
                self.statusBar().showMessage(f"Found {len(results)} rasters")
                logger.info(f"Point search returned {len(results)} results")
                # TODO: Display results in search panel and on map
            else:
                self.statusBar().showMessage("No rasters found")
                logger.info("Point search returned no results")
                
        except Exception as e:
            logger.error(f"Point search failed: {e}", exc_info=True)
            QMessageBox.warning(
                self,
                "Search Error",
                f"Failed to search: {e}\n\nCheck that the Query Service is running."
            )
    
    def _on_polygon_search(self):
        """Handle polygon search request."""
        logger.info("Polygon search requested")
        self.statusBar().showMessage("Polygon search not yet implemented")
        # TODO: Implement polygon search
    
    def _show_about(self):
        """Show the about dialog."""
        QMessageBox.about(
            self,
            "About Geospatial Search Client",
            "<h3>Geospatial Search Client</h3>"
            "<p>Version 0.1.0</p>"
            "<p>A desktop application for searching and visualizing geospatial raster data.</p>"
            "<p><b>Services:</b></p>"
            "<ul>"
            f"<li>Query Service: {settings.query_service_url}</li>"
            f"<li>Tile Service: {settings.tile_service_url}</li>"
            "</ul>"
        )
    
    def closeEvent(self, event):
        """Handle window close event."""
        logger.info("Closing main window")
        super().closeEvent(event)
