from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGraphicsDropShadowEffect,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolBox,
    QVBoxLayout,
    QWidget,
)

from offline_gis_app.desktop.app_mode import DesktopAppMode

if TYPE_CHECKING:
    from offline_gis_app.desktop.api_client import DesktopApiClient


class ControlPanel(QWidget):
    """Desktop control panel widgets for ingest, search, display, and annotation tools."""

    def __init__(self, parent: QWidget | None = None, app_mode: DesktopAppMode = DesktopAppMode.UNIFIED, api_client: DesktopApiClient | None = None):
        super().__init__(parent)
        self.api_client = api_client
        self.setMinimumWidth(380)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)
        self.sections = QToolBox(self)
        self.sections.setObjectName("controlSections")
        self.sections.setMinimumWidth(360)

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Select local/LAN raster path (GeoTIFF / JP2 / MBTiles / DEM)...")
        self.browse_btn = QPushButton("Browse")
        self.preview_btn = QPushButton("Preview")
        self.save_btn = QPushButton("Save")

        self.browse_btn.setToolTip("Pick raster from local disk or secure LAN mount.")
        self.preview_btn.setToolTip("Preview raster on the globe without saving it to catalog.")
        self.save_btn.setToolTip("Save by queueing ingest with checkpoint + resume support.")

        self.upload_box = QGroupBox("Ingest")
        upload_layout = QVBoxLayout(self.upload_box)
        upload_layout.addWidget(self.path_edit)
        row = QHBoxLayout()
        row.addWidget(self.browse_btn, 1)
        row.addWidget(self.preview_btn, 1)
        row.addWidget(self.save_btn, 1)
        upload_layout.addLayout(row)

        self.ingest_progress_bar = QProgressBar()
        self.ingest_progress_bar.setRange(0, 100)
        self.ingest_progress_bar.setValue(0)
        self.ingest_progress_bar.setFormat("%p%")
        self.ingest_status_value = QLabel("Idle")
        self.ingest_step_value = QLabel("No active ingest")
        self.ingest_counts_value = QLabel("Processed 0/0 | Failed 0")
        self.ingest_elapsed_value = QLabel("Elapsed 00:00")
        self.ingest_item_value = QLabel("Source: -")
        self.ingest_details = QTextEdit()
        self.ingest_details.setReadOnly(True)
        self.ingest_details.setMaximumHeight(85)

        # Uploaded Assets table (3 columns: File, Type, Date)
        self.uploaded_assets_list = QTableWidget(0, 3)
        self.uploaded_assets_list.setMaximumHeight(180)
        self.uploaded_assets_list.setHorizontalHeaderLabels(["File Name", "Type", "Date"])
        self.uploaded_assets_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.uploaded_assets_list.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.uploaded_assets_list.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.uploaded_assets_list.setColumnWidth(0, 200)
        self.uploaded_assets_list.setColumnWidth(1, 80)
        self.uploaded_assets_list.setColumnWidth(2, 120)
        self.uploaded_assets_list.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.uploaded_assets_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.uploaded_assets_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.uploaded_assets_list.setStyleSheet("""
            QTableWidget { background: #ffffff; border: 1px solid #d0d0d0; border-radius: 4px; gridline-color: #f0f0f0; }
            QTableWidget::item { padding: 4px; }
            QTableWidget::item:selected { background: #e8f4ff; }
            QHeaderView::section { background: #f5f5f5; padding: 4px; border: none; border-right: 1px solid #d0d0d0; }
        """)
        
        self.assets_refresh_btn = QPushButton("Refresh Catalog")
        self.assets_refresh_btn.setToolTip("Refresh the list of uploaded assets.")
        
        self.uploaded_box = QGroupBox("Uploaded Assets")
        uploaded_layout = QVBoxLayout(self.uploaded_box)
        uploaded_layout.addWidget(self.uploaded_assets_list, 1)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self.assets_refresh_btn)
        uploaded_layout.addLayout(btn_row)

        self.ingest_progress_box = QGroupBox("Progress")
        ingest_progress_layout = QFormLayout(self.ingest_progress_box)
        ingest_progress_layout.addRow("Overall", self.ingest_progress_bar)
        ingest_progress_layout.addRow("Job Status", self.ingest_status_value)
        ingest_progress_layout.addRow("Current Step", self.ingest_step_value)
        ingest_progress_layout.addRow("Elapsed", self.ingest_elapsed_value)
        ingest_progress_layout.addRow("Activity", self.ingest_details)

        self.assets_combo = QComboBox()
        self.refresh_assets_btn = QPushButton("Refresh")
        self.add_layer_btn = QPushButton("Load Selected")

        self.assets_combo.setToolTip("Catalog entries are metadata records. Raw data stays on storage.")
        self.add_layer_btn.setToolTip("Render selected raster as imagery overlay.")
        self.refresh_assets_btn.setToolTip("Refresh asset list from catalog.")

        self.layer_load_status = QLabel("Status: idle")
        self.layer_load_progress = QProgressBar()
        self.layer_load_progress.setRange(0, 100)
        self.layer_load_progress.setValue(0)
        self.layer_load_progress.setVisible(False)

        self.assets_box = QGroupBox("Available Assets")
        assets_layout = QVBoxLayout(self.assets_box)
        assets_layout.setSpacing(12)
        assets_layout.setContentsMargins(10, 10, 10, 10)
        assets_layout.addWidget(self.assets_combo)
        
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addWidget(self.refresh_assets_btn)
        btn_row.addWidget(self.add_layer_btn)
        assets_layout.addLayout(btn_row)
        
        assets_layout.addWidget(self.layer_load_status)
        assets_layout.addWidget(self.layer_load_progress)
        assets_layout.addStretch()

        self.search_coord_lon = QDoubleSpinBox()
        self.search_coord_lon.setRange(-180.0, 180.0)
        self.search_coord_lon.setDecimals(6)
        self.search_coord_lon.setSingleStep(0.0001)
        self.search_coord_lat = QDoubleSpinBox()
        self.search_coord_lat.setRange(-90.0, 90.0)
        self.search_coord_lat.setDecimals(6)
        self.search_coord_lat.setSingleStep(0.0001)
        self.search_point_btn = QPushButton("Point Search")

        self.search_west = QDoubleSpinBox()
        self.search_west.setRange(-180.0, 180.0)
        self.search_west.setDecimals(6)
        self.search_south = QDoubleSpinBox()
        self.search_south.setRange(-90.0, 90.0)
        self.search_south.setDecimals(6)
        self.search_east = QDoubleSpinBox()
        self.search_east.setRange(-180.0, 180.0)
        self.search_east.setDecimals(6)
        self.search_north = QDoubleSpinBox()
        self.search_north.setRange(-90.0, 90.0)
        self.search_north.setDecimals(6)
        self.search_bbox_btn = QPushButton("BBox Search")

        for box in (
            self.search_coord_lon,
            self.search_coord_lat,
            self.search_west,
            self.search_south,
            self.search_east,
            self.search_north,
        ):
            box.setMinimumWidth(120)
            box.setMaximumWidth(145)

        self.search_buffer_m = QSpinBox()
        self.search_buffer_m.setRange(0, 50000)
        self.search_buffer_m.setValue(0)
        self.search_buffer_m.setMaximumWidth(145)
        self.search_draw_box_btn = QPushButton("Draw Box")
        self.search_draw_polygon_btn = QPushButton("Draw Poly")
        self.search_finish_polygon_btn = QPushButton("Finish")
        self.search_clear_geometry_btn = QPushButton("Clear Geometry")
        self.search_from_draw_btn = QPushButton("Search Draw")

        self.search_box = QGroupBox("Search Catalog")
        search_layout = QVBoxLayout(self.search_box)
        search_layout.setSpacing(12)
        search_layout.setContentsMargins(10, 10, 10, 10)
        
        # Point search
        point_label = QLabel("<b>Point Search</b>")
        search_layout.addWidget(point_label)
        coord_row = QHBoxLayout()
        coord_row.setSpacing(8)
        coord_row.addWidget(QLabel("Lon:"))
        coord_row.addWidget(self.search_coord_lon, 1)
        coord_row.addWidget(QLabel("Lat:"))
        coord_row.addWidget(self.search_coord_lat, 1)
        search_layout.addLayout(coord_row)
        search_layout.addWidget(self.search_point_btn)
        
        search_layout.addSpacing(8)
        
        # BBox search
        bbox_label = QLabel("<b>Bounding Box</b>")
        search_layout.addWidget(bbox_label)
        bbox_row_1 = QHBoxLayout()
        bbox_row_1.setSpacing(8)
        bbox_row_1.addWidget(QLabel("W:"))
        bbox_row_1.addWidget(self.search_west, 1)
        bbox_row_1.addWidget(QLabel("S:"))
        bbox_row_1.addWidget(self.search_south, 1)
        search_layout.addLayout(bbox_row_1)
        bbox_row_2 = QHBoxLayout()
        bbox_row_2.setSpacing(8)
        bbox_row_2.addWidget(QLabel("E:"))
        bbox_row_2.addWidget(self.search_east, 1)
        bbox_row_2.addWidget(QLabel("N:"))
        bbox_row_2.addWidget(self.search_north, 1)
        search_layout.addLayout(bbox_row_2)
        search_layout.addWidget(self.search_bbox_btn)
        
        search_layout.addSpacing(8)
        
        # Draw search
        draw_label = QLabel("<b>Draw Shape</b>")
        search_layout.addWidget(draw_label)
        draw_row_1 = QHBoxLayout()
        draw_row_1.setSpacing(8)
        draw_row_1.addWidget(self.search_draw_box_btn, 1)
        draw_row_1.addWidget(self.search_draw_polygon_btn, 1)
        search_layout.addLayout(draw_row_1)
        draw_row_2 = QHBoxLayout()
        draw_row_2.setSpacing(8)
        draw_row_2.addWidget(self.search_finish_polygon_btn, 1)
        draw_row_2.addWidget(self.search_clear_geometry_btn, 1)
        search_layout.addLayout(draw_row_2)
        buffer_row = QHBoxLayout()
        buffer_row.setSpacing(8)
        buffer_row.addWidget(QLabel("Buffer (m):"))
        buffer_row.addWidget(self.search_buffer_m)
        buffer_row.addStretch()
        search_layout.addLayout(buffer_row)
        search_layout.addWidget(self.search_from_draw_btn)
        
        search_layout.addStretch()

        self.brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setRange(0, 200)
        self.brightness_slider.setValue(100)
        self.contrast_slider = QSlider(Qt.Orientation.Horizontal)
        self.contrast_slider.setRange(10, 300)
        self.contrast_slider.setValue(100)
        self.apply_visual_btn = QPushButton("Apply Visual Settings")
        self.pitch_slider = QSlider(Qt.Orientation.Horizontal)
        self.pitch_slider.setRange(-85, -10)
        self.pitch_slider.setValue(-45)
        self.rotate_left_btn = QPushButton("Rotate Left")
        self.rotate_right_btn = QPushButton("Rotate Right")
        self.dem_exaggeration_slider = QSlider(Qt.Orientation.Horizontal)
        self.dem_exaggeration_slider.setRange(50, 800)
        self.dem_exaggeration_slider.setValue(150)
        self.dem_hillshade_slider = QSlider(Qt.Orientation.Horizontal)
        self.dem_hillshade_slider.setRange(0, 100)
        self.dem_hillshade_slider.setValue(75)
        self.dem_azimuth_slider = QSlider(Qt.Orientation.Horizontal)
        self.dem_azimuth_slider.setRange(0, 360)
        self.dem_azimuth_slider.setValue(45)
        self.dem_altitude_slider = QSlider(Qt.Orientation.Horizontal)
        self.dem_altitude_slider.setRange(5, 90)
        self.dem_altitude_slider.setValue(45)
        self.apply_dem_btn = QPushButton("Apply DEM Surface")
        self.rgb_view_mode_combo = QComboBox()
        self.rgb_view_mode_combo.addItem("3D Terrain Scene", "3d")
        self.rgb_view_mode_combo.addItem("2D Map View", "2d")
        self.rgb_view_mode_combo.setToolTip(
            "RGB can switch between an offline 3D terrain scene and a flat 2D map view."
        )
        self.apply_rgb_view_mode_btn = QPushButton("Apply View Mode")
        self.apply_rgb_view_mode_btn.setToolTip("Switch the active raster between 3D terrain and 2D map views.")
        self.rgb_view_mode_combo.setVisible(False)
        self.apply_rgb_view_mode_btn.setVisible(False)

        self.view_box = QGroupBox("Display Settings")
        view_layout = QVBoxLayout(self.view_box)
        view_layout.setSpacing(14)
        view_layout.setContentsMargins(10, 10, 10, 10)
        
        # RGB Layer controls
        rgb_label = QLabel("<b>Imagery</b>")
        view_layout.addWidget(rgb_label)
        bright_layout = QHBoxLayout()
        bright_layout.addWidget(QLabel("Brightness:"))
        bright_layout.addWidget(self.brightness_slider, 1)
        view_layout.addLayout(bright_layout)
        contrast_layout = QHBoxLayout()
        contrast_layout.addWidget(QLabel("Contrast:"))
        contrast_layout.addWidget(self.contrast_slider, 1)
        view_layout.addLayout(contrast_layout)
        view_layout.addWidget(self.apply_visual_btn)
        
        view_layout.addSpacing(8)
        
        # Camera controls
        camera_label = QLabel("<b>Camera</b>")
        view_layout.addWidget(camera_label)
        pitch_layout = QHBoxLayout()
        pitch_layout.addWidget(QLabel("Pitch:"))
        pitch_layout.addWidget(self.pitch_slider, 1)
        view_layout.addLayout(pitch_layout)
        rotate_layout = QHBoxLayout()
        rotate_layout.setSpacing(8)
        rotate_layout.addWidget(self.rotate_left_btn, 1)
        rotate_layout.addWidget(self.rotate_right_btn, 1)
        view_layout.addLayout(rotate_layout)
        
        view_layout.addSpacing(8)
        
        # DEM-specific controls (initially hidden)
        dem_label = QLabel("<b>Terrain</b>")
        view_layout.addWidget(dem_label)
        exagg_layout = QHBoxLayout()
        exagg_layout.addWidget(QLabel("Exaggeration:"))
        exagg_layout.addWidget(self.dem_exaggeration_slider, 1)
        view_layout.addLayout(exagg_layout)
        hillshade_layout = QHBoxLayout()
        hillshade_layout.addWidget(QLabel("Hillshade:"))
        hillshade_layout.addWidget(self.dem_hillshade_slider, 1)
        view_layout.addLayout(hillshade_layout)
        azimuth_layout = QHBoxLayout()
        azimuth_layout.addWidget(QLabel("Azimuth:"))
        azimuth_layout.addWidget(self.dem_azimuth_slider, 1)
        view_layout.addLayout(azimuth_layout)
        altitude_layout = QHBoxLayout()
        altitude_layout.addWidget(QLabel("Altitude:"))
        altitude_layout.addWidget(self.dem_altitude_slider, 1)
        view_layout.addLayout(altitude_layout)
        view_layout.addWidget(self.apply_dem_btn)
        
        view_layout.addStretch()

        self.annotation_edit = QLineEdit()
        self.annotation_edit.setPlaceholderText("Text for latest clicked location")
        self.add_annotation_btn = QPushButton("Add Annotation")
        self.profile_samples = QSpinBox()
        self.profile_samples.setRange(2, 5000)
        self.profile_samples.setValue(200)
        self.extract_profile_btn = QPushButton("Extract DEM Profile (last 2 clicks)")

        self.annotation_box = QGroupBox("Add Annotation")
        annotation_layout = QVBoxLayout(self.annotation_box)
        annotation_layout.setSpacing(10)
        annotation_layout.setContentsMargins(10, 10, 10, 10)
        annotation_layout.addWidget(self.annotation_edit)
        annotation_layout.addWidget(self.add_annotation_btn)
        annotation_layout.addStretch()

        self.profile_box = QGroupBox("Extract Profile")
        profile_layout = QVBoxLayout(self.profile_box)
        profile_layout.setSpacing(10)
        profile_layout.setContentsMargins(10, 10, 10, 10)
        samples_row = QHBoxLayout()
        samples_row.setSpacing(8)
        samples_row.addWidget(QLabel("Samples:"))
        samples_row.addWidget(self.profile_samples)
        samples_row.addStretch()
        profile_layout.addLayout(samples_row)
        profile_layout.addWidget(self.extract_profile_btn)
        profile_layout.addStretch()

        self.click_label = QLabel("None")
        self.measure_label = QLabel("N/A")
        self.status_box = QTextEdit()
        self.status_box.setReadOnly(True)
        self.status_box.setMaximumHeight(120)
        
        self.log_box = QGroupBox("Activity Log")
        log_layout = QVBoxLayout(self.log_box)
        log_layout.setSpacing(8)
        log_layout.setContentsMargins(10, 10, 10, 10)
        click_row = QHBoxLayout()
        click_row.addWidget(QLabel("Last Click:"))
        click_row.addWidget(self.click_label, 1)
        log_layout.addLayout(click_row)
        measure_row = QHBoxLayout()
        measure_row.addWidget(QLabel("Distance:"))
        measure_row.addWidget(self.measure_label, 1)
        log_layout.addLayout(measure_row)
        log_layout.addWidget(QLabel("Messages:"))
        log_layout.addWidget(self.status_box, 1)
        self.data_section = QWidget(self)
        data_layout = QVBoxLayout(self.data_section)
        data_layout.setContentsMargins(8, 8, 8, 8)
        data_layout.setSpacing(10)
        data_layout.addWidget(self.upload_box)
        data_layout.addWidget(self.ingest_progress_box)
        data_layout.addWidget(self.assets_box, 1)
        
        self.search_section = QWidget(self)
        search_section_layout = QVBoxLayout(self.search_section)
        search_section_layout.setContentsMargins(8, 8, 8, 8)
        search_section_layout.setSpacing(10)
        search_section_layout.addWidget(self.search_box)
        
        self.view_section = QWidget(self)
        view_section_layout = QVBoxLayout(self.view_section)
        view_section_layout.setContentsMargins(8, 8, 8, 8)
        view_section_layout.setSpacing(10)
        view_section_layout.addWidget(self.view_box)
        
        self.analysis_section = QWidget(self)
        analysis_layout = QVBoxLayout(self.analysis_section)
        analysis_layout.setContentsMargins(8, 8, 8, 8)
        analysis_layout.setSpacing(10)
        analysis_layout.addWidget(self.annotation_box)
        analysis_layout.addWidget(self.profile_box)
        analysis_layout.addWidget(self.log_box, 1)

        self.sections.addItem(self.data_section, "Data")
        self.search_section_index = self.sections.addItem(self.search_section, "Search")
        self.sections.addItem(self.view_section, "Display")
        self.sections.addItem(self.analysis_section, "Annotate")

        root.addWidget(self.sections, 1)
        self._apply_panel_styles()
        self._apply_widget_shadows()
        self.configure_for_mode(app_mode)

    def configure_for_mode(self, app_mode: DesktopAppMode) -> None:
        """Configure panel for server or client mode."""
        if app_mode == DesktopAppMode.SERVER:
            # Server mode: show sections WITHOUT toolbox tabs
            self.sections.setVisible(False)
            
            # Add server sections directly to main layout
            root_layout = self.layout()
            # Remove the toolbox before adding sections
            for i in range(root_layout.count()):
                if root_layout.itemAt(i).widget() == self.sections:
                    root_layout.takeAt(i)
                    break
            
            # Add server-specific sections directly
            root_layout.addWidget(self.upload_box)
            root_layout.addWidget(self.ingest_progress_box)
            root_layout.addWidget(self.uploaded_box, 1)
            root_layout.addStretch()
            
            # Connect refresh button
            self.assets_refresh_btn.clicked.connect(self.refresh_uploaded_assets)
            # Show loading state initially - will be populated by controller
            self.uploaded_assets_list.setRowCount(1)
            self.uploaded_assets_list.setItem(0, 0, QTableWidgetItem("Loading..."))
            
            # Hide client-only sections
            self.search_box.setVisible(False)
            self.view_box.setVisible(False)
            self.annotation_box.setVisible(False)
            self.profile_box.setVisible(False)
            self.log_box.setVisible(False)
            self.assets_box.setVisible(False)
        else:
            # Client mode: show toolbox tabs
            self.sections.setVisible(True)
            self.upload_box.setVisible(False)
            self.ingest_progress_box.setVisible(False)
            self.search_box.setVisible(True)
            self.view_box.setVisible(True)
            self.annotation_box.setVisible(True)
            self.profile_box.setVisible(True)
            self.log_box.setVisible(True)
            self.assets_box.setVisible(True)
            self.sections.setCurrentIndex(self.search_section_index)

    def log(self, message: str) -> None:
        self.status_box.append(message)

    def append_ingest_detail(self, message: str) -> None:
        self.ingest_details.append(message)

    def refresh_uploaded_assets(self) -> None:
        """Fetch and display list of uploaded assets from the catalog."""
        if not self.api_client:
            self.uploaded_assets_list.setRowCount(1)
            self.uploaded_assets_list.setItem(0, 0, QTableWidgetItem("Waiting for API..."))
            return
        
        try:
            assets = self.api_client.list_assets()
            self.uploaded_assets_list.setRowCount(0)
            
            if not assets:
                self.uploaded_assets_list.setRowCount(1)
                self.uploaded_assets_list.setItem(0, 0, QTableWidgetItem("No assets ingested yet"))
                return
            
            # Sort by ingest timestamp (most recent first)
            sorted_assets = sorted(
                assets,
                key=lambda a: a.get('created_at', ''),
                reverse=True
            )
            
            for row, asset in enumerate(sorted_assets):
                filename = asset.get('file_name', 'Unknown')
                timestamp = asset.get('created_at', None)
                kind = asset.get('kind', 'Unknown').upper()
                
                # Format date in IST (Indian Standard Time: UTC+5:30) - date only
                if timestamp:
                    try:
                        # Handle ISO format timestamp
                        from datetime import timezone, timedelta
                        if isinstance(timestamp, str):
                            # Strip 'Z' and parse as ISO format
                            ts = timestamp.replace('Z', '+00:00')
                            dt = datetime.fromisoformat(ts)
                        else:
                            dt = timestamp
                        
                        # If datetime is naive (no timezone), assume it's UTC
                        if dt.tzinfo is None:
                            utc = timezone(timedelta(0))
                            dt = dt.replace(tzinfo=utc)
                        
                        # Convert UTC to IST (UTC+5:30)
                        ist_offset = timezone(timedelta(hours=5, minutes=30))
                        dt_ist = dt.astimezone(ist_offset)
                        formatted_date = dt_ist.strftime('%d-%b-%Y')
                    except Exception:
                        formatted_date = str(timestamp)
                else:
                    formatted_date = 'Unknown'
                
                # Add row to table
                self.uploaded_assets_list.insertRow(row)
                file_item = QTableWidgetItem(filename)
                file_item.setData(Qt.ItemDataRole.UserRole, asset)
                self.uploaded_assets_list.setItem(row, 0, file_item)
                self.uploaded_assets_list.setItem(row, 1, QTableWidgetItem(kind))
                self.uploaded_assets_list.setItem(row, 2, QTableWidgetItem(formatted_date))
        
        except Exception as e:
            self.uploaded_assets_list.setRowCount(1)
            self.uploaded_assets_list.setItem(0, 0, QTableWidgetItem(f"Error loading assets: {str(e)}"))

    def _apply_panel_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background: #f5f5f5;
                color: #1a1a1a;
            }
            QToolBox {
                background: transparent;
                color: #1a1a1a;
            }
            QToolBox::tab {
                background: #e8e8e8;
                border: 1px solid #b0b0b0;
                border-radius: 4px;
                padding: 10px 16px;
                margin: 2px 2px;
                font-weight: 700;
                font-size: 13px;
                color: #1a1a1a;
                text-align: center;
            }
            QToolBox::tab:selected {
                background: #ffffff;
                color: #0044aa;
                border: 2px solid #0066cc;
                padding: 9px 15px;
                font-weight: 700;
            }
            QToolBox::tab:hover {
                background: #f5f5f5;
            }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                margin-top: 12px;
                padding: 14px;
                font-weight: 700;
                font-size: 14px;
                color: #1a1a1a;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
                color: #1a1a1a;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit {
                background: #ffffff;
                border: 1px solid #d0d0d0;
                border-radius: 4px;
                min-height: 32px;
                padding: 6px 10px;
                font-size: 13px;
                color: #1a1a1a;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                border: 2px solid #0066cc;
            }
            QPushButton {
                background: #e8e8e8;
                color: #1a1a1a;
                border: 1px solid #c0c0c0;
                border-radius: 4px;
                padding: 9px 14px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #f0f0f0;
                border: 1px solid #a0a0a0;
            }
            QPushButton:pressed {
                background: #d8d8d8;
                border: 1px solid #808080;
            }
            QSlider::groove:horizontal {
                border: 1px solid #d0d0d0;
                height: 6px;
                background: #e8e8e8;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #0066cc;
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
                border: 1px solid #0066cc;
            }
            QProgressBar {
                border: 1px solid #d0d0d0;
                border-radius: 4px;
                background: #f0f0f0;
                text-align: center;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background: #0066cc;
                border-radius: 3px;
            }
            QLabel {
                color: #1a1a1a;
                font-size: 13px;
            }
            QFormLayout {
                font-size: 13px;
            }
            """
        )

    def _apply_widget_shadows(self) -> None:
        # Apply subtle shadows to buttons for traditional desktop GUI look
        for button in (
            self.browse_btn,
            self.preview_btn,
            self.save_btn,
            self.assets_refresh_btn,
            self.refresh_assets_btn,
            self.add_layer_btn,
            self.search_point_btn,
            self.search_bbox_btn,
            self.search_draw_box_btn,
            self.search_draw_polygon_btn,
            self.search_finish_polygon_btn,
            self.search_clear_geometry_btn,
            self.search_from_draw_btn,
            self.apply_visual_btn,
            self.rotate_left_btn,
            self.rotate_right_btn,
            self.apply_dem_btn,
            self.add_annotation_btn,
            self.extract_profile_btn,
        ):
            effect = QGraphicsDropShadowEffect(button)
            effect.setBlurRadius(4.0)
            effect.setOffset(1.0, 1.0)
            effect.setColor(QColor(0, 0, 0, 60))
            button.setGraphicsEffect(effect)

    def set_layer_loading(self, active: bool, message: str) -> None:
        self.layer_load_status.setText(message)
        if active:
            self.layer_load_progress.setRange(0, 0)
            self.layer_load_progress.setVisible(True)
            return
        self.layer_load_progress.setRange(0, 100)
        self.layer_load_progress.setValue(100)
        self.layer_load_progress.setVisible(False)
