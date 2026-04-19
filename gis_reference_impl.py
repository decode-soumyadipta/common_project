"""
GIS Desktop App — Reference Implementation
============================================
Offline-safe. No network calls anywhere in this file.
Stack: PyQt6, GDAL, rasterio, numpy, scipy, shapely, pyproj, pysolar

OFFLINE SETUP (run once on air-gapped machine):
    # Set PROJ data path so pyproj works without internet
    import os
    os.environ["PROJ_DATA"] = "/path/to/proj/data"   # bundled with pyproj wheel
    os.environ["GDAL_DATA"] = "/path/to/gdal/data"   # bundled with GDAL wheel

All classes are self-contained. Each can be used independently.
Agent instructions: read each class docstring for inputs/outputs/usage.
"""

import os
import math
import warnings
import datetime
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any

import numpy as np
from numpy.typing import NDArray

import rasterio
from rasterio.windows import from_bounds, Window
from rasterio.transform import rowcol, xy
from rasterio.features import rasterize
from rasterio.mask import mask as rio_mask
from rasterio.enums import Resampling
from rasterio.warp import reproject, calculate_default_transform

from pyproj import Geod, Transformer, CRS
from shapely.geometry import (
    LineString, Polygon, Point, MultiPolygon, mapping, shape
)
from shapely.ops import transform as shapely_transform
import shapely.affinity

from scipy.ndimage import gaussian_filter, convolve
from scipy.signal import savgol_filter

# PyQt6 imports (GUI rendering)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QRunnable, QObject, QThreadPool, QRectF
)
from PyQt6.QtGui import (
    QImage, QPainter, QColor, QPen, QBrush, QPolygonF, QFont
)
from PyQt6.QtWidgets import QWidget, QApplication

# Solar geometry — fully offline, pure Python
try:
    from pysolar.solar import get_altitude, get_azimuth
    PYSOLAR_AVAILABLE = True
except ImportError:
    PYSOLAR_AVAILABLE = False
    warnings.warn("pysolar not installed — shadow height tool disabled")

# Optional: fiona for GeoPackage I/O
try:
    import fiona
    import fiona.crs
    FIONA_AVAILABLE = True
except ImportError:
    FIONA_AVAILABLE = False
    warnings.warn("fiona not installed — GeoPackage export disabled")


# ============================================================
# SHARED UTILITIES
# ============================================================

def get_dem_value_at_point(dem_path: str, easting: float, northing: float) -> float:
    """
    Sample a single elevation value from a COG DEM at (easting, northing)
    in the DEM's native projected CRS. Returns float metres.
    Uses bilinear interpolation.
    """
    with rasterio.open(dem_path) as src:
        # Convert projected coords to pixel row/col
        row, col = rowcol(src.transform, easting, northing)
        # Read a 3x3 window for bilinear interp
        row = int(row)
        col = int(col)
        win = Window(col - 1, row - 1, 3, 3)
        try:
            data = src.read(1, window=win).astype(np.float64)
            nodata = src.nodata
            if nodata is not None:
                data = np.where(data == nodata, np.nan, data)
            # Bilinear interp at centre pixel (subpixel coords)
            # For exact pixel: just return data[1, 1]
            return float(data[1, 1])
        except Exception:
            return float("nan")


def read_dem_window(
    dem_path: str,
    bounds: Tuple[float, float, float, float],  # (minx, miny, maxx, maxy) projected
    smooth_sigma: float = 0.0,
) -> Tuple[NDArray[np.float64], "rasterio.transform.Affine", float]:
    """
    Read DEM pixels within a bounding box.
    Returns (array_float64, transform, resolution_metres).
    Optionally applies Gaussian smoothing (for slope/aspect only — never for raw export).
    """
    with rasterio.open(dem_path) as src:
        win = from_bounds(*bounds, transform=src.transform)
        data = src.read(1, window=win, resampling=Resampling.bilinear).astype(np.float64)
        nodata = src.nodata
        if nodata is not None:
            data = np.where(data == nodata, np.nan, data)
        transform = src.window_transform(win)
        res = src.res[0]  # assume square pixels

    if smooth_sigma > 0:
        # Replace NaN with mean before smoothing, restore after
        nan_mask = np.isnan(data)
        data_filled = np.where(nan_mask, np.nanmean(data), data)
        data_smooth = gaussian_filter(data_filled, sigma=smooth_sigma)
        data = np.where(nan_mask, np.nan, data_smooth)

    return data, transform, res


def horn_gradient(dem: NDArray[np.float64], res: float):
    """
    Horn's method 3x3 partial derivatives. Returns (dz_dx, dz_dy) in m/m.
    Handles NaN by filling with local mean before convolution.
    """
    # Fill NaN for convolution
    nan_mask = np.isnan(dem)
    fill = np.where(nan_mask, np.nanmean(dem), dem)

    # Horn kernels
    kx = np.array([[-1, 0, 1],
                   [-2, 0, 2],
                   [-1, 0, 1]], dtype=np.float64) / (8.0 * res)
    ky = np.array([[1, 2, 1],
                   [0, 0, 0],
                   [-1, -2, -1]], dtype=np.float64) / (8.0 * res)

    dz_dx = convolve(fill, kx, mode='nearest')
    dz_dy = convolve(fill, ky, mode='nearest')

    # Re-apply NaN mask
    dz_dx[nan_mask] = np.nan
    dz_dy[nan_mask] = np.nan
    return dz_dx, dz_dy


def vincenty_distance(
    lon1: float, lat1: float, lon2: float, lat2: float
) -> Tuple[float, float, float]:
    """
    Vincenty inverse geodetic calculation on WGS84.
    Returns (distance_m, azimuth_fwd_deg, azimuth_bwd_deg).
    Never use Haversine for professional measurement — sphere assumption is ~0.3% wrong.
    """
    geod = Geod(ellps="WGS84")
    az_fwd, az_bwd, dist = geod.inv(lon1, lat1, lon2, lat2)
    az_fwd = az_fwd % 360.0
    az_bwd = az_bwd % 360.0
    return dist, az_fwd, az_bwd


def projected_to_wgs84(easting: float, northing: float, epsg: int) -> Tuple[float, float]:
    """Convert projected coords (metres) to WGS84 lon/lat."""
    transformer = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(easting, northing)
    return lon, lat


def wgs84_to_projected(lon: float, lat: float, epsg: int) -> Tuple[float, float]:
    """Convert WGS84 lon/lat to projected coords (metres)."""
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    e, n = transformer.transform(lon, lat)
    return e, n


# ============================================================
# V1 — MULTI-LAYER COMPOSITOR
# ============================================================

class HistogramStretch:
    """
    Per-band 2%–98% cumulative histogram stretch.
    Industry standard for remote sensing display.

    Usage:
        stretch = HistogramStretch.from_overview(rgb_cog_path)
        display_img = stretch.apply(raw_tile_array)  # shape (H, W, 3), uint8 output
    """

    def __init__(self, p_low: NDArray, p_high: NDArray):
        # p_low / p_high shape: (n_bands,)
        self.p_low = np.array(p_low, dtype=np.float64)
        self.p_high = np.array(p_high, dtype=np.float64)

    @classmethod
    def from_overview(cls, raster_path: str, percentile_low: float = 2.0,
                      percentile_high: float = 98.0,
                      overview_level: int = 4) -> "HistogramStretch":
        """
        Compute stretch parameters from a COG overview band (fast — not full raster).
        overview_level=4 means 1/16 resolution sample.
        """
        with rasterio.open(raster_path) as src:
            n_bands = src.count
            p_low = np.zeros(n_bands)
            p_high = np.zeros(n_bands)
            for b in range(1, n_bands + 1):
                # Read lowest available overview
                data = src.read(b, out_shape=(
                    1,
                    max(1, src.height // (2 ** overview_level)),
                    max(1, src.width // (2 ** overview_level)),
                ), resampling=Resampling.nearest).astype(np.float64).ravel()
                nodata = src.nodata
                if nodata is not None:
                    data = data[data != nodata]
                data = data[~np.isnan(data)]
                p_low[b - 1] = np.percentile(data, percentile_low)
                p_high[b - 1] = np.percentile(data, percentile_high)
        return cls(p_low, p_high)

    def apply(self, tile: NDArray) -> NDArray[np.uint8]:
        """
        Apply stretch to tile array.
        tile shape: (n_bands, H, W) — rasterio band-first format.
        Returns uint8 array shape (H, W, n_bands) for Qt display.
        """
        n_bands, H, W = tile.shape
        out = np.zeros((H, W, n_bands), dtype=np.float64)
        for b in range(n_bands):
            lo = self.p_low[b]
            hi = self.p_high[b]
            if hi == lo:
                out[:, :, b] = 128.0
            else:
                out[:, :, b] = (tile[b].astype(np.float64) - lo) / (hi - lo) * 255.0
        return np.clip(out, 0, 255).astype(np.uint8)

    def apply_gamma(self, img_uint8: NDArray[np.uint8], gamma: float = 1.0) -> NDArray[np.uint8]:
        """
        Apply gamma correction after stretch.
        gamma > 1.0 → brighter midtones, gamma < 1.0 → darker midtones.
        Formula: out = 255 × (in/255)^(1/gamma)
        """
        if gamma == 1.0:
            return img_uint8
        lut = (255.0 * (np.arange(256) / 255.0) ** (1.0 / gamma)).astype(np.uint8)
        return lut[img_uint8]


def compose_layers_cpu(
    rgb: NDArray[np.uint8],    # (H, W, 3) uint8
    overlay: NDArray[np.uint8],  # (H, W, 3) uint8
    overlay_alpha: float = 0.5,
) -> NDArray[np.uint8]:
    """
    Porter-Duff 'over' alpha compositing — CPU path.
    For GPU path: use GLSL fragment shader with glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA).
    overlay_alpha: 0.0 = fully transparent overlay, 1.0 = fully opaque overlay.
    """
    a = np.clip(overlay_alpha, 0.0, 1.0)
    blended = (1.0 - a) * rgb.astype(np.float32) + a * overlay.astype(np.float32)
    return np.clip(blended, 0, 255).astype(np.uint8)


def ndarray_to_qimage(arr: NDArray[np.uint8]) -> QImage:
    """Convert (H, W, 3) uint8 numpy array to QImage (RGB888)."""
    H, W, C = arr.shape
    assert C == 3, "Expected 3-channel RGB"
    # QImage requires contiguous memory in RGB format
    arr_c = np.ascontiguousarray(arr)
    return QImage(arr_c.data, W, H, W * 3, QImage.Format.Format_RGB888)


# ============================================================
# V2 — ANALYTICAL HILLSHADE
# ============================================================

class Hillshade:
    """
    Horn's method hillshade with multi-directional USGS option.
    Reveals micro-topography at 1–2 cm DEM resolution.

    Usage (single direction):
        hs = Hillshade.compute(dem_array, res_metres, azimuth=225.0, elevation=45.0)
        # hs is uint8 (H, W) greyscale

    Usage (multi-directional, USGS method — recommended for intelligence):
        hs = Hillshade.compute_multidirectional(dem_array, res_metres)
    """

    @staticmethod
    def compute(
        dem: NDArray[np.float64],
        res: float,
        azimuth_deg: float = 315.0,    # 315 = NW (cartographic convention)
        elevation_deg: float = 45.0,
    ) -> NDArray[np.uint8]:
        """
        Single-illumination hillshade. Formula: Lambert reflectance.
        azimuth_deg: sun azimuth, 0=North, clockwise
        elevation_deg: sun elevation above horizon
        """
        dz_dx, dz_dy = horn_gradient(dem, res)

        slope = np.arctan(np.sqrt(dz_dx ** 2 + dz_dy ** 2))
        aspect = np.arctan2(dz_dy, -dz_dx)

        zenith = math.radians(90.0 - elevation_deg)
        azimuth = math.radians(azimuth_deg)

        hs = (
            np.cos(zenith) * np.cos(slope)
            + np.sin(zenith) * np.sin(slope) * np.cos(azimuth - aspect)
        )
        hs = np.clip(hs * 255.0, 0, 255).astype(np.uint8)
        return hs

    @staticmethod
    def compute_multidirectional(
        dem: NDArray[np.float64], res: float
    ) -> NDArray[np.uint8]:
        """
        USGS multi-directional hillshade (Mark 1992 / Imhof weighting).
        Averages 8 azimuths at 45° intervals to eliminate directional bias.
        USGS weighting: primary weight on 225° (SW), equal secondary on 270° and 315°.
        Produces the best micro-terrain rendering for surveillance imagery.
        """
        azimuths = [0, 45, 90, 135, 180, 225, 270, 315]
        all_hs = []
        for az in azimuths:
            hs = Hillshade.compute(dem, res, azimuth_deg=float(az), elevation_deg=45.0)
            all_hs.append(hs.astype(np.float32))

        # USGS Imbrie weighting
        # Primary: 225° gets 0.5, secondary: 270° and 315° get 0.25 each
        # Remaining 5 directions split to 0.0 (USGS uses only 3 dominant azimuths)
        # Reference: USGS Open-File Report 92-422
        weights = {0: 0.0, 45: 0.0, 90: 0.0, 135: 0.0,
                   180: 0.0, 225: 0.5, 270: 0.25, 315: 0.25}
        result = np.zeros_like(all_hs[0])
        for i, az in enumerate(azimuths):
            result += weights[az] * all_hs[i]

        return np.clip(result, 0, 255).astype(np.uint8)


# ============================================================
# V3 — COLOUR RELIEF (DEM RAMP RENDERER)
# ============================================================

class ColourRelief:
    """
    Maps DEM float64 values to RGB using piecewise linear colour ramps.
    Supports absolute mode (colours tied to real elevations) and relative mode
    (colours stretched to tile min/max — enhances local micro-relief).

    Usage:
        ramp = ColourRelief.viridis_ramp()                   # preset
        rgb_img = ColourRelief.render(dem_array, ramp, mode='absolute')
    """

    @dataclass
    class ControlPoint:
        elevation: float   # metres (absolute mode) OR 0.0–1.0 fraction (relative mode)
        r: int
        g: int
        b: int

    @staticmethod
    def viridis_ramp() -> List["ColourRelief.ControlPoint"]:
        """Perceptually uniform, colour-blind safe. Use for quantitative analysis."""
        CP = ColourRelief.ControlPoint
        return [
            CP(0.0,   68,  1, 84),
            CP(0.2,   59, 82, 139),
            CP(0.4,   33, 145, 140),
            CP(0.6,   94, 201, 98),
            CP(0.8,  253, 231, 37),
            CP(1.0,  253, 231, 37),
        ]

    @staticmethod
    def etopo_ramp() -> List["ColourRelief.ControlPoint"]:
        """Classic terrain ramp: deep blue→green→brown→white."""
        CP = ColourRelief.ControlPoint
        return [
            CP(0.0,   0,   0, 200),
            CP(0.15,  0, 128, 255),
            CP(0.3,  34, 139,  34),
            CP(0.5, 139, 115,  85),
            CP(0.75, 180, 120,  60),
            CP(1.0, 255, 255, 255),
        ]

    @staticmethod
    def render(
        dem: NDArray[np.float64],
        ramp: List["ColourRelief.ControlPoint"],
        mode: str = "absolute",       # 'absolute' or 'relative'
        z_min: Optional[float] = None,  # for absolute mode
        z_max: Optional[float] = None,  # for absolute mode
    ) -> NDArray[np.uint8]:
        """
        Render DEM as RGB colour image.
        mode='absolute': ramp control point elevations are in metres.
            z_min/z_max define the ramp extents. If None, use ramp min/max.
        mode='relative': ramp control points are 0.0–1.0 fractions,
            stretched to tile min/max. Good for micro-relief regardless of absolute height.
        Returns uint8 (H, W, 3).
        """
        if mode == "relative":
            lo = np.nanmin(dem)
            hi = np.nanmax(dem)
        else:
            lo = z_min if z_min is not None else ramp[0].elevation
            hi = z_max if z_max is not None else ramp[-1].elevation

        # Normalise DEM to 0–1
        denom = hi - lo if hi != lo else 1.0
        norm = np.clip((dem - lo) / denom, 0.0, 1.0)

        # Sort control points by elevation (normalised)
        if mode == "absolute":
            pts = [(cp.elevation, cp.r, cp.g, cp.b) for cp in ramp]
            # Normalise control point elevations too
            pts = [((e - lo) / denom, r, g, b) for e, r, g, b in pts]
        else:
            pts = [(cp.elevation, cp.r, cp.g, cp.b) for cp in ramp]
        pts.sort(key=lambda x: x[0])

        H, W = norm.shape
        rgb = np.zeros((H, W, 3), dtype=np.float32)

        flat = norm.ravel()
        r_out = np.zeros(len(flat))
        g_out = np.zeros(len(flat))
        b_out = np.zeros(len(flat))

        for i in range(len(pts) - 1):
            e0, r0, g0, b0 = pts[i]
            e1, r1, g1, b1 = pts[i + 1]
            in_range = (flat >= e0) & (flat <= e1)
            if not np.any(in_range):
                continue
            t = (flat[in_range] - e0) / (e1 - e0 + 1e-10)
            r_out[in_range] = r0 + t * (r1 - r0)
            g_out[in_range] = g0 + t * (g1 - g0)
            b_out[in_range] = b0 + t * (b1 - b0)

        rgb = np.stack([r_out, g_out, b_out], axis=1).reshape(H, W, 3)
        return np.clip(rgb, 0, 255).astype(np.uint8)


# ============================================================
# V4 — SPLIT-SCREEN SWIPE COMPARATOR (Qt widget logic)
# ============================================================

class SwipeComparatorWidget(QWidget):
    """
    Synchronized split-screen swipe comparator.
    Left panel shows layer_a, right panel shows layer_b.
    Both are georeferenced QImages rendered from identical viewport extents.

    Usage:
        widget = SwipeComparatorWidget(parent)
        widget.set_layers(qimage_left, qimage_right)
        widget.set_swipe_position(0.5)  # 50% from left
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._img_left: Optional[QImage] = None
        self._img_right: Optional[QImage] = None
        self._swipe_pos: float = 0.5    # 0.0–1.0 fraction of widget width
        self._dragging: bool = False
        self.setMouseTracking(True)

    def set_layers(self, left: QImage, right: QImage):
        """Both images must be the same pixel dimensions (same viewport extent)."""
        assert left.size() == right.size(), (
            "Both layers must cover identical pixel extent. "
            "Reproject/resample to match if CRS or resolution differs."
        )
        self._img_left = left
        self._img_right = right
        self.update()

    def set_swipe_position(self, fraction: float):
        """fraction: 0.0 (full right) to 1.0 (full left)."""
        self._swipe_pos = max(0.01, min(0.99, fraction))
        self.update()

    def paintEvent(self, event):
        if self._img_left is None or self._img_right is None:
            return
        painter = QPainter(self)
        W = self.width()
        H = self.height()
        split_x = int(W * self._swipe_pos)

        # Draw left panel (clipped to left of split_x)
        painter.setClipRect(0, 0, split_x, H)
        painter.drawImage(0, 0, self._img_left.scaled(
            W, H, Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation))

        # Draw right panel (clipped to right of split_x)
        painter.setClipRect(split_x, 0, W - split_x, H)
        painter.drawImage(0, 0, self._img_right.scaled(
            W, H, Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation))

        # Draw swipe handle line
        painter.setClipping(False)
        pen = QPen(QColor(255, 255, 0), 2, Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.drawLine(split_x, 0, split_x, H)

        # Handle circle
        painter.setBrush(QBrush(QColor(255, 255, 0, 180)))
        painter.drawEllipse(split_x - 12, H // 2 - 12, 24, 24)
        painter.end()

    def mousePressEvent(self, event):
        split_x = int(self.width() * self._swipe_pos)
        if abs(event.position().x() - split_x) < 20:
            self._dragging = True

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.set_swipe_position(event.position().x() / self.width())

    def mouseReleaseEvent(self, event):
        self._dragging = False


# ============================================================
# M1 — GEODETIC DISTANCE & AZIMUTH
# ============================================================

@dataclass
class DistanceResult:
    distance_m: float
    distance_3d_m: Optional[float]  # None if no DEM
    azimuth_fwd_deg: float
    azimuth_bwd_deg: float
    dz_m: Optional[float]           # elevation difference
    cardinal: str                   # e.g. "NE", "SSW"

    def summary(self) -> str:
        lines = [
            f"Distance (2D):   {self.distance_m:.3f} m",
            f"Azimuth (fwd):   {self.azimuth_fwd_deg:.1f}° ({self.cardinal})",
            f"Azimuth (back):  {self.azimuth_bwd_deg:.1f}°",
        ]
        if self.dz_m is not None:
            lines.append(f"ΔZ (elevation):  {self.dz_m:+.3f} m")
        if self.distance_3d_m is not None:
            lines.append(f"Distance (3D):   {self.distance_3d_m:.3f} m")
        return "\n".join(lines)


def _azimuth_to_cardinal(az: float) -> str:
    """Convert azimuth degrees to 16-point compass label."""
    directions = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"
    ]
    idx = int((az % 360.0) / 22.5 + 0.5) % 16
    return directions[idx]


def measure_distance(
    lon1: float, lat1: float,
    lon2: float, lat2: float,
    dem_path: Optional[str] = None,
    projected_epsg: Optional[int] = None,  # needed to sample DEM
) -> DistanceResult:
    """
    Vincenty geodetic distance + azimuth between two WGS84 points.
    If dem_path provided: also returns 3D slope-corrected distance.

    Inputs:
        lon1, lat1: first point WGS84 decimal degrees
        lon2, lat2: second point WGS84 decimal degrees
        dem_path: COG DEM file path (optional)
        projected_epsg: EPSG code of DEM's projected CRS (e.g. 32643 for UTM43N)

    Output: DistanceResult dataclass (see summary() for formatted string)
    """
    dist, az_fwd, az_bwd = vincenty_distance(lon1, lat1, lon2, lat2)

    dz = None
    dist_3d = None

    if dem_path and projected_epsg:
        e1, n1 = wgs84_to_projected(lon1, lat1, projected_epsg)
        e2, n2 = wgs84_to_projected(lon2, lat2, projected_epsg)
        z1 = get_dem_value_at_point(dem_path, e1, n1)
        z2 = get_dem_value_at_point(dem_path, e2, n2)
        if not (math.isnan(z1) or math.isnan(z2)):
            dz = z2 - z1
            dist_3d = math.sqrt(dist ** 2 + dz ** 2)

    return DistanceResult(
        distance_m=dist,
        distance_3d_m=dist_3d,
        azimuth_fwd_deg=az_fwd,
        azimuth_bwd_deg=az_bwd,
        dz_m=dz,
        cardinal=_azimuth_to_cardinal(az_fwd),
    )


# ============================================================
# M2 — POLYGON AREA & PERIMETER (PLANIMETRIC + SURFACE AREA)
# ============================================================

@dataclass
class AreaResult:
    planimetric_area_m2: float
    surface_area_m2: Optional[float]   # None if no DEM
    perimeter_m: float
    compactness_index: float           # 4πA/P² — 1.0 = circle
    void_fraction: Optional[float]     # fraction of DEM pixels that were NaN

    def summary(self) -> str:
        lines = [
            f"Planimetric area: {self.planimetric_area_m2:.2f} m²  "
            f"({self.planimetric_area_m2 / 10000:.4f} ha)",
            f"Perimeter:        {self.perimeter_m:.2f} m",
            f"Compactness:      {self.compactness_index:.4f} (1.0=circle)",
        ]
        if self.surface_area_m2 is not None:
            diff = self.surface_area_m2 - self.planimetric_area_m2
            pct = diff / self.planimetric_area_m2 * 100
            lines.append(
                f"Surface area:     {self.surface_area_m2:.2f} m²  "
                f"(+{pct:.2f}% terrain correction)"
            )
        if self.void_fraction is not None and self.void_fraction > 0.01:
            lines.append(
                f"WARNING: {self.void_fraction*100:.1f}% of DEM pixels inside polygon "
                f"are void (NoData). Surface area is underestimated."
            )
        return "\n".join(lines)


def measure_polygon_area(
    vertices_projected: List[Tuple[float, float]],  # [(easting, northing), ...]
    projected_epsg: int,
    dem_path: Optional[str] = None,
) -> AreaResult:
    """
    Compute planimetric area (Shoelace via Shapely), perimeter (Vincenty),
    and true surface area integrating DEM slope (secant correction method).

    Surface area formula:
        For each DEM pixel inside polygon:
            local_slope = arctan(sqrt(dz_dx² + dz_dy²))
            pixel_surface = res² / cos(local_slope)   [secant correction]
        A_surface = Σ pixel_surface

    This is the same formula used in ESRI Surface Volume and GRASS r.surf.area.
    """
    poly = Polygon(vertices_projected)
    if not poly.is_valid:
        poly = poly.buffer(0)  # auto-repair
    plan_area = poly.area    # m² in projected CRS (Shoelace, exact)

    # Perimeter: sum of Vincenty distances between consecutive vertices
    transformer_fwd = Transformer.from_crs(
        f"EPSG:{projected_epsg}", "EPSG:4326", always_xy=True
    )
    verts = list(poly.exterior.coords)
    perimeter = 0.0
    for i in range(len(verts) - 1):
        lon1, lat1 = transformer_fwd.transform(verts[i][0], verts[i][1])
        lon2, lat2 = transformer_fwd.transform(verts[i + 1][0], verts[i + 1][1])
        d, _, _ = vincenty_distance(lon1, lat1, lon2, lat2)
        perimeter += d

    compactness = (4.0 * math.pi * plan_area) / (perimeter ** 2) if perimeter > 0 else 0.0

    surface_area = None
    void_fraction = None

    if dem_path:
        bounds = poly.bounds  # (minx, miny, maxx, maxy)
        dem, transform, res = read_dem_window(dem_path, bounds, smooth_sigma=0.0)

        # Rasterize polygon to pixel mask
        poly_geom = [mapping(poly)]
        mask_arr = rasterize(
            poly_geom,
            out_shape=dem.shape,
            transform=transform,
            fill=0,
            default_value=1,
            dtype=np.uint8,
            all_touched=False,
        )

        inside = mask_arr == 1
        total_inside = np.sum(inside)
        nan_inside = np.sum(np.isnan(dem) & inside)
        void_fraction = float(nan_inside) / float(total_inside) if total_inside > 0 else 0.0

        # Compute slope for surface area
        dz_dx, dz_dy = horn_gradient(dem, res)
        slope = np.arctan(np.sqrt(dz_dx ** 2 + dz_dy ** 2))  # radians
        cos_slope = np.cos(slope)
        cos_slope = np.where(cos_slope < 1e-6, 1e-6, cos_slope)  # avoid div/0

        pixel_surface = (res ** 2) / cos_slope
        valid = inside & ~np.isnan(dem)
        surface_area = float(np.sum(pixel_surface[valid]))

    return AreaResult(
        planimetric_area_m2=plan_area,
        surface_area_m2=surface_area,
        perimeter_m=perimeter,
        compactness_index=compactness,
        void_fraction=void_fraction,
    )


# ============================================================
# M3 — ELEVATION PROFILE
# ============================================================

@dataclass
class ProfileResult:
    distances_m: NDArray[np.float64]   # cumulative distance along profile
    elevations_m: NDArray[np.float64]  # elevation at each sample
    eastings: NDArray[np.float64]      # projected easting at each sample
    northings: NDArray[np.float64]     # projected northing at each sample
    min_elev: float
    max_elev: float
    mean_elev: float
    total_ascent_m: float              # sum of positive Δz
    total_descent_m: float             # sum of negative Δz
    max_slope_deg: float
    max_slope_pct: float
    profile_length_3d_m: float

    def to_csv(self) -> str:
        """Export as CSV string."""
        lines = ["distance_m,easting_m,northing_m,elevation_m"]
        for i in range(len(self.distances_m)):
            lines.append(
                f"{self.distances_m[i]:.3f},"
                f"{self.eastings[i]:.3f},"
                f"{self.northings[i]:.3f},"
                f"{self.elevations_m[i]:.4f}"
            )
        return "\n".join(lines)

    def summary(self) -> str:
        return (
            f"Profile length (2D): {self.distances_m[-1]:.2f} m\n"
            f"Profile length (3D): {self.profile_length_3d_m:.2f} m\n"
            f"Min elevation: {self.min_elev:.3f} m\n"
            f"Max elevation: {self.max_elev:.3f} m\n"
            f"Mean elevation: {self.mean_elev:.3f} m\n"
            f"Total ascent: +{self.total_ascent_m:.3f} m\n"
            f"Total descent: -{self.total_descent_m:.3f} m\n"
            f"Max slope: {self.max_slope_deg:.2f}° / {self.max_slope_pct:.1f}%"
        )


def compute_elevation_profile(
    vertices_projected: List[Tuple[float, float]],  # polyline vertices (easting, northing)
    dem_path: str,
    sample_interval_m: Optional[float] = None,   # None = use native DEM resolution
    smoothing_window: Optional[int] = None,      # Savitzky-Golay window (odd integer, e.g. 11)
) -> ProfileResult:
    """
    Sample DEM elevations along a polyline at regular intervals.
    Uses bilinear resampling (accurate to sub-pixel level).

    Savitzky-Golay smoothing: order=2, window=smoothing_window.
    Apply ONLY for display — raw elevations always preserved in output.
    """
    line = LineString(vertices_projected)

    with rasterio.open(dem_path) as src:
        native_res = src.res[0]
        nodata = src.nodata

    interval = sample_interval_m if sample_interval_m else native_res
    total_len = line.length
    n_samples = max(2, int(total_len / interval) + 1)

    sample_dists = np.linspace(0, total_len, n_samples)
    sample_pts = [line.interpolate(d) for d in sample_dists]
    eastings = np.array([p.x for p in sample_pts])
    northings = np.array([p.y for p in sample_pts])

    with rasterio.open(dem_path) as src:
        coords = list(zip(eastings, northings))
        raw_elevs = np.array(
            [v[0] for v in src.sample(coords, resampling=Resampling.bilinear)],
            dtype=np.float64,
        )
        if nodata is not None:
            raw_elevs[raw_elevs == nodata] = np.nan

    elevations = raw_elevs.copy()

    if smoothing_window and smoothing_window >= 5:
        # Savitzky-Golay: polynomial order 2
        window = smoothing_window if smoothing_window % 2 == 1 else smoothing_window + 1
        valid_mask = ~np.isnan(elevations)
        if np.sum(valid_mask) > window:
            elevations_filled = np.where(np.isnan(elevations), np.nanmean(elevations), elevations)
            elevations = savgol_filter(elevations_filled, window_length=window, polyorder=2)
            elevations[~valid_mask] = np.nan

    # Derived statistics
    valid = elevations[~np.isnan(elevations)]
    dz = np.diff(elevations)
    dd = np.diff(sample_dists)

    ascent = float(np.nansum(dz[dz > 0]))
    descent = float(np.nansum(-dz[dz < 0]))

    slopes_deg = np.degrees(np.arctan(np.abs(dz) / dd))
    slopes_pct = np.abs(dz) / dd * 100.0
    max_slope_deg = float(np.nanmax(slopes_deg)) if len(slopes_deg) > 0 else 0.0
    max_slope_pct = float(np.nanmax(slopes_pct)) if len(slopes_pct) > 0 else 0.0

    # 3D length
    length_3d = float(np.nansum(np.sqrt(dd ** 2 + dz ** 2)))

    return ProfileResult(
        distances_m=sample_dists,
        elevations_m=elevations,
        eastings=eastings,
        northings=northings,
        min_elev=float(np.nanmin(valid)) if len(valid) else 0.0,
        max_elev=float(np.nanmax(valid)) if len(valid) else 0.0,
        mean_elev=float(np.nanmean(valid)) if len(valid) else 0.0,
        total_ascent_m=ascent,
        total_descent_m=descent,
        max_slope_deg=max_slope_deg,
        max_slope_pct=max_slope_pct,
        profile_length_3d_m=length_3d,
    )


# ============================================================
# M4 — VOLUME COMPUTATION (CUT / FILL)
# ============================================================

@dataclass
class VolumeResult:
    cut_volume_m3: float    # material above reference
    fill_volume_m3: float   # material below reference
    net_volume_m3: float    # cut − fill (positive = net above ref)
    reference_elevation_m: float
    void_fraction: float
    pixel_area_m2: float    # res² — for reporting
    n_pixels_computed: int

    def summary(self) -> str:
        lines = [
            f"Reference elevation: {self.reference_elevation_m:.4f} m",
            f"Cut volume:   +{self.cut_volume_m3:.3f} m³",
            f"Fill volume:  -{self.fill_volume_m3:.3f} m³",
            f"Net volume:   {self.net_volume_m3:+.3f} m³",
            f"Pixels used:  {self.n_pixels_computed} @ {self.pixel_area_m2:.6f} m²/pixel",
        ]
        if self.void_fraction > 0.01:
            lines.append(
                f"WARNING: {self.void_fraction*100:.1f}% void pixels inside AOI — "
                f"volume result is UNDERESTIMATED. Inspect DEM for gaps."
            )
        return "\n".join(lines)


def compute_volume(
    polygon_projected: Polygon,
    dem_path: str,
    reference_mode: str = "flat",      # 'flat' or 'best_fit_plane'
    reference_elevation: Optional[float] = None,  # used if mode='flat' and value given
) -> VolumeResult:
    """
    Prismatoid summation of volume above/below a reference surface.

    reference_mode='flat':
        Uses reference_elevation (metres). If None, uses polygon boundary pixel mean.

    reference_mode='best_fit_plane':
        Fits a least-squares plane to the DEM pixels on the polygon BOUNDARY ring
        (±2 pixels). This is the standard method for stockpile volume — removes
        the effect of underlying ground slope on the volume result.

    Formula per pixel:
        ΔZ = DEM_pixel − Z_reference_at_pixel
        if ΔZ > 0: cut_volume += ΔZ × res²
        if ΔZ < 0: fill_volume += |ΔZ| × res²
    """
    bounds = polygon_projected.bounds
    dem, transform, res = read_dem_window(dem_path, bounds, smooth_sigma=0.0)

    # Rasterize polygon
    mask = rasterize(
        [mapping(polygon_projected)],
        out_shape=dem.shape,
        transform=transform,
        fill=0, default_value=1,
        dtype=np.uint8, all_touched=False,
    )
    inside = mask == 1
    total_inside = int(np.sum(inside))
    nan_inside = int(np.sum(np.isnan(dem) & inside))
    void_fraction = nan_inside / total_inside if total_inside > 0 else 0.0

    valid = inside & ~np.isnan(dem)
    z_vals = dem[valid]

    if reference_mode == "best_fit_plane":
        # Rasterize boundary ring (dilated polygon minus eroded polygon)
        # Approximate with: rasterize exterior ring ±2 pixels
        exterior_poly = Polygon(polygon_projected.exterior.coords).buffer(res * 2)
        interior_poly = Polygon(polygon_projected.exterior.coords).buffer(-res * 2)
        boundary_mask_outer = rasterize(
            [mapping(exterior_poly)],
            out_shape=dem.shape, transform=transform,
            fill=0, default_value=1, dtype=np.uint8, all_touched=False,
        )
        if interior_poly.is_valid and not interior_poly.is_empty:
            boundary_mask_inner = rasterize(
                [mapping(interior_poly)],
                out_shape=dem.shape, transform=transform,
                fill=0, default_value=1, dtype=np.uint8, all_touched=False,
            )
        else:
            boundary_mask_inner = np.zeros_like(boundary_mask_outer)

        boundary = (boundary_mask_outer == 1) & (boundary_mask_inner == 0) & ~np.isnan(dem)
        if np.sum(boundary) >= 3:
            # Build coordinate arrays for least squares
            rows, cols = np.where(boundary)
            east = cols * res
            north = rows * res
            z_bnd = dem[boundary]
            A = np.column_stack([east, north, np.ones(len(east))])
            coeffs, _, _, _ = np.linalg.lstsq(A, z_bnd, rcond=None)
            # a*E + b*N + c = Z_ref(pixel)
            all_rows, all_cols = np.where(valid)
            east_all = all_cols * res
            north_all = all_rows * res
            z_ref_vals = coeffs[0] * east_all + coeffs[1] * north_all + coeffs[2]
            dz = z_vals - z_ref_vals
            ref_elev_report = float(coeffs[2])  # Z at origin
        else:
            # Fallback to flat at mean
            ref_elev = float(np.nanmean(dem[boundary])) if np.sum(boundary) > 0 else float(np.nanmean(z_vals))
            dz = z_vals - ref_elev
            ref_elev_report = ref_elev
    else:
        # Flat reference
        if reference_elevation is not None:
            ref_elev = reference_elevation
        else:
            # Default: mean of boundary pixels
            ref_elev = float(np.nanmean(z_vals))
        dz = z_vals - ref_elev
        ref_elev_report = ref_elev

    pixel_area = res ** 2
    cut_vol = float(np.sum(dz[dz > 0]) * pixel_area)
    fill_vol = float(np.sum(-dz[dz < 0]) * pixel_area)
    net_vol = cut_vol - fill_vol

    return VolumeResult(
        cut_volume_m3=cut_vol,
        fill_volume_m3=fill_vol,
        net_volume_m3=net_vol,
        reference_elevation_m=ref_elev_report,
        void_fraction=void_fraction,
        pixel_area_m2=pixel_area,
        n_pixels_computed=int(np.sum(valid)),
    )


# ============================================================
# M5 — LINE-OF-SIGHT (VIEWSHED)
# ============================================================

@dataclass
class ViewshedResult:
    visibility_array: NDArray[np.bool_]  # True = visible, same shape as DEM window
    transform: Any                        # rasterio affine transform for overlay rendering
    observer_easting: float
    observer_northing: float
    visible_area_m2: float
    total_area_m2: float
    visible_fraction: float
    max_visible_distance_m: float

    def summary(self) -> str:
        return (
            f"Visible area:    {self.visible_area_m2:.1f} m²\n"
            f"Total area:      {self.total_area_m2:.1f} m²\n"
            f"Visible fraction: {self.visible_fraction*100:.1f}%\n"
            f"Max visible dist: {self.max_visible_distance_m:.1f} m"
        )


def compute_viewshed(
    observer_easting: float,
    observer_northing: float,
    dem_path: str,
    observer_height_m: float = 1.8,
    target_height_m: float = 0.0,
    max_radius_m: float = 500.0,
    apply_refraction: bool = True,      # atmospheric refraction correction
    refraction_k: float = 0.13,         # standard atmospheric refraction coefficient
) -> ViewshedResult:
    """
    Binary viewshed using radial ray-casting from observer.
    For each target pixel, casts a ray and checks for DEM obstructions.

    This is O(N²) per observer — practical for radii up to ~500 m at 1–2 cm resolution
    (that's 50,000 pixels radius — use chunked processing for larger radii).
    For production scale: call GRASS r.viewshed via subprocess.

    Refraction correction (Wang et al.):
        Z_corrected(P) = DEM(P) − k × d² / (2 × R_earth)
        where k=0.13, R_earth=6,371,000 m, d = distance from observer to P.
    Applied to every intermediate point along the ray.
    """
    R_earth = 6_371_000.0

    bounds = (
        observer_easting - max_radius_m,
        observer_northing - max_radius_m,
        observer_easting + max_radius_m,
        observer_northing + max_radius_m,
    )
    dem, affine_transform, res = read_dem_window(dem_path, bounds, smooth_sigma=0.0)
    H, W = dem.shape

    # Observer pixel coords within the window
    obs_row, obs_col = rowcol(affine_transform, observer_easting, observer_northing)
    obs_row = int(np.clip(obs_row, 0, H - 1))
    obs_col = int(np.clip(obs_col, 0, W - 1))

    z_obs = dem[obs_row, obs_col]
    if np.isnan(z_obs):
        z_obs = float(np.nanmean(dem))
    z_obs += observer_height_m

    visibility = np.zeros((H, W), dtype=np.bool_)

    # Row/col grids
    rows_grid, cols_grid = np.meshgrid(np.arange(H), np.arange(W), indexing='ij')

    for tgt_row in range(H):
        for tgt_col in range(W):
            dr = tgt_row - obs_row
            dc = tgt_col - obs_col
            dist_px = math.sqrt(dr * dr + dc * dc)
            dist_m = dist_px * res

            if dist_m > max_radius_m or dist_m < 1e-6:
                continue

            z_tgt = dem[tgt_row, tgt_col]
            if np.isnan(z_tgt):
                continue
            z_tgt += target_height_m

            # Number of intermediate samples
            n_steps = max(2, int(dist_px))
            line_visible = True

            for step in range(1, n_steps):
                t = step / n_steps
                r_int = obs_row + t * dr
                c_int = obs_col + t * dc
                r_i = int(round(r_int))
                c_i = int(round(c_int))
                r_i = np.clip(r_i, 0, H - 1)
                c_i = np.clip(c_i, 0, W - 1)

                d_step = t * dist_m
                z_terrain = dem[r_i, c_i]
                if np.isnan(z_terrain):
                    continue

                # Atmospheric refraction correction
                if apply_refraction and d_step > 100:
                    z_terrain -= refraction_k * (d_step ** 2) / (2.0 * R_earth)

                # Z of the sight ray at this intermediate point
                z_ray = z_obs + t * (z_tgt - z_obs)

                if z_terrain > z_ray:
                    line_visible = False
                    break

            visibility[tgt_row, tgt_col] = line_visible

    visible_pixels = int(np.sum(visibility))
    total_pixels = int(np.sum(~np.isnan(dem)))
    pixel_area = res ** 2

    # Max visible distance
    vis_rows, vis_cols = np.where(visibility)
    if len(vis_rows) > 0:
        dists = np.sqrt((vis_rows - obs_row) ** 2 + (vis_cols - obs_col) ** 2) * res
        max_dist = float(np.max(dists))
    else:
        max_dist = 0.0

    return ViewshedResult(
        visibility_array=visibility,
        transform=affine_transform,
        observer_easting=observer_easting,
        observer_northing=observer_northing,
        visible_area_m2=visible_pixels * pixel_area,
        total_area_m2=total_pixels * pixel_area,
        visible_fraction=visible_pixels / total_pixels if total_pixels > 0 else 0.0,
        max_visible_distance_m=max_dist,
    )


def compute_viewshed_grass(
    observer_easting: float,
    observer_northing: float,
    dem_path: str,
    observer_height_m: float = 1.8,
    max_radius_m: float = 2000.0,
    output_path: str = "/tmp/viewshed_out.tif",
) -> str:
    """
    Call GRASS GIS r.viewshed via subprocess for production-scale viewshed.
    Much faster than pure-Python for large radii. Requires GRASS installed.
    Returns path to output GeoTIFF.

    For intelligence use: preferred method when radius > 500 m.
    """
    import subprocess
    cmd = [
        "grass", "--tmp-location", dem_path,
        "--exec", "r.viewshed",
        f"input={dem_path}",
        f"output={output_path}",
        f"coordinates={observer_easting},{observer_northing}",
        f"observer_elevation={observer_height_m}",
        f"max_distance={max_radius_m}",
        "-c",   # apply atmospheric refraction correction
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"GRASS r.viewshed failed: {result.stderr}")
    return output_path


# ============================================================
# M6 — SLOPE & ASPECT ANALYSIS
# ============================================================

@dataclass
class SlopeAspectResult:
    slope_deg: NDArray[np.float64]     # per-pixel slope in degrees
    aspect_deg: NDArray[np.float64]    # per-pixel aspect 0–360, North-clockwise
    mean_slope_deg: float
    std_slope_deg: float
    max_slope_deg: float
    area_by_class_m2: Dict[str, float]  # slope class label → area m²
    aspect_histogram: NDArray[np.float64]  # 16-sector frequency (degrees 0-360)

    def summary(self) -> str:
        lines = [
            f"Mean slope: {self.mean_slope_deg:.2f}°  (std: {self.std_slope_deg:.2f}°)",
            f"Max slope:  {self.max_slope_deg:.2f}°",
            "Area by slope class:",
        ]
        for cls, area in self.area_by_class_m2.items():
            lines.append(f"  {cls}: {area:.1f} m² ({area/10000:.4f} ha)")
        return "\n".join(lines)


def compute_slope_aspect(
    polygon_projected: Polygon,
    dem_path: str,
    smooth_sigma: float = 0.0,    # Gaussian sigma in pixels; 0 = no smoothing
) -> SlopeAspectResult:
    """
    Pixel-wise slope and aspect from DEM within polygon AOI.
    Horn's method (same as hillshade — consistent gradient estimator).

    Aspect convention: 0° = North, increases clockwise (standard GIS convention).
    slope_pct = sqrt(dz_dx² + dz_dy²) × 100
    slope_deg = degrees(arctan(sqrt(dz_dx² + dz_dy²)))
    aspect = (90 − degrees(arctan2(dz_dy, −dz_dx))) mod 360  → North-clockwise
    """
    bounds = polygon_projected.bounds
    dem, transform, res = read_dem_window(dem_path, bounds, smooth_sigma=smooth_sigma)

    mask = rasterize(
        [mapping(polygon_projected)],
        out_shape=dem.shape, transform=transform,
        fill=0, default_value=1, dtype=np.uint8, all_touched=False,
    )
    inside = (mask == 1) & ~np.isnan(dem)

    dz_dx, dz_dy = horn_gradient(dem, res)

    slope_rad = np.arctan(np.sqrt(dz_dx ** 2 + dz_dy ** 2))
    slope_deg = np.degrees(slope_rad)

    # Aspect: North-clockwise convention
    aspect_math = np.degrees(np.arctan2(dz_dy, -dz_dx))
    aspect_north = (90.0 - aspect_math) % 360.0

    # Apply polygon mask
    slope_in = slope_deg[inside]
    aspect_in = aspect_north[inside]

    pixel_area = res ** 2

    # Slope classes (standard geomorphology)
    classes = {
        "0–5°":   (slope_in < 5),
        "5–15°":  (slope_in >= 5) & (slope_in < 15),
        "15–30°": (slope_in >= 15) & (slope_in < 30),
        "30–45°": (slope_in >= 30) & (slope_in < 45),
        ">45°":   (slope_in >= 45),
    }
    area_by_class = {k: float(np.sum(v)) * pixel_area for k, v in classes.items()}

    # Aspect histogram — 16 sectors of 22.5°
    hist, _ = np.histogram(aspect_in, bins=16, range=(0, 360))
    hist_norm = hist.astype(np.float64) / (len(aspect_in) + 1e-10)

    slope_out = np.full(dem.shape, np.nan)
    aspect_out = np.full(dem.shape, np.nan)
    slope_out[inside] = slope_in
    aspect_out[inside] = aspect_in

    return SlopeAspectResult(
        slope_deg=slope_out,
        aspect_deg=aspect_out,
        mean_slope_deg=float(np.nanmean(slope_in)),
        std_slope_deg=float(np.nanstd(slope_in)),
        max_slope_deg=float(np.nanmax(slope_in)) if len(slope_in) > 0 else 0.0,
        area_by_class_m2=area_by_class,
        aspect_histogram=hist_norm,
    )


# ============================================================
# M7 — STRUCTURED ANNOTATION (GeoPackage I/O)
# ============================================================

@dataclass
class AnnotationPoint:
    easting: float
    northing: float
    projected_epsg: int
    category: str          # "structure","vehicle","personnel","infrastructure","anomaly","other"
    confidence: str        # "confirmed","probable","possible","suspected"
    height_m: Optional[float] = None    # auto-sampled from DEM
    timestamp: Optional[str] = None     # ISO8601
    notes: str = ""
    classification_level: str = "UNCLASS"  # "UNCLASS","CONFIDENTIAL","SECRET","TOP SECRET"
    fid: Optional[int] = None


@dataclass
class AnnotationPolygon:
    vertices_projected: List[Tuple[float, float]]
    projected_epsg: int
    feature_type: str      # "building","compound","vehicle_park","cleared_area","crater","other"
    condition: str = "intact"
    area_m2: float = 0.0           # auto-computed
    perimeter_m: float = 0.0       # auto-computed
    orientation_deg: float = 0.0   # MBR azimuth, auto-computed
    notes: str = ""
    fid: Optional[int] = None


def compute_mbr_orientation(polygon: Polygon) -> float:
    """
    Compute the azimuth of the longer axis of the minimum bounding rectangle.
    Returns degrees from North (0–180°), clockwise.
    Used for building alignment analysis in intelligence work.

    Shapely minimum_rotated_rectangle returns a rectangle aligned to the longest axis.
    We extract the longer edge vector and compute its azimuth.
    """
    mbr = polygon.minimum_rotated_rectangle
    coords = list(mbr.exterior.coords)
    # MBR has 5 points (closed ring), pick the longer of the two edge directions
    edges = []
    for i in range(4):
        dx = coords[i + 1][0] - coords[i][0]
        dy = coords[i + 1][1] - coords[i][1]
        length = math.sqrt(dx * dx + dy * dy)
        azimuth = (math.degrees(math.atan2(dx, dy))) % 180.0  # 0–180°
        edges.append((length, azimuth))
    edges.sort(reverse=True)
    return edges[0][1]  # azimuth of longest edge


def create_annotation_point(
    easting: float, northing: float, projected_epsg: int,
    category: str, confidence: str,
    dem_path: Optional[str] = None, **kwargs
) -> AnnotationPoint:
    """Create a point annotation, auto-sampling elevation from DEM if provided."""
    height = None
    if dem_path:
        h = get_dem_value_at_point(dem_path, easting, northing)
        if not math.isnan(h):
            height = h
    ts = datetime.datetime.utcnow().isoformat() + "Z"
    return AnnotationPoint(
        easting=easting, northing=northing, projected_epsg=projected_epsg,
        category=category, confidence=confidence,
        height_m=height, timestamp=ts, **kwargs
    )


def create_annotation_polygon(
    vertices: List[Tuple[float, float]], projected_epsg: int,
    feature_type: str, **kwargs
) -> AnnotationPolygon:
    """Create a polygon annotation with auto-computed area, perimeter, MBR orientation."""
    poly = Polygon(vertices)
    area = poly.area
    mbr_az = compute_mbr_orientation(poly)

    # Perimeter via Vincenty
    transformer = Transformer.from_crs(
        f"EPSG:{projected_epsg}", "EPSG:4326", always_xy=True
    )
    verts = list(poly.exterior.coords)
    perim = 0.0
    for i in range(len(verts) - 1):
        lon1, lat1 = transformer.transform(verts[i][0], verts[i][1])
        lon2, lat2 = transformer.transform(verts[i + 1][0], verts[i + 1][1])
        d, _, _ = vincenty_distance(lon1, lat1, lon2, lat2)
        perim += d

    return AnnotationPolygon(
        vertices_projected=vertices, projected_epsg=projected_epsg,
        feature_type=feature_type, area_m2=area,
        perimeter_m=perim, orientation_deg=mbr_az, **kwargs
    )


def save_annotations_to_gpkg(
    points: List[AnnotationPoint],
    polygons: List[AnnotationPolygon],
    output_path: str,
    projected_epsg: int,
):
    """
    Save all annotations to a GeoPackage (.gpkg) file.
    GeoPackage is the OGC standard replacing Shapefiles — single SQLite file,
    supports multiple layers, full CRS, no 10-char field name limit.
    Requires fiona.
    """
    if not FIONA_AVAILABLE:
        raise ImportError("fiona is required for GeoPackage export. pip install fiona")

    crs_wkt = CRS.from_epsg(projected_epsg).to_wkt()

    # Points layer
    point_schema = {
        "geometry": "Point",
        "properties": {
            "category": "str", "confidence": "str",
            "height_m": "float", "timestamp": "str",
            "notes": "str", "class_level": "str",
        }
    }
    with fiona.open(output_path, "w", driver="GPKG", schema=point_schema,
                   crs=crs_wkt, layer="annotations_point") as dst:
        for ann in points:
            dst.write({
                "geometry": mapping(Point(ann.easting, ann.northing)),
                "properties": {
                    "category": ann.category, "confidence": ann.confidence,
                    "height_m": ann.height_m or -9999.0,
                    "timestamp": ann.timestamp or "",
                    "notes": ann.notes, "class_level": ann.classification_level,
                }
            })

    # Polygons layer
    poly_schema = {
        "geometry": "Polygon",
        "properties": {
            "feature_type": "str", "condition": "str",
            "area_m2": "float", "perimeter_m": "float",
            "orientation_deg": "float", "notes": "str",
        }
    }
    with fiona.open(output_path, "a", driver="GPKG", schema=poly_schema,
                   crs=crs_wkt, layer="annotations_polygon") as dst:
        for ann in polygons:
            dst.write({
                "geometry": mapping(Polygon(ann.vertices_projected)),
                "properties": {
                    "feature_type": ann.feature_type, "condition": ann.condition,
                    "area_m2": ann.area_m2, "perimeter_m": ann.perimeter_m,
                    "orientation_deg": ann.orientation_deg, "notes": ann.notes,
                }
            })


# ============================================================
# M8 — SHADOW HEIGHT ESTIMATION
# ============================================================

@dataclass
class ShadowHeightResult:
    estimated_height_m: float
    height_corrected_m: Optional[float]   # DEM terrain-slope corrected
    shadow_length_m: float
    solar_elevation_deg: float
    solar_azimuth_deg: float
    uncertainty_m: float                  # ±pixel_resolution / tan(solar_elev)
    is_reliable: bool                     # False if solar_elev < 10°
    warning: Optional[str]

    def summary(self) -> str:
        h = self.height_corrected_m if self.height_corrected_m is not None else self.estimated_height_m
        lines = [
            f"Estimated height:    {h:.2f} m ± {self.uncertainty_m:.2f} m",
            f"Shadow length:       {self.shadow_length_m:.3f} m",
            f"Solar elevation:     {self.solar_elevation_deg:.2f}°",
            f"Solar azimuth:       {self.solar_azimuth_deg:.2f}°",
        ]
        if not self.is_reliable:
            lines.append(f"WARNING: {self.warning}")
        return "\n".join(lines)


def measure_shadow_height(
    base_lon: float, base_lat: float,             # WGS84 — base of object
    shadow_tip_lon: float, shadow_tip_lat: float,  # WGS84 — tip of shadow on ground
    acquisition_datetime_utc: datetime.datetime,   # must be timezone-aware UTC
    dem_path: Optional[str] = None,
    projected_epsg: Optional[int] = None,
    imagery_resolution_m: float = 0.05,           # 5 cm default for RGB imagery
) -> ShadowHeightResult:
    """
    Estimate object height from shadow length using solar geometry.

    Formula:
        H = shadow_length × tan(solar_elevation)

    DEM slope correction (if DEM available):
        If base and shadow tip are at different elevations (sloped terrain),
        the shadow foreshortens or elongates. Correction:
            ΔZ = DEM(shadow_tip) − DEM(base)
            H_corrected = H − ΔZ    [first-order terrain correction]

    Uncertainty from pixel resolution:
        δH = imagery_resolution_m / tan(solar_elevation)
        A 5 cm pixel at 30° sun angle introduces ±8.7 cm height uncertainty.

    Requires pysolar (offline, pure Python).
    Input datetime must be UTC and timezone-aware:
        dt = datetime.datetime(2024, 6, 15, 8, 30, 0, tzinfo=datetime.timezone.utc)
    """
    if not PYSOLAR_AVAILABLE:
        raise ImportError("pysolar not installed. pip install pysolar")

    # Validate direction: shadow should fall away from sun
    solar_az = get_azimuth(base_lat, base_lon, acquisition_datetime_utc)
    solar_el = get_altitude(base_lat, base_lon, acquisition_datetime_utc)

    warning = None
    is_reliable = True
    if solar_el < 10.0:
        warning = (
            f"Solar elevation is {solar_el:.1f}° — very low sun angle. "
            "Shadow length is extremely sensitive to small errors. "
            "Height estimate is UNRELIABLE."
        )
        is_reliable = False

    # Geodetic distance base → shadow tip
    shadow_length_m, shadow_az, _ = vincenty_distance(
        base_lon, base_lat, shadow_tip_lon, shadow_tip_lat
    )

    # Check shadow direction vs solar azimuth (should be ~180° opposite)
    shadow_direction_from_sun = (solar_az + 180.0) % 360.0
    angle_diff = abs(shadow_az - shadow_direction_from_sun)
    if angle_diff > 180:
        angle_diff = 360 - angle_diff
    if angle_diff > 30.0:
        warning = (
            f"Shadow direction ({shadow_az:.1f}°) differs from expected "
            f"({shadow_direction_from_sun:.1f}°) by {angle_diff:.1f}°. "
            "Check that base and shadow tip points are correctly placed."
        )
        is_reliable = False

    # Core formula
    solar_el_rad = math.radians(solar_el)
    if solar_el <= 0.1:
        return ShadowHeightResult(
            estimated_height_m=0.0, height_corrected_m=None,
            shadow_length_m=shadow_length_m,
            solar_elevation_deg=solar_el, solar_azimuth_deg=solar_az,
            uncertainty_m=999.0, is_reliable=False,
            warning="Sun is below horizon — cannot compute height."
        )

    H = shadow_length_m * math.tan(solar_el_rad)

    # Pixel resolution uncertainty
    uncertainty = imagery_resolution_m / math.tan(solar_el_rad)

    # DEM terrain correction
    H_corrected = None
    if dem_path and projected_epsg:
        e_base, n_base = wgs84_to_projected(base_lon, base_lat, projected_epsg)
        e_tip, n_tip = wgs84_to_projected(shadow_tip_lon, shadow_tip_lat, projected_epsg)
        z_base = get_dem_value_at_point(dem_path, e_base, n_base)
        z_tip = get_dem_value_at_point(dem_path, e_tip, n_tip)
        if not (math.isnan(z_base) or math.isnan(z_tip)):
            dz = z_tip - z_base
            # First-order terrain correction:
            # On upslope: shadow is shorter than on flat ground → H is underestimated → add back
            # On downslope: shadow is longer → H overestimated → subtract
            H_corrected = H - dz

    return ShadowHeightResult(
        estimated_height_m=H,
        height_corrected_m=H_corrected,
        shadow_length_m=shadow_length_m,
        solar_elevation_deg=solar_el,
        solar_azimuth_deg=solar_az,
        uncertainty_m=uncertainty,
        is_reliable=is_reliable,
        warning=warning,
    )


# ============================================================
# QUICK DEMO / SMOKE TEST (offline, no real data needed)
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("GIS Reference Implementation — Smoke Tests")
    print("=" * 60)

    # --- M1: Distance ---
    print("\n[M1] Geodetic Distance (Delhi to Agra)")
    r = measure_distance(77.2090, 28.6139, 78.0081, 27.1767)
    print(r.summary())

    # --- M2: Polygon Area (synthetic) ---
    print("\n[M2] Polygon Area (100m × 50m rectangle, UTM43N EPSG:32643)")
    verts = [(500000.0, 3000000.0), (500100.0, 3000000.0),
             (500100.0, 3000050.0), (500000.0, 3000050.0),
             (500000.0, 3000000.0)]
    # Without DEM (planimetric only)
    poly = Polygon(verts)
    area = poly.area
    print(f"  Planimetric area (Shoelace): {area:.2f} m²  (expect 5000.00)")

    # --- M7: MBR Orientation ---
    print("\n[M7] MBR Orientation of rotated rectangle")
    import shapely.affinity
    rect = Polygon([(0, 0), (100, 0), (100, 30), (0, 30), (0, 0)])
    rect_rotated = shapely.affinity.rotate(rect, 37.0, origin='centroid')
    az = compute_mbr_orientation(rect_rotated)
    print(f"  MBR azimuth: {az:.1f}°  (expect ~37.0°)")

    # --- Hillshade (synthetic DEM) ---
    print("\n[V2] Hillshade on synthetic 100×100 DEM cone")
    y, x = np.mgrid[0:100, 0:100]
    cone_dem = 100.0 - np.sqrt((x - 50) ** 2 + (y - 50) ** 2).astype(np.float64)
    cone_dem = np.clip(cone_dem, 0, 100)
    hs = Hillshade.compute(cone_dem, res=1.0, azimuth_deg=315.0, elevation_deg=45.0)
    print(f"  Hillshade min: {hs.min()}, max: {hs.max()}, mean: {hs.mean():.1f}")

    hs_multi = Hillshade.compute_multidirectional(cone_dem, res=1.0)
    print(f"  Multi-dir HS  min: {hs_multi.min()}, max: {hs_multi.max()}, mean: {hs_multi.mean():.1f}")

    # --- Colour Relief ---
    print("\n[V3] Colour Relief on cone DEM")
    ramp = ColourRelief.viridis_ramp()
    rgb = ColourRelief.render(cone_dem, ramp, mode="relative")
    print(f"  Colour relief shape: {rgb.shape}, dtype: {rgb.dtype}")

    # --- Shadow height (no DEM) ---
    if PYSOLAR_AVAILABLE:
        print("\n[M8] Shadow height estimation")
        dt_utc = datetime.datetime(2024, 6, 15, 6, 0, 0,
                                   tzinfo=datetime.timezone.utc)
        try:
            sh = measure_shadow_height(
                base_lon=77.209, base_lat=28.614,
                shadow_tip_lon=77.2091, shadow_tip_lat=28.6139,
                acquisition_datetime_utc=dt_utc,
                imagery_resolution_m=0.05,
            )
            print(sh.summary())
        except Exception as e:
            print(f"  Shadow test error: {e}")
    else:
        print("\n[M8] pysolar not available — skipping shadow test")

    print("\n" + "=" * 60)
    print("All smoke tests complete.")
    print("=" * 60)
