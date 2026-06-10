"""High-performance 3D LiDAR Viewer using pyqtgraph and laspy.

Leverages GPU-accelerated OpenGL rendering for dense point clouds
and offloads loading to an asynchronous thread.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pyqtgraph.opengl as gl
from qtpy.QtCore import Qt, QThread, Signal
from qtpy.QtGui import QVector3D
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger("client_desktop.lidar_viewer")


class LASLoaderThread(QThread):
    """Worker thread to read LAS/LAZ file and parse points asynchronously."""
    progress = Signal(int)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, file_path: str, stride: int = 1):
        super().__init__()
        self.file_path = file_path
        self.stride = stride
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            import laspy

            if self._is_cancelled:
                return

            self.progress.emit(10)
            logger.info("Opening LAS file: %s", self.file_path)
            
            with laspy.open(self.file_path) as fh:
                if self._is_cancelled:
                    return
                # Only read header first to get total points
                total_points = fh.header.point_count
                self.progress.emit(25)
                
                # Ingest full data
                las = fh.read()
            
            if self._is_cancelled:
                return
            self.progress.emit(50)

            # Slice based on stride
            x = np.array(las.x)[::self.stride]
            y = np.array(las.y)[::self.stride]
            z = np.array(las.z)[::self.stride]
            
            if self._is_cancelled:
                return
            self.progress.emit(70)

            # Offset points to prevent floating-point precision jitter in OpenGL
            x_offset, y_offset, z_offset = np.mean(x), np.mean(y), np.mean(z)
            points = np.vstack((x - x_offset, y - y_offset, z - z_offset)).transpose().astype(np.float32)

            # 2. Extract Intensity if available
            intensity = None
            if hasattr(las, 'intensity'):
                try:
                    intensity = np.array(las.intensity)[::self.stride].astype(np.float32)
                except Exception as e:
                    logger.debug("Failed to extract intensity: %s", e)

            # 3. Extract RGB if available
            rgb_colors = None
            if hasattr(las, 'red') and hasattr(las, 'green') and hasattr(las, 'blue'):
                try:
                    r_raw = np.array(las.red)[::self.stride]
                    g_raw = np.array(las.green)[::self.stride]
                    b_raw = np.array(las.blue)[::self.stride]
                    
                    if r_raw.any() or g_raw.any() or b_raw.any():
                        max_val = max(np.max(r_raw), np.max(g_raw), np.max(b_raw))
                        scale = 65535.0 if max_val > 255 else 255.0
                        r = (r_raw / scale).astype(np.float32)
                        g = (g_raw / scale).astype(np.float32)
                        b = (b_raw / scale).astype(np.float32)
                        rgb_colors = np.vstack((r, g, b, np.ones_like(r))).transpose()
                except Exception as e:
                    logger.debug("Failed to extract colors: %s", e)

            if self._is_cancelled:
                return
            self.progress.emit(90)

            result = {
                "points": points,
                "raw_z": z,
                "intensity": intensity,
                "rgb_colors": rgb_colors,
                "point_count": total_points,
                "offset": (x_offset, y_offset, z_offset)
            }
            
            if self._is_cancelled:
                return
            self.finished.emit(result)

        except Exception as exc:
            logger.exception("LAS Loader Thread encountered an error")
            self.error.emit(str(exc))


class FloatingControlPanel(QFrame):
    """Sleek transparent dark floating panel for LiDAR controls."""
    
    def __init__(self, parent: QWidget, on_close_callback=None):
        super().__init__(parent)
        self.on_close_callback = on_close_callback
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        
        self.setStyleSheet("""
            QFrame {
                background-color: rgba(15, 23, 42, 220); /* Slate 900 with opacity */
                border: 1px solid rgba(71, 85, 105, 180); /* Slate 600 */
                border-radius: 8px;
            }
            QLabel {
                color: #f8fafc; /* Slate 50 */
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial;
                font-size: 11px;
                border: none;
                background: transparent;
            }
            QLabel#title {
                font-size: 13px;
                font-weight: bold;
                color: #38bdf8; /* Sky 400 */
            }
            QLabel#subtitle {
                font-size: 10px;
                color: #94a3b8; /* Slate 400 */
                margin-top: -2px;
            }
            QComboBox {
                background-color: #334155; /* Slate 700 */
                color: white;
                border: 1px solid #475569;
                border-radius: 4px;
                padding: 4px 6px;
                min-width: 100px;
            }
            QComboBox:hover {
                border-color: #38bdf8;
            }
            QSlider::groove:horizontal {
                border: 1px solid #475569;
                height: 5px;
                background: #1e293b;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #38bdf8;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #f8fafc;
                border: 1px solid #475569;
                width: 12px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 6px;
            }
            QPushButton {
                background-color: #2563eb; /* Blue 600 */
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 10px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton#resetBtn {
                background-color: #475569; /* Slate 600 */
            }
            QPushButton#resetBtn:hover {
                background-color: #64748b;
            }
            QPushButton#closeBtn {
                background-color: #ef4444; /* Red 500 */
            }
            QPushButton#closeBtn:hover {
                background-color: #dc2626;
            }
            QCheckBox {
                color: #cbd5e1;
                background: transparent;
                border: none;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
            }
        """)
        
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        
        # Title Row
        title_label = QLabel("3D LiDAR Viewer", self)
        title_label.setObjectName("title")
        subtitle_label = QLabel("Native Hardware-Accelerated View", self)
        subtitle_label.setObjectName("subtitle")
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        
        # Horizontal Separator
        line = QFrame(self)
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: rgba(71, 85, 105, 100); border: none; height: 1px;")
        layout.addWidget(line)
        
        # File info section
        info_layout = QGridLayout()
        info_layout.setSpacing(6)
        
        info_layout.addWidget(QLabel("Dataset:", self), 0, 0)
        self.lbl_name = QLabel("None", self)
        self.lbl_name.setStyleSheet("font-weight: bold;")
        info_layout.addWidget(self.lbl_name, 0, 1)
        
        info_layout.addWidget(QLabel("Total Pts:", self), 1, 0)
        self.lbl_total = QLabel("0", self)
        info_layout.addWidget(self.lbl_total, 1, 1)
        
        info_layout.addWidget(QLabel("Rendered:", self), 2, 0)
        self.lbl_rendered = QLabel("0 (100%)", self)
        info_layout.addWidget(self.lbl_rendered, 2, 1)
        
        layout.addLayout(info_layout)
        
        # Controls section
        ctrl_layout = QGridLayout()
        ctrl_layout.setSpacing(8)
        
        # Stride density dropdown
        ctrl_layout.addWidget(QLabel("Density Stride:", self), 0, 0)
        self.combo_stride = QComboBox(self)
        self.combo_stride.addItem("Auto (Balanced)", 0)
        self.combo_stride.addItem("Full (100%)", 1)
        self.combo_stride.addItem("Medium (50%)", 2)
        self.combo_stride.addItem("Low (20%)", 5)
        self.combo_stride.addItem("Very Low (10%)", 10)
        self.combo_stride.addItem("Draft (1%)", 100)
        ctrl_layout.addWidget(self.combo_stride, 0, 1)
        
        # Color Map
        ctrl_layout.addWidget(QLabel("Color Mode:", self), 1, 0)
        self.combo_color = QComboBox(self)
        self.combo_color.addItem("Elevation Ramp", "elevation")
        self.combo_color.addItem("Intensity", "intensity")
        self.combo_color.addItem("RGB (Asset)", "rgb")
        self.combo_color.addItem("Solid Orange", "orange")
        self.combo_color.addItem("Solid Teal", "teal")
        ctrl_layout.addWidget(self.combo_color, 1, 1)
        
        # Point Size
        ctrl_layout.addWidget(QLabel("Point Size:", self), 2, 0)
        size_layout = QHBoxLayout()
        size_layout.setSpacing(6)
        self.slider_size = QSlider(Qt.Orientation.Horizontal, self)
        self.slider_size.setRange(10, 80)  # Maps to 1.0 - 8.0
        self.slider_size.setValue(15)
        self.lbl_size_val = QLabel("1.5", self)
        self.lbl_size_val.setFixedWidth(20)
        size_layout.addWidget(self.slider_size)
        size_layout.addWidget(self.lbl_size_val)
        ctrl_layout.addLayout(size_layout, 2, 1)
        
        # Toggle Grid Checkbox
        self.chk_grid = QCheckBox("Show Grid overlay", self)
        self.chk_grid.setChecked(True)
        ctrl_layout.addWidget(self.chk_grid, 3, 0, 1, 2)
        
        layout.addLayout(ctrl_layout)
        
        # Spacer
        layout.addSpacing(4)
        
        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)
        
        self.btn_reset = QPushButton("Reset Camera", self)
        self.btn_reset.setObjectName("resetBtn")
        btn_layout.addWidget(self.btn_reset)
        
        self.btn_close = QPushButton("Close Viewer", self)
        self.btn_close.setObjectName("closeBtn")
        btn_layout.addWidget(self.btn_close)
        
        layout.addLayout(btn_layout)
        
        # Connect internal signal for slider value label update
        self.slider_size.valueChanged.connect(self._on_slider_changed)
        if self.on_close_callback:
            self.btn_close.clicked.connect(self.on_close_callback)

    def _on_slider_changed(self, val: int):
        self.lbl_size_val.setText(f"{val/10.0:.1f}")


class LoadingOverlay(QWidget):
    """Transparent backdrop overlay with progress bar and loading detail."""
    
    def __init__(self, parent: QWidget, on_cancel_callback=None):
        super().__init__(parent)
        self.on_cancel_callback = on_cancel_callback
        
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(15, 23, 42, 210);
            }
            QLabel {
                color: #f8fafc;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial;
                font-size: 13px;
                font-weight: 500;
                background: transparent;
            }
            QProgressBar {
                border: 1px solid #475569;
                border-radius: 6px;
                text-align: center;
                background-color: #1e293b;
                color: white;
                font-weight: bold;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #38bdf8;
                border-radius: 5px;
            }
            QPushButton {
                background-color: #ef4444;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #dc2626;
            }
        """)
        
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(15)
        
        self.lbl_msg = QLabel("Ingesting point cloud data...", self)
        self.lbl_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_msg)
        
        self.progress = QProgressBar(self)
        self.progress.setFixedWidth(300)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        
        self.btn_cancel = QPushButton("Cancel Loading", self)
        self.btn_cancel.setFixedWidth(120)
        layout.addWidget(self.btn_cancel)
        
        if self.on_cancel_callback:
            self.btn_cancel.clicked.connect(self.on_cancel_callback)


class LiDARViewerWidget(QWidget):
    """High-performance point cloud GL canvas widget with overlay control panel."""

    def __init__(self, parent=None, controller=None):
        super().__init__(parent)
        self.controller = controller
        
        self.current_file_path = None
        self.current_file_name = None
        self.loader_thread = None
        self.finished_threads = []
        self.points_data = None
        self.current_scatter = None
        self.grid = None
        
        # Main Layout (Fill screen with GL viewport)
        self.layout_main = QVBoxLayout(self)
        self.layout_main.setContentsMargins(0, 0, 0, 0)
        self.layout_main.setSpacing(0)
        
        # 3D GL Viewer Window
        self.gl_viewer = gl.GLViewWidget(self)
        self.gl_viewer.opts['distance'] = 100
        self.layout_main.addWidget(self.gl_viewer)
        
        # Initialize grid
        self._setup_grid()
        
        # Floating control panel
        self.controls = FloatingControlPanel(self, on_close_callback=self.close_viewer)
        self.controls.hide()
        
        # Floating loading overlay
        self.loading_overlay = LoadingOverlay(self, on_cancel_callback=self.cancel_loading)
        self.loading_overlay.hide()
        
        # Wire up controls panel signals
        self.controls.combo_stride.currentIndexChanged.connect(self._on_stride_changed)
        self.controls.combo_color.currentIndexChanged.connect(self._on_color_mode_changed)
        self.controls.slider_size.valueChanged.connect(self._on_point_size_changed)
        self.controls.chk_grid.toggled.connect(self._toggle_grid_visible)
        self.controls.btn_reset.clicked.connect(self.reset_camera)

    def _setup_grid(self):
        self.grid = gl.GLGridItem()
        self.grid.setSize(x=500, y=500, z=1)
        self.grid.setSpacing(x=50, y=50, z=1)
        self.gl_viewer.addItem(self.grid)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Place control panel floating in top-right corner
        margin = 15
        panel_width = 300
        panel_height = self.controls.sizeHint().height()
        self.controls.setGeometry(
            self.width() - panel_width - margin,
            margin,
            panel_width,
            panel_height
        )
        # Stretch loading overlay across entire widget
        self.loading_overlay.setGeometry(self.rect())

    def load_las_file(self, file_path: str, file_name: str):
        """Ingest point cloud from the file asynchronously."""
        if self.current_file_path == file_path:
            # Already loaded this dataset
            return
            
        self.cancel_loading()
        
        self.current_file_path = file_path
        self.current_file_name = file_name
        self.controls.lbl_name.setText(file_name)
        
        # Switch controls dropdown index to Auto
        self.controls.combo_stride.blockSignals(True)
        self.controls.combo_stride.setCurrentIndex(0)
        self.controls.combo_stride.blockSignals(False)
        
        # Determine initial decimation stride based on total file size
        # Very simple metric: if file > 100MB, use custom stride initially to load faster
        file_size_mb = Path(file_path).stat().st_size / (1024.0 * 1024.0)
        initial_stride = 1
        if file_size_mb > 150:
            initial_stride = 5
        elif file_size_mb > 50:
            initial_stride = 2
            
        self._start_loader(file_path, initial_stride)

    def _start_loader(self, file_path: str, stride: int):
        self.cancel_loading()
        self.loading_overlay.lbl_msg.setText(f"Ingesting point cloud details from {self.current_file_name}...")
        self.loading_overlay.progress.setValue(0)
        self.loading_overlay.show()
        self.controls.hide()
        
        self.loader_thread = LASLoaderThread(file_path, stride)
        self.loader_thread.progress.connect(self.loading_overlay.progress.setValue)
        self.loader_thread.finished.connect(self._on_load_success)
        self.loader_thread.error.connect(self._on_load_error)
        self.loader_thread.start()

    def _clean_finished_threads(self):
        self.finished_threads = [t for t in self.finished_threads if t.isRunning()]

    def cancel_loading(self):
        if self.loader_thread and self.loader_thread.isRunning():
            try:
                self.loader_thread.progress.disconnect()
                self.loader_thread.finished.disconnect()
                self.loader_thread.error.disconnect()
            except Exception:
                pass
            self.loader_thread.cancel()
            self.loader_thread.wait()
            self.finished_threads.append(self.loader_thread)
        self.loader_thread = None
        self._clean_finished_threads()
        self.loading_overlay.hide()

    def close_viewer(self):
        """Switches back to map and keeps visibility."""
        self.cancel_loading()
        window = self.window()
        
        if hasattr(window, "set_canvas_index"):
            window.set_canvas_index(0)
        elif hasattr(window, "canvas_stack"):
            window.canvas_stack.setCurrentIndex(0)

    def _on_load_success(self, data: dict):
        if self.loader_thread:
            self.finished_threads.append(self.loader_thread)
            self.loader_thread = None
        self._clean_finished_threads()
        self.loading_overlay.hide()
        self.points_data = data
        
        # Update point count info
        total_pts = data["point_count"]
        rendered_pts = len(data["points"])
        percent = (rendered_pts / total_pts) * 100
        
        self.controls.lbl_total.setText(f"{total_pts:,} pts")
        self.controls.lbl_rendered.setText(f"{rendered_pts:,} pts ({percent:.1f}%)")
        
        # Configure color mode combo options based on file attributes
        self.controls.combo_color.blockSignals(True)
        # Enable/Disable RGB color option conditionally
        rgb_item_idx = self.controls.combo_color.findData("rgb")
        if data["rgb_colors"] is not None:
            self.controls.combo_color.setItemText(rgb_item_idx, "RGB (Asset)")
            # Default to RGB mode if available
            self.controls.combo_color.setCurrentIndex(rgb_item_idx)
        else:
            self.controls.combo_color.setItemText(rgb_item_idx, "RGB (Not available)")
            self.controls.combo_color.setCurrentIndex(0) # Default to Elevation Ramp
            
        # Enable/Disable Intensity option
        intensity_item_idx = self.controls.combo_color.findData("intensity")
        if data["intensity"] is not None:
            self.controls.combo_color.setItemText(intensity_item_idx, "Intensity")
        else:
            self.controls.combo_color.setItemText(intensity_item_idx, "Intensity (Not available)")
            
        self.controls.combo_color.blockSignals(False)
        
        # Render the cloud!
        self._render_cloud()
        
        # Focus camera on the centroid (which corresponds to origin 0,0,0 after offset shift)
        self.reset_camera()
        self.controls.show()

    def _on_load_error(self, err_msg: str):
        if self.loader_thread:
            self.finished_threads.append(self.loader_thread)
            self.loader_thread = None
        self._clean_finished_threads()
        self.loading_overlay.hide()
        logger.error("Failed to load point cloud file asynchronously: %s", err_msg)
        if self.controller:
            self.controller.panel.log(f"Point Cloud Load Failed: {err_msg}")
        self.close_viewer()

    def _on_stride_changed(self, index: int):
        if not self.current_file_path:
            return
            
        stride_val = self.controls.combo_stride.itemData(index)
        
        if stride_val == 0:
            # Auto-balanced: target roughly 1.5 million points
            # Let's inspect total points
            total_points = self.points_data["point_count"] if self.points_data else 6000000
            stride_val = max(1, total_points // 1500000)
            
        logger.info("Re-decimating point cloud with stride: %d", stride_val)
        self._start_loader(self.current_file_path, stride_val)

    def _on_color_mode_changed(self, index: int):
        self._render_cloud()

    def _on_point_size_changed(self, val: int):
        if self.current_scatter:
            self.current_scatter.setData(size=val / 10.0)

    def _toggle_grid_visible(self, checked: bool):
        if checked:
            if self.grid not in self.gl_viewer.items:
                self.gl_viewer.addItem(self.grid)
        else:
            if self.grid in self.gl_viewer.items:
                self.gl_viewer.removeItem(self.grid)

    def reset_camera(self):
        """Fit camera center to origin and reset bounds."""
        self.gl_viewer.opts['center'] = QVector3D(0, 0, 0)
        self.gl_viewer.opts['distance'] = 80
        self.gl_viewer.update()

    def _render_cloud(self):
        if not self.points_data:
            return
            
        # Clean up existing scatter plot item
        if self.current_scatter:
            try:
                self.gl_viewer.removeItem(self.current_scatter)
            except Exception as e:
                logger.debug("Error removing item: %s", e)
            self.current_scatter = None
            
        points = self.points_data["points"]
        color_mode = self.controls.combo_color.currentData()
        
        colors = None
        if color_mode == "rgb" and self.points_data["rgb_colors"] is not None:
            colors = self.points_data["rgb_colors"]
        elif color_mode == "intensity" and self.points_data["intensity"] is not None:
            # Map Intensity to red-ish/fire scale
            intensity = self.points_data["intensity"]
            min_i, max_i = np.min(intensity), np.max(intensity)
            norm_i = (intensity - min_i) / (max_i - min_i + 1e-6)
            
            colors = np.zeros((len(intensity), 4))
            colors[:, 0] = norm_i          # Red
            colors[:, 1] = norm_i * 0.6    # Green (Orange-yellow ramp)
            colors[:, 2] = 0.2             # Low blue
            colors[:, 3] = 1.0             # Alpha
        elif color_mode == "orange":
            colors = np.zeros((len(points), 4))
            colors[:, 0] = 0.95            # Red
            colors[:, 1] = 0.50            # Green (Orange)
            colors[:, 2] = 0.15            # Blue
            colors[:, 3] = 1.0
        elif color_mode == "teal":
            colors = np.zeros((len(points), 4))
            colors[:, 0] = 0.10            # Red
            colors[:, 1] = 0.75            # Green (Teal)
            colors[:, 2] = 0.80            # Blue
            colors[:, 3] = 1.0
        else:
            # Default or fallback color mapping is elevation ramp
            # Map height (Z values) to a gorgeous spectral gradient
            raw_z = self.points_data["raw_z"]
            min_z, max_z = np.min(raw_z), np.max(raw_z)
            norm_z = (raw_z - min_z) / (max_z - min_z + 1e-6)
            
            # Vectorized blue -> green -> red spectral ramp
            colors = np.zeros((len(points), 4))
            r = np.clip(4.0 * norm_z - 2.0, 0.0, 1.0)
            g = np.clip(1.5 - np.abs(4.0 * norm_z - 2.0), 0.0, 1.0)
            b = np.clip(2.0 - 4.0 * norm_z, 0.0, 1.0)
            
            colors[:, 0] = r
            colors[:, 1] = g
            colors[:, 2] = b
            colors[:, 3] = 1.0

        size_val = self.controls.slider_size.value() / 10.0
        
        # Instantiate optimized GL scatter plot item
        self.current_scatter = gl.GLScatterPlotItem(
            pos=points,
            color=colors,
            size=size_val,
            pxMode=True
        )
        self.gl_viewer.addItem(self.current_scatter)
        self.gl_viewer.update()
