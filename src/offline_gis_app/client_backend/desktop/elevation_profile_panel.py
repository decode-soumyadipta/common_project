"""Elevation Profile Panel — embedded Qt widget, GPU-accelerated via QOpenGLWidget.

Layout (embedded in main window vertical splitter):
  ┌─────────────────────────────────────────────────────────────┐
  │  ▌ Elevation Profile  ──────────────────────────  [✕ Close] │  ← header bar
  ├──────────────────────────┬──────────────────────────────────┤
  │   2D Profile Chart       │   3D Section Plane               │
  │   (distance vs elev)     │   (oblique cut view)             │
  └──────────────────────────┴──────────────────────────────────┘

Uses QOpenGLWidget as base so Qt routes all QPainter calls through the GPU
compositor on Windows/NVIDIA — smooth, hardware-accelerated rendering.
Falls back to QWidget transparently if OpenGL is unavailable.
"""
from __future__ import annotations

import math
from typing import Sequence

from qtpy.QtCore import QPointF, Qt, Signal
from qtpy.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from qtpy.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# Try GPU-accelerated base; fall back to plain QWidget silently
try:
    from qtpy.QtOpenGLWidgets import QOpenGLWidget as _ChartBase  # Qt6
except ImportError:
    try:
        from qtpy.QtWidgets import QOpenGLWidget as _ChartBase  # Qt5
    except ImportError:
        _ChartBase = QWidget  # CPU fallback — still works fine


# ── Colour palette ────────────────────────────────────────────────────────────
_BG          = QColor(255, 255, 255)
_GRID        = QColor(215, 225, 240)
_AXIS        = QColor( 50,  70, 100)
_FILL_TOP    = QColor( 41, 128, 185, 210)
_FILL_BOT    = QColor( 41, 128, 185,  30)
_LINE        = QColor( 25,  90, 160)
_TICK_LABEL  = QColor( 55,  75, 105)
_TITLE       = QColor( 15,  35,  65)
_RIBBON_TOP  = QColor( 41, 128, 185, 220)
_RIBBON_BOT  = QColor( 41, 128, 185,  50)
_RIBBON_EDGE = QColor( 15,  70, 150)
_SECTION_BG  = QColor(245, 248, 252)
_SECTION_FILL_TOP = QColor( 80, 160, 220, 200)
_SECTION_FILL_BOT = QColor( 80, 160, 220,  40)

_FONT_SMALL = QFont("Menlo", 9)
_FONT_TITLE = QFont("Segoe UI", 10, QFont.Weight.Bold)
_FONT_AXIS  = QFont("Segoe UI", 9)

_ML = 58   # margin left  (Y-axis labels)
_MB = 44   # margin bottom (X-axis labels)
_MT = 28   # margin top
_MR = 14   # margin right


# ─────────────────────────────────────────────────────────────────────────────
# 2D Profile Chart
# ─────────────────────────────────────────────────────────────────────────────

class _Profile2DWidget(_ChartBase):
    """2D elevation profile: distance (m) on X, elevation (m) on Y."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._values: list[float] = []
        self._distance_m: float = 0.0
        self._cursor_frac: float | None = None   # 0–1 along the profile, None = hidden
        self.setMinimumSize(300, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, values: list[float], distance_m: float) -> None:
        self._values = [v for v in values if math.isfinite(v)]
        self._distance_m = float(distance_m)
        self._cursor_frac = None
        self.update()

    def set_cursor_fraction(self, frac: float | None) -> None:
        """Move the georeferenced cursor to position frac (0–1) along the profile."""
        self._cursor_frac = frac
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.fillRect(0, 0, self.width(), self.height(), _BG)
        if len(self._values) >= 2:
            self._draw(p, self.width(), self.height())
        p.end()

    def _draw(self, p: QPainter, W: int, H: int) -> None:
        vals   = self._values
        n      = len(vals)
        vmin   = min(vals)
        vmax   = max(vals)
        vrange = max(vmax - vmin, 1.0)
        dist   = self._distance_m

        # Chart rectangle
        lx = _ML;  rx = W - _MR
        ty = _MT;  by = H - _MB
        cw = max(rx - lx, 1);  ch = max(by - ty, 1)

        def px(i: int) -> float:
            return lx + (i / (n - 1)) * cw

        def py(v: float) -> float:
            return by - ((v - vmin) / vrange) * ch

        # ── Grid ──────────────────────────────────────────────────────────
        p.setFont(_FONT_SMALL)
        fm = QFontMetrics(_FONT_SMALL)
        n_y = 5
        for i in range(n_y + 1):
            frac = i / n_y
            elev = vmin + frac * vrange
            y    = by - frac * ch
            p.setPen(QPen(_GRID, 1, Qt.PenStyle.DashLine))
            p.drawLine(lx, int(y), rx, int(y))
            p.setPen(_TICK_LABEL)
            lbl = f"{elev:.0f} m"
            tw  = fm.horizontalAdvance(lbl)
            p.drawText(lx - tw - 5, int(y) + fm.ascent() // 2, lbl)

        n_x = 5
        for i in range(n_x + 1):
            frac = i / n_x
            d    = frac * dist
            x    = lx + frac * cw
            p.setPen(QPen(_GRID, 1, Qt.PenStyle.DashLine))
            p.drawLine(int(x), ty, int(x), by)
            p.setPen(_TICK_LABEL)
            lbl = f"{d/1000:.1f} km" if d >= 1000 else f"{d:.0f} m"
            tw  = fm.horizontalAdvance(lbl)
            p.drawText(int(x) - tw // 2, by + fm.height() + 3, lbl)

        # ── Filled area ───────────────────────────────────────────────────
        path = QPainterPath()
        path.moveTo(QPointF(px(0), by))
        for i in range(n):
            path.lineTo(QPointF(px(i), py(vals[i])))
        path.lineTo(QPointF(px(n - 1), by))
        path.closeSubpath()

        grad = QLinearGradient(0, ty, 0, by)
        grad.setColorAt(0.0, _FILL_TOP)
        grad.setColorAt(1.0, _FILL_BOT)
        p.fillPath(path, grad)

        # ── Profile line ──────────────────────────────────────────────────
        p.setPen(QPen(_LINE, 2))
        for i in range(1, n):
            p.drawLine(QPointF(px(i - 1), py(vals[i - 1])), QPointF(px(i), py(vals[i])))

        # ── Axes ──────────────────────────────────────────────────────────
        p.setPen(QPen(_AXIS, 1.5))
        p.drawLine(lx, ty, lx, by)
        p.drawLine(lx, by, rx, by)

        # ── Axis labels ───────────────────────────────────────────────────
        p.setFont(_FONT_AXIS)
        p.setPen(_TITLE)
        p.save()
        p.translate(13, (ty + by) // 2)
        p.rotate(-90)
        p.drawText(-45, 0, "Elevation (m)")
        p.restore()
        p.drawText((lx + rx) // 2 - 50, H - 3, "Distance along profile")

        # ── Title + stats ─────────────────────────────────────────────────
        p.setFont(_FONT_TITLE)
        p.setPen(_TITLE)
        p.drawText(lx, ty - 6, "2D Elevation Profile")
        p.setFont(_FONT_SMALL)
        p.setPen(_TICK_LABEL)
        dist_str = f"{dist/1000:.2f} km" if dist >= 1000 else f"{dist:.0f} m"
        p.drawText(
            rx - 260, ty - 6,
            f"Min {vmin:.1f} m  Max {vmax:.1f} m  Δ {vmax-vmin:.1f} m  L {dist_str}",
        )

        # ── Georeferenced cursor crosshair ────────────────────────────────
        if self._cursor_frac is not None and 0.0 <= self._cursor_frac <= 1.0:
            frac = self._cursor_frac
            # Interpolate elevation at cursor position
            idx_f = frac * (n - 1)
            idx0  = int(idx_f)
            idx1  = min(idx0 + 1, n - 1)
            t     = idx_f - idx0
            elev_at_cursor = vals[idx0] * (1.0 - t) + vals[idx1] * t

            cx = lx + frac * cw
            cy_cursor = py(elev_at_cursor)

            # Dotted vertical line (X axis indicator)
            cursor_pen = QPen(QColor(200, 160, 0, 200), 1.0, Qt.PenStyle.DotLine)
            p.setPen(cursor_pen)
            p.drawLine(int(cx), ty, int(cx), by)
            # Dotted horizontal line (Y axis indicator)
            p.drawLine(lx, int(cy_cursor), rx, int(cy_cursor))

            # Cursor point — dull yellow filled circle
            p.setPen(QPen(QColor(80, 50, 0, 220), 1.2))
            p.setBrush(QColor(200, 160, 0, 220))
            r = 5
            p.drawEllipse(int(cx) - r, int(cy_cursor) - r, r * 2, r * 2)

            # Readout label
            d_at_cursor = frac * dist
            d_str = f"{d_at_cursor/1000:.2f} km" if d_at_cursor >= 1000 else f"{d_at_cursor:.0f} m"
            lbl = f"{d_str}  {elev_at_cursor:.1f} m"
            p.setFont(_FONT_SMALL)
            fm2 = QFontMetrics(_FONT_SMALL)
            tw2 = fm2.horizontalAdvance(lbl)
            lbl_x = min(int(cx) + 7, rx - tw2 - 2)
            lbl_y = max(int(cy_cursor) - 5, ty + fm2.ascent())
            p.setPen(QColor(80, 50, 0, 230))
            p.drawText(lbl_x, lbl_y, lbl)


# ─────────────────────────────────────────────────────────────────────────────
# 3D Section Plane Widget
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# 3D Section Plane Widget — interactive (drag to rotate, scroll to zoom)
# ─────────────────────────────────────────────────────────────────────────────

def _elev_to_color(frac: float) -> QColor:
    """Map normalised elevation [0,1] to a terrain colormap (blue→green→yellow→red)."""
    stops = [
        (0.00, QColor( 68,  1, 84)),   # deep purple (low)
        (0.25, QColor( 59, 82, 139)),  # blue
        (0.50, QColor( 33, 145, 140)), # teal
        (0.75, QColor( 94, 201,  98)), # green
        (1.00, QColor(253, 231,  37)), # yellow (high)
    ]
    frac = max(0.0, min(1.0, frac))
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        if frac <= t1:
            t = (frac - t0) / (t1 - t0)
            r = int(c0.red()   + t * (c1.red()   - c0.red()))
            g = int(c0.green() + t * (c1.green() - c0.green()))
            b = int(c0.blue()  + t * (c1.blue()  - c0.blue()))
            return QColor(r, g, b, 220)
    return stops[-1][1]


class _Profile3DWidget(_ChartBase):
    """Interactive 3D cross-section plane.

    Mouse controls:
      Left-drag  — rotate azimuth / tilt
      Scroll     — zoom in/out
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._values: list[float] = []
        self._distance_m: float = 0.0
        # View state
        self._azimuth: float = 25.0    # degrees, horizontal rotation
        self._tilt: float    = 28.0    # degrees, vertical tilt
        self._zoom: float    = 1.0
        self._pan_x: float   = 0.0    # horizontal pan offset (normalised)
        self._pan_y: float   = 0.0    # vertical pan offset (normalised)
        self._drag_start = None
        self._drag_mode: str = "rotate"   # "rotate" or "pan"
        self._cursor_frac: float | None = None   # georeferenced cursor position
        self.setMinimumSize(300, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def set_data(self, values: list[float], distance_m: float) -> None:
        self._values = [v for v in values if math.isfinite(v)]
        self._distance_m = float(distance_m)
        self._cursor_frac = None
        self.update()

    def set_cursor_fraction(self, frac: float | None) -> None:
        """Move the georeferenced cursor to position frac (0–1) along the profile."""
        self._cursor_frac = frac
        self.update()

    # ── Mouse interaction ─────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_mode = "rotate"
            self._drag_start = (event.x(), event.y(), self._azimuth, self._tilt, self._pan_x, self._pan_y)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif event.button() == Qt.MouseButton.RightButton:
            self._drag_mode = "pan"
            self._drag_start = (event.x(), event.y(), self._azimuth, self._tilt, self._pan_x, self._pan_y)
            self.setCursor(Qt.CursorShape.SizeAllCursor)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_start = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        """Double-click resets view to default."""
        self._azimuth = 25.0
        self._tilt    = 28.0
        self._zoom    = 1.0
        self._pan_x   = 0.0
        self._pan_y   = 0.0
        self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_start is None:
            return
        x0, y0, az0, tilt0, px0, py0 = self._drag_start
        dx = event.x() - x0
        dy = event.y() - y0
        if self._drag_mode == "rotate":
            self._azimuth = az0 + dx * 0.4
            self._tilt    = max(5.0, min(85.0, tilt0 - dy * 0.3))
        else:  # pan
            scale = 0.002 / max(self._zoom, 0.1)
            self._pan_x = px0 + dx * scale
            self._pan_y = py0 - dy * scale
        self.update()

    def wheelEvent(self, event) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        self._zoom *= (1.15 if delta > 0 else 0.87)
        self._zoom = max(0.2, min(6.0, self._zoom))
        self.update()

    # ── Rendering ─────────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.fillRect(0, 0, self.width(), self.height(), _BG)
        if len(self._values) >= 2:
            self._draw(p, self.width(), self.height())
        p.end()

    def _project(self, x3: float, y3: float, z3: float,
                 cx: float, cy: float, scale: float,
                 az_rad: float, tilt_rad: float) -> QPointF:
        """Simple oblique projection: rotate around Y then tilt around X."""
        # Rotate around vertical axis (azimuth)
        rx = x3 * math.cos(az_rad) - z3 * math.sin(az_rad)
        rz = x3 * math.sin(az_rad) + z3 * math.cos(az_rad)
        # Tilt (elevation angle)
        sx = rx
        sy = y3 * math.cos(tilt_rad) - rz * math.sin(tilt_rad)
        return QPointF(cx + sx * scale, cy - sy * scale)

    def _draw(self, p: QPainter, W: int, H: int) -> None:
        vals   = self._values
        n      = len(vals)
        vmin   = min(vals)
        vmax   = max(vals)
        vrange = max(vmax - vmin, 1.0)

        # Colorbar width
        cb_w = 18
        cb_x = W - cb_w - 8

        # 3D world coords: X = distance [0..1], Y = elevation [0..1], Z = depth [0..0.15]
        az_rad   = math.radians(self._azimuth)
        tilt_rad = math.radians(self._tilt)
        scale    = min(W - cb_w - 30, H - 50) * 0.38 * self._zoom
        cx       = (W - cb_w - 20) * 0.5 + self._pan_x * scale * 2
        cy       = H * 0.55 + self._pan_y * scale * 2

        def pt(i: int, depth: float = 0.0) -> QPointF:
            x3 = (i / (n - 1)) - 0.5
            y3 = (vals[i] - vmin) / vrange - 0.3
            z3 = depth
            return self._project(x3, y3, z3, cx, cy, scale, az_rad, tilt_rad)

        def pt_base(i: int, depth: float = 0.0) -> QPointF:
            x3 = (i / (n - 1)) - 0.5
            y3 = -0.3
            z3 = depth
            return self._project(x3, y3, z3, cx, cy, scale, az_rad, tilt_rad)

        depth = 0.15  # thickness of the section plane

        # ── Back face ─────────────────────────────────────────────────────
        bp = QPolygonF([pt(i, depth) for i in range(n)] +
                       [pt_base(i, depth) for i in range(n - 1, -1, -1)])
        p.setBrush(QColor(200, 220, 240, 60))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(bp)

        # ── Front face — coloured strips ──────────────────────────────────
        for i in range(n - 1):
            frac_l = (vals[i]   - vmin) / vrange
            frac_r = (vals[i+1] - vmin) / vrange
            frac_m = (frac_l + frac_r) / 2
            col = _elev_to_color(frac_m)
            quad = QPolygonF([
                pt(i, 0), pt(i+1, 0),
                pt_base(i+1, 0), pt_base(i, 0),
            ])
            p.setBrush(col)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPolygon(quad)

        # ── Top connecting face ───────────────────────────────────────────
        for i in range(n - 1):
            frac_m = ((vals[i] + vals[i+1]) / 2 - vmin) / vrange
            col = _elev_to_color(frac_m)
            col.setAlpha(120)
            quad = QPolygonF([pt(i, 0), pt(i+1, 0), pt(i+1, depth), pt(i, depth)])
            p.setBrush(col)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPolygon(quad)

        # ── Side walls ────────────────────────────────────────────────────
        for side_i in [0, n - 1]:
            wall = QPolygonF([pt(side_i, 0), pt(side_i, depth),
                              pt_base(side_i, depth), pt_base(side_i, 0)])
            p.setBrush(QColor(100, 140, 180, 80))
            p.setPen(QPen(_RIBBON_EDGE, 0.6))
            p.drawPolygon(wall)

        # ── Profile edge line ─────────────────────────────────────────────
        p.setPen(QPen(QColor(20, 60, 120), 1.8))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(1, n):
            p.drawLine(pt(i - 1, 0), pt(i, 0))

        # ── Base lines ────────────────────────────────────────────────────
        p.setPen(QPen(_AXIS, 0.8))
        p.drawLine(pt_base(0, 0), pt_base(n - 1, 0))
        p.drawLine(pt_base(0, depth), pt_base(n - 1, depth))
        p.drawLine(pt_base(0, 0), pt_base(0, depth))
        p.drawLine(pt_base(n - 1, 0), pt_base(n - 1, depth))

        # ── Y-axis ticks ──────────────────────────────────────────────────
        p.setFont(_FONT_SMALL)
        fm = QFontMetrics(_FONT_SMALL)
        p.setPen(_TICK_LABEL)
        for i in range(5):
            frac = i / 4
            elev = vmin + frac * vrange
            x3   = -0.5
            y3   = frac - 0.3
            sp   = self._project(x3, y3, 0, cx, cy, scale, az_rad, tilt_rad)
            lbl  = f"{elev:.0f} m"
            tw   = fm.horizontalAdvance(lbl)
            p.drawText(int(sp.x()) - tw - 4, int(sp.y()) + fm.ascent() // 2, lbl)

        # ── Title ─────────────────────────────────────────────────────────
        p.setFont(_FONT_TITLE)
        p.setPen(_TITLE)
        p.drawText(8, 18, "3D Cross-Section")
        p.setFont(_FONT_SMALL)
        p.setPen(_TICK_LABEL)
        p.drawText(8, 30, "L-drag: rotate  R-drag: pan  Scroll: zoom  Dbl-click: reset")

        # ── Colorbar ──────────────────────────────────────────────────────
        cb_h = H - 60
        cb_y0 = 30
        n_stops = 64
        for i in range(n_stops):
            frac = i / (n_stops - 1)
            col  = _elev_to_color(frac)
            col.setAlpha(255)
            y    = cb_y0 + (1.0 - frac) * cb_h
            p.fillRect(cb_x, int(y), cb_w, max(1, int(cb_h / n_stops) + 1), col)

        # Colorbar border
        p.setPen(QPen(_AXIS, 0.8))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(cb_x, cb_y0, cb_w, int(cb_h))

        # Colorbar labels
        p.setFont(_FONT_SMALL)
        p.setPen(_TICK_LABEL)
        for i in range(5):
            frac = i / 4
            elev = vmin + frac * vrange
            y    = cb_y0 + (1.0 - frac) * cb_h
            lbl  = f"{elev:.0f}"
            p.drawText(cb_x + cb_w + 3, int(y) + fm.ascent() // 2, lbl)

        # Colorbar title (rotated)
        p.save()
        p.translate(W - 4, cb_y0 + cb_h // 2)
        p.rotate(90)
        p.drawText(-20, 0, "m")
        p.restore()

        # ── Georeferenced cursor point on 3D section ──────────────────────
        if self._cursor_frac is not None and 0.0 <= self._cursor_frac <= 1.0 and n >= 2:
            frac = self._cursor_frac
            idx_f = frac * (n - 1)
            idx0  = int(idx_f)
            idx1  = min(idx0 + 1, n - 1)
            t     = idx_f - idx0
            elev_at_cursor = vals[idx0] * (1.0 - t) + vals[idx1] * t

            # Project the cursor point onto the front face of the 3D section
            x3 = frac - 0.5
            y3 = (elev_at_cursor - vmin) / vrange - 0.3
            sp = self._project(x3, y3, 0.0, cx, cy, scale, az_rad, tilt_rad)

            # Dull yellow point
            p.setPen(QPen(QColor(80, 50, 0, 220), 1.5))
            p.setBrush(QColor(200, 160, 0, 220))
            r = 6
            p.drawEllipse(int(sp.x()) - r, int(sp.y()) - r, r * 2, r * 2)

            # Dotted vertical drop line to base
            base_sp = self._project(x3, -0.3, 0.0, cx, cy, scale, az_rad, tilt_rad)
            p.setPen(QPen(QColor(200, 160, 0, 160), 1.0, Qt.PenStyle.DotLine))
            p.drawLine(sp, base_sp)


# ─────────────────────────────────────────────────────────────────────────────
# Embedded panel (not a dialog — lives inside the main window splitter)
# ─────────────────────────────────────────────────────────────────────────────

class ElevationProfilePanel(QWidget):
    """Embedded elevation profile panel — docks below the map view.

    Signals:
        close_requested: emitted when the user clicks the ✕ button.
    """

    close_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(220)
        self.setMaximumHeight(340)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # ── Separator line at top ─────────────────────────────────────────
        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setStyleSheet("QFrame { color: #c9d3df; margin: 0px; }")
        sep.setFixedHeight(1)

        # ── Header bar ────────────────────────────────────────────────────
        header_bar = QWidget(self)
        header_bar.setFixedHeight(26)
        header_bar.setStyleSheet(
            "QWidget { background: #eef2f7; }"
        )
        hbl = QHBoxLayout(header_bar)
        hbl.setContentsMargins(8, 0, 8, 0)
        hbl.setSpacing(6)

        icon_lbl = QLabel("Elevation Profile", header_bar)
        icon_lbl.setStyleSheet("font-weight: 600; font-size: 11px; color: #1a2a3a; background: transparent;")
        hbl.addWidget(icon_lbl)
        hbl.addStretch(1)

        self._info_label = QLabel("", header_bar)
        self._info_label.setStyleSheet("font-size: 10px; color: #4a6080; background: transparent;")
        hbl.addWidget(self._info_label)

        close_btn = QPushButton("✕", header_bar)
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #6a7a8a; font-size: 12px; }"
            "QPushButton:hover { color: #c0392b; }"
        )
        close_btn.clicked.connect(self.close_requested.emit)
        hbl.addWidget(close_btn)

        # ── Charts ────────────────────────────────────────────────────────
        self._chart_2d = _Profile2DWidget(self)
        self._chart_3d = _Profile3DWidget(self)

        charts_row = QHBoxLayout()
        charts_row.setContentsMargins(0, 0, 0, 0)
        charts_row.setSpacing(1)
        charts_row.addWidget(self._chart_2d)

        divider = QFrame(self)
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        divider.setStyleSheet("color: #c9d3df;")
        charts_row.addWidget(divider)

        charts_row.addWidget(self._chart_3d)

        # ── Root layout ───────────────────────────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(sep)
        root.addWidget(header_bar)
        root.addLayout(charts_row)

    def set_profile(
        self,
        values: Sequence[float],
        distance_m: float,
        start_lon: float,
        start_lat: float,
        end_lon: float,
        end_lat: float,
    ) -> None:
        """Populate both charts with profile data."""
        vals = [float(v) for v in values if math.isfinite(float(v))]
        if not vals:
            return
        vmin = min(vals)
        vmax = max(vals)
        dist_str = f"{distance_m/1000:.2f} km" if distance_m >= 1000 else f"{distance_m:.0f} m"
        self._info_label.setText(
            f"({start_lon:.4f}°, {start_lat:.4f}°) → ({end_lon:.4f}°, {end_lat:.4f}°)   "
            f"L: {dist_str}   Min: {vmin:.1f} m   Max: {vmax:.1f} m   "
            f"Δ: {vmax-vmin:.1f} m   n={len(vals)}"
        )
        self._chart_2d.set_data(vals, distance_m)
        self._chart_3d.set_data(vals, distance_m)
        self.update()

    def set_cursor_fraction(self, frac: float) -> None:
        """Update the georeferenced cursor on both charts (0–1 along the profile)."""
        self._chart_2d.set_cursor_fraction(frac)
        self._chart_3d.set_cursor_fraction(frac)
