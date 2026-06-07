"""Settings dialog — rendering quality controls.

Exposes 4 parameters that directly affect perceived map quality and performance:
  1. Tile Sharpness (SSE)          — controls LOD precision of terrain/imagery tiles
  2. Render Resolution             — overall pixel density of the Cesium canvas
  3. Tile Cache Size               — how many tiles stay in GPU memory (pan smoothness)
  4. Simultaneous Tile Loading     — how quickly new tiles appear when navigating
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from src_new.clients.desktop_search.controller import DesktopController

logger = logging.getLogger("desktop.settings_dialog")

# ---------------------------------------------------------------------------
# Quality presets — maps "level" (0-3) to Cesium parameters
# ---------------------------------------------------------------------------
_PRESETS = {
    # level: (label, sse, resolution_scale, tile_cache, loading_descendants)
    0: ("Low",    4.0, 0.5,  200, 3),
    1: ("Medium", 2.0, 0.75, 400, 5),
    2: ("High",   1.0, 1.0,  800, 8),
    3: ("Ultra",  0.5, 1.0, 1200, 12),
}


class _QualitySliderRow(QWidget):
    """A single labelled slider row with left/right tick labels."""

    def __init__(
        self,
        title: str,
        tooltip: str,
        tick_labels: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._ticks = tick_labels
        n = len(tick_labels) - 1

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 6, 0, 6)
        outer.setSpacing(4)

        # Row title + tooltip
        title_lbl = QLabel(f"<b>{title}</b>")
        title_lbl.setToolTip(tooltip)
        outer.addWidget(title_lbl)

        # Slider
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(n)
        self.slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider.setTickInterval(1)
        self.slider.setPageStep(1)
        self.slider.setSingleStep(1)
        outer.addWidget(self.slider)

        # Tick labels row
        lbl_row = QHBoxLayout()
        lbl_row.setContentsMargins(0, 0, 0, 0)
        for t in tick_labels:
            lbl = QLabel(t)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("font-size: 10px; color: #555;")
            lbl_row.addWidget(lbl, stretch=1)
        outer.addLayout(lbl_row)

        # Current value label
        self.value_lbl = QLabel()
        self.value_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.value_lbl.setStyleSheet("font-size: 10px; color: #1f6fd2; font-weight: bold;")
        outer.addWidget(self.value_lbl)

        self._update_value_label(self.slider.value())
        self.slider.valueChanged.connect(self._update_value_label)

    # ------------------------------------------------------------------
    def _update_value_label(self, idx: int) -> None:
        lbl = self._ticks[max(0, min(idx, len(self._ticks) - 1))]
        self.value_lbl.setText(lbl)

    def value(self) -> int:
        return self.slider.value()

    def set_value(self, idx: int) -> None:
        self.slider.setValue(max(0, min(idx, self.slider.maximum())))


class SettingsDialog(QDialog):
    """Rendering quality settings dialog."""

    def __init__(self, parent: QWidget, controller: DesktopController) -> None:
        super().__init__(parent)
        self._controller = controller
        self._build_ui()
        self._load_current()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.setWindowTitle("Settings")
        self.setWindowFlags(
            self.windowFlags()
            & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self.setMinimumWidth(480)
        self.setMaximumWidth(560)

        main = QVBoxLayout(self)
        main.setContentsMargins(18, 16, 18, 12)
        main.setSpacing(10)

        # Header
        hdr = QLabel(
            "<b style='font-size:14px;'>Rendering Quality</b>"
            "<span style='font-size:11px; color:#666;'>"
            "  —  Adjust to match your machine's capability"
            "</span>"
        )
        hdr.setTextFormat(Qt.TextFormat.RichText)
        main.addWidget(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #d0d8e8;")
        main.addWidget(sep)

        # Group box
        grp = QGroupBox("Map Rendering Parameters")
        grp.setStyleSheet(
            "QGroupBox { font-weight: bold; border: 1px solid #c8d4e8;"
            " border-radius: 6px; margin-top: 8px; padding-top: 10px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px;"
            " padding: 0 4px; }"
        )
        grp_layout = QVBoxLayout(grp)
        grp_layout.setSpacing(2)
        main.addWidget(grp)

        # --- 1. Tile Sharpness (SSE) ---
        self._sse_row = _QualitySliderRow(
            "Tile Sharpness / Detail",
            "Controls how precisely terrain and imagery tiles are subdivided.\n"
            "Lower SSE = sharper tiles but higher GPU load.\n"
            "Ultra loads the finest tiles; Low uses coarser tiles for speed.",
            ["Low", "Medium", "High", "Ultra"],
        )
        grp_layout.addWidget(self._sse_row)

        grp_layout.addWidget(self._make_separator())

        # --- 2. Render Resolution ---
        self._res_row = _QualitySliderRow(
            "Render Resolution",
            "Overall pixel density of the 3D map canvas.\n"
            "Native (1.0×) is the sharpest; lower values reduce GPU load.\n"
            "Visible as overall crispness of the map.",
            ["50%  (Low)", "75%  (Medium)", "100%  (Native)", "100%  (Ultra)"],
        )
        grp_layout.addWidget(self._res_row)

        grp_layout.addWidget(self._make_separator())

        # --- 3. Tile Cache ---
        self._cache_row = _QualitySliderRow(
            "Tile Cache (Pan Smoothness)",
            "How many map tiles are kept in GPU memory.\n"
            "Larger cache = smoother panning as previously visited areas reload instantly.\n"
            "Reduce if the application uses too much RAM.",
            ["Low (200)", "Medium (400)", "High (800)", "Ultra (1200)"],
        )
        grp_layout.addWidget(self._cache_row)

        grp_layout.addWidget(self._make_separator())

        # --- 4. Tile Load Speed ---
        self._load_row = _QualitySliderRow(
            "Tile Load Speed",
            "How many tiles load simultaneously when navigating.\n"
            "Higher = tiles fill in faster; may cause momentary frame drops on slow machines.\n"
            "Lower = tiles appear more gradually but navigation stays smooth.",
            ["Low (3)", "Medium (5)", "High (8)", "Ultra (12)"],
        )
        grp_layout.addWidget(self._load_row)

        # Note
        note = QLabel(
            "<i style='font-size:10px;color:#888;'>"
            "Changes apply immediately to the live map view. "
            "Restart the application to reset to auto-detected defaults."
            "</i>"
        )
        note.setTextFormat(Qt.TextFormat.RichText)
        note.setWordWrap(True)
        main.addWidget(note)

        # Buttons
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Close,
        )
        apply_btn = btn_box.button(QDialogButtonBox.StandardButton.Apply)
        apply_btn.setText("Apply")
        apply_btn.setStyleSheet(
            "QPushButton { background:#1f6fd2; color:white; border-radius:4px;"
            " padding:5px 18px; font-weight:bold; }"
            "QPushButton:hover { background:#1558b0; }"
        )
        apply_btn.clicked.connect(self._apply)
        btn_box.rejected.connect(self.reject)
        main.addWidget(btn_box)

    # ------------------------------------------------------------------
    @staticmethod
    def _make_separator() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet("color: #eef0f5; margin: 4px 0;")
        return f

    # ------------------------------------------------------------------
    def _load_current(self) -> None:
        """Set sliders to the closest preset matching the current live values."""
        # Default to "High" if we can't detect
        level = 2
        try:
            from src_new.clients.desktop_search.controller import DesktopController  # noqa: F401
            # Try to read _userQualitySSE if it was set; fall back to GPU-detected
            stored = getattr(self._controller, "_quality_level", None)
            if stored is not None:
                level = int(stored)
        except Exception:
            pass
        self._sse_row.set_value(level)
        self._res_row.set_value(level)
        self._cache_row.set_value(level)
        self._load_row.set_value(level)

    # ------------------------------------------------------------------
    def _apply(self) -> None:
        """Read slider values and push quality settings to the JS bridge."""
        from qtpy.QtWidgets import QApplication as _QApp

        sse_level   = self._sse_row.value()
        res_level   = self._res_row.value()
        cache_level = self._cache_row.value()
        load_level  = self._load_row.value()

        sse        = _PRESETS[sse_level][1]
        res_scale  = _PRESETS[res_level][2]
        cache_size = _PRESETS[cache_level][3]
        desc_lim   = _PRESETS[load_level][4]

        # ── Show "Applying…" state on the button ──────────────────────────
        from qtpy.QtWidgets import QDialogButtonBox as _DBB
        apply_btn = self.sender()  # button that was clicked
        orig_text = None
        if apply_btn:
            orig_text = apply_btn.text()
            apply_btn.setText("⏳  Applying…")
            apply_btn.setEnabled(False)
        _QApp.processEvents()       # flush UI so the label updates immediately

        try:
            self._controller._run_js_call("setQualitySettings", {
                "sse": sse,
                "resolutionScale": res_scale,
                "tileCacheSize": cache_size,
                "loadingDescendantLimit": desc_lim,
            })

            # Remember the dominant level for next open
            self._controller._quality_level = sse_level

            logger.info(
                "Quality settings applied: sse=%.1f res=%.2f cache=%d desc=%d",
                sse, res_scale, cache_size, desc_lim,
            )
            self._controller.panel.log(
                f"Quality: {_PRESETS[sse_level][0]} — "
                f"SSE={sse}, res={res_scale}×, cache={cache_size}, load={desc_lim}"
            )
        finally:
            # ── Restore button after a short delay so the user sees feedback ──
            if apply_btn and orig_text is not None:
                from qtpy.QtCore import QTimer as _QTimer
                _QTimer.singleShot(700, lambda: (
                    apply_btn.setText("✓  Applied"),
                    apply_btn.setEnabled(True),
                    _QTimer.singleShot(1200, lambda: (
                        apply_btn.setText(orig_text),
                    ))
                ))

