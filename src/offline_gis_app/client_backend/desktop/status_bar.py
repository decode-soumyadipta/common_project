"""
status_bar.py
=============
Clean, minimal status bar for the Offline 3-D GIS desktop application.

Layout:
  ┌──────────────────────────────────────────────────────────────────────────┐
  │ [Progress Bar] │ Lon: 87.231456° │ Lat: 23.710234° │ UTM: 45N 500000 mE │ Elev: 312.45 m │ EPSG:4326 │
  └──────────────────────────────────────────────────────────────────────────┘

Signals consumed (from WebBridge via the QWebChannel pipe):
  - mouseCoordinates(lon: float, lat: float, elevation_m: float)
  - cameraChanged(scale_denominator: float, heading_deg: float)
  - loadingProgress(percent: int, message: str)
"""

from __future__ import annotations

import math

from qtpy.QtCore import Qt, Slot
from qtpy.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QStatusBar,
    QWidget,
)
from pyproj import Transformer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_separator() -> QFrame:
    """Create a vertical separator line for the status bar.
    
    Returns:
        QFrame configured as a vertical line separator.
    """
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.VLine)
    sep.setFrameShadow(QFrame.Shadow.Sunken)
    sep.setStyleSheet("color: rgba(200,200,200,0.3);")
    sep.setFixedWidth(1)
    return sep


def _coord_box(text: str = "—", tooltip: str = "", min_width: int = 120) -> QFrame:
    """Create a styled coordinate display box.
    
    Args:
        text: Initial text content.
        tooltip: Tooltip text.
        min_width: Minimum width in pixels.
        
    Returns:
        QFrame containing a label with the coordinate value.
    """
    box = QFrame()
    box.setObjectName("coordBox")
    box.setStyleSheet("""
        QFrame#coordBox {
            background: #ffffff;
            border: 1px solid #b0bac5;
            border-radius: 3px;
            padding: 2px 4px;
        }
        QLabel {
            color: #0a1929;
            font-size: 11px;
            font-family: 'Menlo', 'Consolas', 'Monaco', monospace;
            font-weight: 600;
            padding: 1px 3px;
            margin: 0px;
            background: transparent;
        }
    """)
    box.setMinimumWidth(min_width)
    
    layout = QHBoxLayout(box)
    layout.setContentsMargins(4, 2, 4, 2)
    layout.setSpacing(0)
    
    label = QLabel(text)
    label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
    label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
    if tooltip:
        label.setToolTip(tooltip)
    
    layout.addWidget(label)
    box.label = label  # Store reference for easy access
    
    return box


def _utm_epsg_for_lon_lat(lon: float, lat: float) -> int:
    """Calculate the UTM EPSG code for given coordinates.
    
    Args:
        lon: Longitude in degrees.
        lat: Latitude in degrees.
        
    Returns:
        EPSG code for the appropriate UTM zone.
    """
    zone = int((lon + 180.0) // 6.0) + 1
    return 32600 + zone if lat >= 0 else 32700 + zone


# ---------------------------------------------------------------------------
# Main status bar widget
# ---------------------------------------------------------------------------

_STATUSBAR_STYLE = """
QStatusBar {
    background: #f5f7fa;
    border-top: 1px solid #c0c8d0;
    color: #0a1929;
    font-size: 11px;
}
QProgressBar {
    border: 1px solid #b0bac5;
    background: #e0e5eb;
    border-radius: 2px;
    text-align: center;
    min-height: 8px;
    max-height: 8px;
}
QProgressBar::chunk {
    background: #2f80ed;
    border-radius: 1px;
}
"""


class GISStatusBar(QStatusBar):
    """
    Clean, minimal status bar for the Offline 3D GIS application.

    Usage::

        status_bar = GISStatusBar(parent=main_window)
        main_window.setStatusBar(status_bar)
        # Wire bridge signals:
        bridge.mouseCoordinates.connect(status_bar.on_mouse_coordinates)
        bridge.loadingProgress.connect(status_bar.on_loading_progress)
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the GIS status bar.
        
        Args:
            parent: Parent widget (typically the main window).
        """
        super().__init__(parent)
        self.setStyleSheet(_STATUSBAR_STYLE)
        self.setSizeGripEnabled(False)
        self.setFixedHeight(36)

        # ── Progress bar (no text, just blue fill) ───────────────────────
        self._progress_bar = QProgressBar(self)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedWidth(100)  # Half the previous width
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)

        # ── Progress label (2-3 word status beside the bar) ───────────────
        self._progress_label = QLabel("", self)
        self._progress_label.setFixedWidth(110)
        self._progress_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._progress_label.setStyleSheet(
            "QLabel { color: #90caf9; font-size: 11px; font-family: 'Menlo','Consolas','Monaco',monospace; }"
        )

        # ── Coordinate boxes ──────────────────────────────────────────────
        self._utm_transformers: dict[int, Transformer] = {}
        
        self._lon_box = _coord_box("Lon: —", "Longitude (WGS-84)", 140)
        self._lat_box = _coord_box("Lat: —", "Latitude (WGS-84)", 140)
        self._utm_box = _coord_box("UTM: —", "UTM coordinates", 160)
        self._elev_box = _coord_box("Elev: —", "Elevation above sea level", 120)
        self._crs_box = _coord_box("EPSG:4326", "Coordinate Reference System", 100)
        self._crs_box.setStyleSheet("""
            QFrame#coordBox {
                background: #e3f2fd;
                border: 1px solid #90caf9;
                border-radius: 3px;
                padding: 2px 4px;
            }
            QLabel {
                color: #0d47a1;
                font-size: 11px;
                font-family: 'Menlo', 'Consolas', 'Monaco', monospace;
                font-weight: 700;
                padding: 1px 3px;
                margin: 0px;
                background: transparent;
            }
        """)

        # ── Layout ────────────────────────────────────────────────────────
        container = QWidget(self)
        container.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout(container)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(8)

        # Add stretch first to push everything to the right
        row.addStretch(1)
        row.addWidget(self._progress_label)
        row.addWidget(self._progress_bar)
        row.addWidget(_make_separator())
        row.addWidget(self._lon_box)
        row.addWidget(self._lat_box)
        row.addWidget(_make_separator())
        row.addWidget(self._utm_box)
        row.addWidget(_make_separator())
        row.addWidget(self._elev_box)
        row.addWidget(_make_separator())
        row.addWidget(self._crs_box)

        self.addPermanentWidget(container, 1)

        # ── Coordinate precision ──────────────────────────────────────────
        self._coord_decimal_places = 6
        self._elev_decimal_places = 2

        # ── Progress priority tracking ────────────────────────────────────
        # Computation progress (fill volume, slope, etc.) takes priority over
        # tile-loading progress so the two don't fight each other.
        self._computation_active = False

    # ------------------------------------------------------------------
    # Slots wired to WebBridge signals
    # ------------------------------------------------------------------

    @Slot(float, float, float)
    def on_mouse_coordinates(self, lon: float, lat: float, elevation_m: float) -> None:
        """Receive live mouse coordinates from the CesiumJS bridge.
        
        Args:
            lon: Longitude in degrees.
            lat: Latitude in degrees.
            elevation_m: Elevation in meters (-9999 if no DEM available).
        """
        # Check if coordinates are valid
        if not (math.isfinite(lon) and math.isfinite(lat)):
            self.clear_coordinates()
            return

        # Longitude
        lon_str = f"{lon:.{self._coord_decimal_places}f}°"
        self._lon_box.label.setText(f"Lon: {lon_str}")

        # Latitude
        lat_str = f"{lat:.{self._coord_decimal_places}f}°"
        self._lat_box.label.setText(f"Lat: {lat_str}")

        # UTM
        utm_text = self._format_utm_coordinates(lon, lat)
        self._utm_box.label.setText(f"UTM: {utm_text}")

        # Elevation - only show when DEM data is available
        # -9999 indicates no DEM terrain is loaded
        if math.isfinite(elevation_m) and elevation_m > -9000.0:
            elev_text = f"{elevation_m:,.{self._elev_decimal_places}f} m"
            self._elev_box.label.setText(f"Elev: {elev_text}")
        else:
            # No DEM available - keep box visible but blank
            self._elev_box.label.setText("Elev: —")

    @Slot(float, float)
    def on_camera_changed(self, scale_denominator: float, heading_deg: float) -> None:
        """Receive camera scale and heading from the CesiumJS bridge.
        
        Args:
            scale_denominator: Map scale denominator (e.g., 25000 for 1:25000).
            heading_deg: Camera heading in degrees (0° = North).
        """
        # Camera info not displayed in minimal status bar
        pass

    @Slot(int, str)
    def on_loading_progress(self, percent: int, message: str) -> None:
        """Update the progress bar with loading status.
        
        Args:
            percent: Progress percentage (0-100), or -1 for indeterminate spinner.
            message: Status message describing what's loading.
        """
        is_computation = "fill volume" in (message or "").lower()

        if percent < 0:
            # -1 → indeterminate spinner (e.g. long-running computation)
            self._computation_active = True
            self._progress_bar.setRange(0, 0)
            self._progress_bar.setToolTip(str(message or "Processing…"))
            self._progress_label.setText(self._short_label(message))
            return

        percent = max(0, min(100, percent))  # Clamp to 0-100

        # Tile-loading events (percent < 100, message="Loading tiles" / "Complete")
        # must not overwrite an active computation progress update.
        if not is_computation and self._computation_active:
            return

        if is_computation:
            # Track computation lifecycle: 0 = start, 100 = done
            if percent == 0:
                self._computation_active = True
            elif percent == 100:
                self._computation_active = False

        if percent > 0 and percent < 100:
            self._progress_bar.setRange(0, 100)
            self._progress_bar.setValue(percent)
            self._progress_label.setText(self._short_label(message))
        else:
            # 0 (start) → show indeterminate so the bar is visible immediately
            # 100 (done) → reset
            if percent == 0 and is_computation:
                self._progress_bar.setRange(0, 0)  # indeterminate until first real %
                self._progress_label.setText(self._short_label(message))
            else:
                self._progress_bar.setRange(0, 100)
                self._progress_bar.setValue(0)
                self._progress_label.setText("")
        self._progress_bar.setToolTip("")

    @staticmethod
    def _short_label(message: str) -> str:
        """Return a crisp 2-3 word label from a longer message string."""
        _MAP = {
            "fill volume":   "Fill Volume…",
            "analysing":     "Analysing…",
            "computing":     "Computing…",
            "loading":       "Loading…",
            "rendering":     "Rendering…",
            "searching":     "Searching…",
            "done":          "",
            "complete":      "",
        }
        lower = (message or "").lower()
        for key, label in _MAP.items():
            if key in lower:
                return label
        # Fallback: first two words, max 18 chars
        words = (message or "").split()
        short = " ".join(words[:2])
        return short[:18] + ("…" if len(short) > 18 else "")

    @Slot(bool)
    def on_render_busy(self, busy: bool) -> None:
        """Show indeterminate progress while the renderer is active.
        
        Args:
            busy: True when the renderer is processing frames.
        """
        # Never let render-busy state overwrite an active computation progress.
        if self._computation_active:
            return
        if busy:
            self._progress_bar.setRange(0, 0)  # indeterminate spinner
        else:
            self._progress_bar.setRange(0, 100)
            self._progress_bar.setValue(0)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def set_crs(self, auth_id: str) -> None:
        """Set the CRS badge text.
        
        Args:
            auth_id: CRS authority identifier (e.g., 'EPSG:4326').
        """
        self._crs_box.label.setText(auth_id or "EPSG:4326")

    def set_coordinate_precision(self, decimal_places: int) -> None:
        """Set the number of decimal places for coordinate display.
        
        Args:
            decimal_places: Number of decimal places (1-10).
        """
        self._coord_decimal_places = max(1, min(10, decimal_places))

    def set_elevation_precision(self, decimal_places: int) -> None:
        """Set the number of decimal places for elevation display.
        
        Args:
            decimal_places: Number of decimal places (0-4).
        """
        self._elev_decimal_places = max(0, min(4, decimal_places))

    def clear_coordinates(self) -> None:
        """Reset coord display when cursor leaves the map."""
        self._lon_box.label.setText("Lon: —")
        self._lat_box.label.setText("Lat: —")
        self._utm_box.label.setText("UTM: —")
        self._elev_box.label.setText("Elev: —")

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _format_utm_coordinates(self, lon: float, lat: float) -> str:
        """Format coordinates as UTM string.
        
        Args:
            lon: Longitude in degrees.
            lat: Latitude in degrees.
            
        Returns:
            Formatted UTM coordinate string (e.g., "32N 500000 mE").
        """
        epsg = _utm_epsg_for_lon_lat(lon, lat)
        transformer = self._utm_transformers.get(epsg)
        if transformer is None:
            transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
            self._utm_transformers[epsg] = transformer

        easting, northing = transformer.transform(lon, lat)
        zone = epsg % 100
        hemisphere = "N" if lat >= 0 else "S"
        return f"{zone}{hemisphere} {easting:,.0f} mE"
