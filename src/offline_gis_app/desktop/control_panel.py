from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class ControlPanel(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumWidth(340)
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Select GeoTIFF / JP2 / MBTiles / DEM path...")
        self.browse_btn = QPushButton("Browse")
        self.register_btn = QPushButton("Register & Load")

        upload_box = QGroupBox("Data Ingestion")
        upload_layout = QVBoxLayout(upload_box)
        upload_layout.addWidget(self.path_edit)
        row = QHBoxLayout()
        row.addWidget(self.browse_btn)
        row.addWidget(self.register_btn)
        upload_layout.addLayout(row)
        root.addWidget(upload_box)

        self.assets_combo = QComboBox()
        self.refresh_assets_btn = QPushButton("Refresh Assets")
        self.add_layer_btn = QPushButton("Add Selected Layer")
        self.fly_to_btn = QPushButton("Fly To Selected")

        assets_box = QGroupBox("Catalog & Layers")
        assets_layout = QVBoxLayout(assets_box)
        assets_layout.addWidget(self.assets_combo)
        row2 = QHBoxLayout()
        row2.addWidget(self.refresh_assets_btn)
        row2.addWidget(self.add_layer_btn)
        assets_layout.addLayout(row2)
        assets_layout.addWidget(self.fly_to_btn)
        root.addWidget(assets_box)

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

        view_box = QGroupBox("View Controls")
        view_form = QFormLayout(view_box)
        view_form.addRow("Brightness", self.brightness_slider)
        view_form.addRow("Contrast", self.contrast_slider)
        view_form.addRow("Pitch", self.pitch_slider)
        rotate_row = QHBoxLayout()
        rotate_row.addWidget(self.rotate_left_btn)
        rotate_row.addWidget(self.rotate_right_btn)
        view_form.addRow("Rotate", rotate_row)
        view_form.addRow("DEM Exaggeration", self.dem_exaggeration_slider)
        view_form.addRow("DEM Hillshade", self.dem_hillshade_slider)
        view_form.addRow("DEM Azimuth", self.dem_azimuth_slider)
        view_form.addRow("DEM Altitude", self.dem_altitude_slider)
        view_form.addRow(self.apply_dem_btn)
        view_form.addRow(self.apply_visual_btn)
        root.addWidget(view_box)

        self.annotation_edit = QLineEdit()
        self.annotation_edit.setPlaceholderText("Text for latest clicked location")
        self.add_annotation_btn = QPushButton("Add Annotation")
        self.profile_samples = QSpinBox()
        self.profile_samples.setRange(2, 5000)
        self.profile_samples.setValue(200)
        self.extract_profile_btn = QPushButton("Extract DEM Profile (last 2 clicks)")

        tools_box = QGroupBox("Annotation & Profile")
        tools_layout = QFormLayout(tools_box)
        tools_layout.addRow("Annotation", self.annotation_edit)
        tools_layout.addRow(self.add_annotation_btn)
        tools_layout.addRow("Profile samples", self.profile_samples)
        tools_layout.addRow(self.extract_profile_btn)
        root.addWidget(tools_box)

        self.click_label = QLabel("Last click: none")
        self.measure_label = QLabel("Last distance: n/a")
        self.status_box = QTextEdit()
        self.status_box.setReadOnly(True)
        self.status_box.setMaximumHeight(160)

        log_box = QGroupBox("Live Status")
        log_layout = QVBoxLayout(log_box)
        log_layout.addWidget(self.click_label)
        log_layout.addWidget(self.measure_label)
        log_layout.addWidget(self.status_box)
        root.addWidget(log_box)

        root.addStretch(1)

    def log(self, message: str) -> None:
        self.status_box.append(message)
