"""Elevation profile tool coordinator.

Single responsibility: manage the two-click elevation profile workflow.
- Activates crosshair cursor
- Collects exactly 2 map clicks
- Calls the API to extract the profile
- Displays results in the ElevationProfilePanel Qt widget
"""
from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from desktop_client.client_backend.desktop.controller import DesktopController


class ElevationProfileCoordinator:
    """Manages the elevation profile two-click workflow."""

    def __init__(self, controller: DesktopController) -> None:
        self._c = controller
        self._logger = logging.getLogger("desktop.elevation_profile")
        self._active = False
        self._clicks: list[list[float]] = []
        self._panel = None   # set externally via set_panel()
        self.on_complete = None  # optional callback: called when profile finishes or is cancelled

    def set_panel(self, panel) -> None:
        """Inject the embedded ElevationProfilePanel from the main window."""
        self._panel = panel

    @property
    def active(self) -> bool:
        return self._active

    def activate(self) -> bool:
        """Start elevation profile mode. Returns True if activated."""
        dem_path = self._c._selected_dem_path()
        if not dem_path:
            self._c.panel.log("Select or show a DEM layer first, then click Elevation Profile.")
            return False

        self._active = True
        self._clicks = []
        self._c.state.clicked_points.clear()
        # Enable crosshair cursor and disable pan
        self._c._run_js_call("setPanMode", False)
        self._c._set_measurement_cursor_enabled(True)
        self._c.panel.log(
            "Elevation Profile: click START point on the DEM, then END point."
        )
        self._logger.info("Elevation profile mode activated")
        return True

    def deactivate(self) -> None:
        """Cancel/stop elevation profile mode and clear all map overlays."""
        self._active = False
        self._clicks = []
        self._c._set_measurement_cursor_enabled(False)
        self._c._run_js_call("clearProfilePreview")
        self._c._run_js_call("clearProfileLine")
        self._c._run_js_call("setPanMode", True)
        self._logger.info("Elevation profile mode deactivated")
        # Hide the Qt panel and collapse the splitter
        if self._panel is not None and self._panel.isVisible():
            self._panel.hide()
            main_win = self._c.web_view.window()
            v_splitter = getattr(main_win, "_map_v_splitter", None)
            if v_splitter is not None:
                total = v_splitter.height()
                v_splitter.setSizes([total, 0])
        if callable(self.on_complete):
            self.on_complete()

    def on_map_click(self, lon: float, lat: float) -> bool:
        """Handle a map click. Returns True if the click was consumed."""
        if not self._active:
            return False

        self._clicks.append([lon, lat])
        n = len(self._clicks)

        if n == 1:
            self._c.panel.log(
                f"Start point: ({lon:.6f}, {lat:.6f}) — click END point."
            )
            # Draw a preview marker on the globe for the start point
            self._c._run_js_call("drawProfileStartMarker", lon, lat)
            return True

        if n >= 2:
            # Got both points — clear preview, run the profile
            self._c._set_measurement_cursor_enabled(False)
            self._c._run_js_call("clearProfilePreview")
            self._c._run_js_call("setPanMode", True)
            self._run_profile()
            # Re-arm: reset clicks so the next map click starts a fresh line.
            # The previous profile line on the globe is cleared when drawProfileLine
            # is called for the new line (it clears all previous entities first).
            self._clicks = []
            self._active = True
            self._c._run_js_call("setPanMode", False)
            self._c._set_measurement_cursor_enabled(True)
            self._c.panel.log(
                "Profile complete. Click a new START point to draw another line, "
                "or click the toolbar button to stop."
            )
            return True

        return False

    def _geodesic_distance_m(
        self, lon1: float, lat1: float, lon2: float, lat2: float
    ) -> float:
        """Compute geodesic distance in metres between two WGS-84 points."""
        try:
            from pyproj import Geod
            geod = Geod(ellps="WGS84")
            _, _, dist = geod.inv(lon1, lat1, lon2, lat2)
            return float(dist)
        except Exception:
            # Haversine fallback
            R = 6_371_000.0
            phi1, phi2 = math.radians(lat1), math.radians(lat2)
            dphi = math.radians(lat2 - lat1)
            dlam = math.radians(lon2 - lon1)
            a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
            return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def _run_profile(self) -> None:
        """Execute the profile extraction with the two collected clicks."""
        import httpx

        dem_path = self._c._selected_dem_path()
        if not dem_path:
            self._c.panel.log("No DEM asset selected.")
            return

        samples = int(self._c._default_profile_samples)
        points = self._clicks[-2:]
        (lon1, lat1), (lon2, lat2) = points[0], points[1]

        try:
            result = self._c.api.extract_profile(
                dem_path, points, samples=samples
            )
        except httpx.HTTPError as exc:
            self._c.panel.log(f"Profile extraction failed: {exc}")
            self._logger.exception("Profile extraction failed path=%s", dem_path)
            return

        values = result.get("values", [])
        if not values:
            self._c.panel.log("Profile extraction returned no values.")
            return

        self._c._last_profile_values = [float(v) for v in values]
        distance_m = self._geodesic_distance_m(lon1, lat1, lon2, lat2)

        # Draw the profile line on the Cesium globe (clears any previous line)
        self._c._run_js_call(
            "drawProfileLine", lon1, lat1, lon2, lat2
        )

        # Show/update the Qt profile panel
        self._show_panel(values, distance_m, lon1, lat1, lon2, lat2)

        vmin = min(self._c._last_profile_values)
        vmax = max(self._c._last_profile_values)
        self._c.panel.log(
            f"Elevation Profile: {len(values)} samples  "
            f"Min: {vmin:.1f} m  Max: {vmax:.1f} m  "
            f"Length: {distance_m/1000:.2f} km"
        )
        self._logger.info(
            "Profile extracted samples=%s path=%s dist_m=%.1f",
            len(values), dem_path, distance_m,
        )

    def _show_panel(
        self,
        values: list,
        distance_m: float,
        lon1: float, lat1: float,
        lon2: float, lat2: float,
    ) -> None:
        """Populate the embedded panel and expand the splitter to show it."""
        if self._panel is None:
            self._logger.warning("No elevation profile panel set — skipping display")
            return

        self._panel.set_profile(values, distance_m, lon1, lat1, lon2, lat2)

        # Show the panel and resize the vertical splitter
        if not self._panel.isVisible():
            self._panel.show()
            # Find the map-column vertical splitter and give the profile panel ~260px
            main_win = self._c.web_view.window()
            v_splitter = getattr(main_win, "_map_v_splitter", None)
            if v_splitter is not None:
                total = v_splitter.height()
                profile_h = 260
                map_h = max(total - profile_h, 200)
                v_splitter.setSizes([map_h, profile_h])
