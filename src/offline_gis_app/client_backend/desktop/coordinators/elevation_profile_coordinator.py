"""Elevation profile tool coordinator.

Single responsibility: manage the two-click elevation profile workflow.
- Activates crosshair cursor
- Collects exactly 2 map clicks
- Calls the API to extract the profile
- Displays results in the panel
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from offline_gis_app.client_backend.desktop.controller import DesktopController


class ElevationProfileCoordinator:
    """Manages the elevation profile two-click workflow."""

    def __init__(self, controller: DesktopController) -> None:
        self._c = controller
        self._logger = logging.getLogger("desktop.elevation_profile")
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def activate(self) -> bool:
        """Start elevation profile mode. Returns True if activated."""
        asset = self._c._selected_asset()
        if not asset:
            self._c.panel.log("Select a DEM asset first, then click Elevation Profile.")
            return False
        if not self._c._is_dem_asset(asset):
            self._c.panel.log("Elevation Profile requires a DEM layer.")
            return False

        self._active = True
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
        """Cancel elevation profile mode."""
        self._active = False
        self._c._set_measurement_cursor_enabled(False)
        self._c._run_js_call("setPanMode", True)
        self._logger.info("Elevation profile mode deactivated")

    def on_map_click(self, lon: float, lat: float) -> bool:
        """Handle a map click. Returns True if the click was consumed."""
        if not self._active:
            return False

        self._c.state.clicked_points.append([lon, lat])
        n = len(self._c.state.clicked_points)

        if n == 1:
            self._c.panel.log(
                f"Start point set: ({lon:.6f}, {lat:.6f}). Now click END point."
            )
            return True

        if n >= 2:
            # Got both points — run the profile
            self._active = False
            self._c._set_measurement_cursor_enabled(False)
            self._c._run_js_call("setPanMode", True)
            self._run_profile()
            return True

        return False

    def _run_profile(self) -> None:
        """Execute the profile extraction with the two collected clicks."""
        import httpx

        asset = self._c._selected_asset()
        if not asset:
            self._c.panel.log("No DEM asset selected.")
            return

        samples = int(self._c._default_profile_samples)
        points = self._c.state.clicked_points[-2:]
        try:
            result = self._c.api.extract_profile(
                asset["file_path"], points, samples=samples
            )
        except httpx.HTTPError as exc:
            self._c.panel.log(f"Profile extraction failed: {exc}")
            self._logger.exception("Profile extraction failed path=%s", asset["file_path"])
            return

        values = result.get("values", [])
        if not values:
            self._c.panel.log("Profile extraction returned no values.")
            return

        self._c._last_profile_values = [float(v) for v in values]
        preview = ", ".join(f"{v:.2f}" for v in values[:8])
        self._c.panel.log(
            f"Elevation Profile: {len(values)} samples extracted.\n"
            f"Min: {min(values):.2f} m  Max: {max(values):.2f} m\n"
            f"First values: {preview}..."
        )
        self._logger.info(
            "Profile extracted samples=%s path=%s", len(values), asset["file_path"]
        )
