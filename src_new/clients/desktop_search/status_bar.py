"""
status_bar.py
=============
Clean, minimal status bar for the Offline 3-D GIS desktop application.

Layout:
  ┌──────────────────────────────────────────────────────────────────────────┐
    │ [Progress Bar] │ Lon: 87.231456° │ Lat: 23.710234° │ UTM: 45N 500000 mE │ EPSG:4326 │
  └──────────────────────────────────────────────────────────────────────────┘

Signals consumed (from WebBridge via the QWebChannel pipe):
    - mouseCoordinates(lon: float, lat: float)
  - cameraChanged(scale_denominator: float, heading_deg: float)
  - loadingProgress(percent: int, message: str)
"""

from __future__ import annotations

import math
import time

from pyproj import Transformer
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

# --------------------------------------------------------------------------- Helpers ---------------------------------------------------------------------------


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
            border: 1px solid #cccccc;
            border-radius: 2px;
            padding: 2px 4px;
        }
        QLabel {
            color: #222222;
            font-size: 11px;
            font-family: 'Segoe UI', sans-serif;
            font-weight: 500;
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


# --------------------------------------------------------------------------- Main status bar widget ---------------------------------------------------------------------------

_STATUSBAR_STYLE = """
QStatusBar {
    background: #f0f0f0;
    border-top: 1px solid #c0c0c0;
    color: #333333;
    font-size: 11px;
}
QStatusBar::item {
    border: none;
}
QProgressBar {
    border: 1px solid #999999;
    background: #ffffff;
    border-radius: 2px;
    text-align: center;
    min-height: 12px;
    max-height: 12px;
}
QProgressBar::chunk {
    background: #4a90e2;
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
        self._progress_bar.setFixedWidth(120)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(True)
        
        self._activity_label = QLabel("READY")
        self._activity_label.setStyleSheet("color: #555555; font-weight: bold; font-family: sans-serif; font-size: 10px; padding-left: 5px;")
        self._activity_label.setFixedWidth(110)
        self._activity_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        # ── Coordinate boxes ──────────────────────────────────────────────
        self._utm_transformers: dict[int, Transformer] = {}

        self._lon_box = _coord_box("Lon: —", "Longitude (WGS-84)", 140)
        self._lat_box = _coord_box("Lat: —", "Latitude (WGS-84)", 140)
        self._utm_box = _coord_box("UTM: —", "UTM coordinates (meters)", 180)
        self._crs_box = _coord_box("EPSG:4326", "Coordinate Reference System", 100)
        self._crs_box.setStyleSheet("""
            QFrame#coordBox {
                background: #e1f5fe;
                border: 1px solid #b3e5fc;
                border-radius: 2px;
                padding: 2px 4px;
            }
            QLabel {
                color: #0277bd;
                font-size: 11px;
                font-family: 'Segoe UI', sans-serif;
                font-weight: 600;
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
        row.addWidget(self._activity_label)
        row.addWidget(self._progress_bar)
        row.addStretch(1)
        row.addWidget(_make_separator())
        row.addWidget(self._lon_box)
        row.addWidget(self._lat_box)
        row.addWidget(_make_separator())
        row.addWidget(self._utm_box)
        row.addWidget(_make_separator())
        row.addWidget(self._crs_box)

        self.addPermanentWidget(container, 1)

        # ── Coordinate precision ──────────────────────────────────────────
        self._coord_decimal_places = 6
        self._coord_update_interval_s = 0.05
        self._last_coord_update_ts = 0.0
        # ── Progress priority tracking ────────────────────────────────────
        # Computation progress (fill volume, slope, etc.) takes priority over tile-loading progress so the two don't fight each other.
        self._computation_active = False

    # ------------------------------------------------------------------ Slots wired to WebBridge signals ------------------------------------------------------------------

    @Slot(float, float)
    def on_mouse_coordinates(self, lon: float, lat: float) -> None:
        """Receive live mouse coordinates from the CesiumJS bridge.

        Args:
            lon: Longitude in degrees.
            lat: Latitude in degrees.
        """
        # Check if coordinates are valid
        if not (math.isfinite(lon) and math.isfinite(lat)):
            self.clear_coordinates()
            return

        now = time.monotonic()
        if now - self._last_coord_update_ts < self._coord_update_interval_s:
            return
        self._last_coord_update_ts = now

        # Enhanced coordinate display with higher precision for professional use Use 8 decimal places for sub-meter accuracy
        precision = min(self._coord_decimal_places, 8)

        # Longitude with enhanced formatting
        lon_str = f"{lon:.{precision}f}°"
        self._lon_box.label.setText(f"Lon: {lon_str}")

        # Latitude with enhanced formatting
        lat_str = f"{lat:.{precision}f}°"
        self._lat_box.label.setText(f"Lat: {lat_str}")

        # UTM with zone information and meters display
        utm_text = self._format_utm_coordinates(lon, lat)
        self._utm_box.label.setText(f"UTM: {utm_text}")

        # Dynamic CRS display - show UTM zone for current location
        utm_epsg = _utm_epsg_for_lon_lat(lon, lat)
        utm_zone = int((lon + 180.0) // 6.0) + 1
        hemisphere = "N" if lat >= 0 else "S"
        self._crs_box.label.setText(f"UTM {utm_zone}{hemisphere}")
        self._crs_box.setToolTip(f"EPSG:{utm_epsg} (UTM Zone {utm_zone}{hemisphere})")

    @Slot(float, float, float)
    def on_camera_changed(self, scale_denominator: float, heading_deg: float, pitch_deg: float) -> None:
        """Receive camera scale and heading from the CesiumJS bridge.

        Args:
            scale_denominator: Map scale denominator (e.g., 25000 for 1:25000).
            heading_deg: Camera heading in degrees (0° = North).
            pitch_deg: Camera pitch in degrees.
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
        msg_lower = (message or "").lower()
        is_computation = any(kw in msg_lower for kw in ["fill volume", "computing", "analysing", "processing", "slope"])
        is_tile_load = "tile" in msg_lower

        # -1 → indeterminate spinner (e.g. long-running computation)
        if percent < 0:
            self._computation_active = True
            self._progress_bar.setRange(0, 0)
            self._progress_bar.setVisible(True)
            self._progress_bar.setToolTip(str(message or "Processing…"))
            self._activity_label.setText(self._short_label(message).upper() or "ACTIVE")
            return

        percent = max(0, min(100, percent))  # Clamp to 0-100

        # Lifecycle management: 100% always clears computation active state
        if percent == 100:
            self._computation_active = False

        # Tile-loading events must not overwrite an active computation progress UNLESS the tile event itself is a completion signal (percent=100).
        if is_tile_load and self._computation_active and percent < 100:
            return

        if is_computation:
            if percent < 100:
                self._computation_active = True
            else:
                self._computation_active = False

        if 0 < percent < 100:
            self._progress_bar.setRange(0, 100)
            self._progress_bar.setValue(percent)
            self._activity_label.setText(self._short_label(message).upper() or "LOADING")
        else:
            # Handle 0% (Start) or 100% (Complete)
            self._progress_bar.setRange(0, 100)
            if percent == 0 and (is_computation or "loading" in msg_lower):
                # Show a small hint of progress (5%) for "Active/Loading" starts
                self._progress_bar.setValue(5)
                self._activity_label.setText(self._short_label(message).upper() or "ACTIVE")
            else:
                # 100% or other -> READY
                self._progress_bar.setValue(0)
                self._activity_label.setText("READY")
        self._progress_bar.setToolTip(message or "System Ready")

    @staticmethod
    def _short_label(message: str) -> str:
        """Return a crisp 2-3 word label from a longer message string."""
        _MAP = {
            "fill volume": "Fill Volume…",
            "analysing": "Analysing…",
            "computing": "Computing…",
            "loading": "Loading…",
            "rendering": "Rendering…",
            "searching": "Searching…",
            "done": "",
            "complete": "",
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

    # ------------------------------------------------------------------ Public helpers ------------------------------------------------------------------

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

    def clear_coordinates(self) -> None:
        """Reset coord display when cursor leaves the map."""
        self._lon_box.label.setText("Lon: —")
        self._lat_box.label.setText("Lat: —")
        self._utm_box.label.setText("UTM: —")

    # ------------------------------------------------------------------ Private ------------------------------------------------------------------

    def _format_utm_coordinates(self, lon: float, lat: float) -> str:
        """Format coordinates as UTM string with meters.

        Args:
            lon: Longitude in degrees.
            lat: Latitude in degrees.

        Returns:
            Formatted UTM coordinate string with meters (e.g., "32N 500000 mE 4500000 mN").
        """
        epsg = _utm_epsg_for_lon_lat(lon, lat)
        transformer = self._utm_transformers.get(epsg)
        if transformer is None:
            transformer = Transformer.from_crs(
                "EPSG:4326", f"EPSG:{epsg}", always_xy=True
            )
            self._utm_transformers[epsg] = transformer

        easting, northing = transformer.transform(lon, lat)
        zone = epsg % 100
        hemisphere = "N" if lat >= 0 else "S"
        return f"{zone}{hemisphere} {easting:,.0f} mE {northing:,.0f} mN"
