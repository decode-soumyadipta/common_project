from __future__ import annotations

import logging
import math


class CameraCoordinator:
    """Encapsulate camera and view control operations for desktop controller."""

    def __init__(self, controller):
        self._controller = controller
        self._logger = logging.getLogger("client_desktop.camera_coordinator")

    def flyto_asset_bounds(self, asset: dict, kind: str) -> None:
        """Smooth camera flyto for the asset bounds with smart 2D/3D rendering."""
        c = self._controller
        try:
            # Get asset bounds
            bounds = asset.get("bounds")
            if not bounds or len(bounds) != 4:
                c.panel.log("Asset bounds not available for flyto")
                return

            west, south, east, north = bounds

            # Calculate center and appropriate camera height
            center_lon = (west + east) / 2
            center_lat = (south + north) / 2

            # Calculate diagonal distance for camera height
            lat_diff = north - south
            lon_diff = east - west
            diagonal = math.sqrt(lat_diff**2 + lon_diff**2)

            # Camera height based on asset size (in degrees to meters approximation) 1 degree ≈ 111km, we want to see the whole asset
            camera_height = diagonal * 111000 * 1.5  # 1.5x for padding
            camera_height = max(
                1000, min(camera_height, 50000000)
            )  # Clamp between 1km and 50,000km

            # Determine rendering mode based on asset type
            is_dem = kind in ["DEM", "ELEVATION"]

            # Smart camera positioning
            if is_dem:
                # For DEM: 3D view with tilt for terrain visualization
                pitch_degrees = -45  # Look down at 45 degrees
                heading_degrees = 0
                c.panel.log(f"Flying to DEM (3D view): {asset.get('file_name')}")
            else:
                # For imagery: 2D top-down view
                pitch_degrees = -90  # Straight down
                heading_degrees = 0
                c.panel.log(f"Flying to imagery (2D view): {asset.get('file_name')}")

            # Execute smooth flyto
            c._run_js_call(
                "flyToLocation",
                {
                    "longitude": center_lon,
                    "latitude": center_lat,
                    "height": camera_height,
                    "heading": heading_degrees,
                    "pitch": pitch_degrees,
                    "roll": 0,
                    "duration": 2.0,  # 2 second smooth animation
                },
            )

            c._logger.info(
                "Camera flyto: lon=%.4f lat=%.4f height=%.0f pitch=%d (mode=%s)",
                center_lon,
                center_lat,
                camera_height,
                pitch_degrees,
                "3D" if is_dem else "2D",
            )

        except Exception as e:
            c._logger.error("Flyto failed: %s", e, exc_info=True)
            c.panel.log(f"Camera movement failed: {e}")

    def fly_through_asset(self, asset: dict) -> bool:
        """Fly through an asset's bounds with smooth animation."""
        c = self._controller
        bounds = c._asset_bounds(asset)
        if bounds is None:
            center = c._asset_centroid(asset)
            if center is None:
                c._logger.warning(
                    "Fly-through unavailable for asset=%s", asset.get("file_name")
                )
                return False
            # Fallback micro-bounds around centroid when exact bounds are unavailable.
            delta = 0.01
            bounds = {
                "west": center["lon"] - delta,
                "south": center["lat"] - delta,
                "east": center["lon"] + delta,
                "north": center["lat"] + delta,
            }

        c._run_js_call(
            "flyThroughBounds",
            bounds["west"],
            bounds["south"],
            bounds["east"],
            bounds["north"],
        )
        return True

    def rotate_camera(self, degrees: float) -> None:
        """Rotate the camera by the specified degrees."""
        c = self._controller
        c._run_js_call("rotateCamera", float(degrees))
        c.panel.log(f"Camera rotated {degrees}°")

    def set_pitch(self, value: int) -> None:
        """Set camera pitch from slider value."""
        c = self._controller
        # Convert slider value (0-90) to pitch degrees (-90 to 0)
        pitch_degrees = -float(value)
        c._run_js_call("setCameraPitch", pitch_degrees)
