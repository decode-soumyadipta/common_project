"""Utility coordinator for helper methods and validation functions."""

from __future__ import annotations

import ipaddress
import logging
import math
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from src_new.clients.desktop_search.controller import DesktopController


class UtilityCoordinator:
    """Handles utility functions for validation, path normalization, and coordinate operations."""

    def __init__(self, controller: DesktopController):
        self._controller = controller
        self._logger = logging.getLogger("client_desktop.utility_coordinator")

    @staticmethod
    def is_valid_lon_lat(lon, lat) -> bool:
        """Validate longitude and latitude values."""
        if lon is None or lat is None:
            return False
        try:
            lon_v = float(lon)
            lat_v = float(lat)
        except (TypeError, ValueError):
            return False
        return -180.0 <= lon_v <= 180.0 and -90.0 <= lat_v <= 90.0

    @staticmethod
    def is_near_global_bounds(bounds: dict[str, float] | None) -> bool:
        """Check if bounds are near-global extent."""
        if not isinstance(bounds, dict):
            return False
        try:
            west = float(bounds.get("west"))
            south = float(bounds.get("south"))
            east = float(bounds.get("east"))
            north = float(bounds.get("north"))
        except (TypeError, ValueError):
            return False
        return west <= -179.5 and east >= 179.5 and south <= -84.5 and north >= 84.5

    @staticmethod
    def normalize_path_for_compare(path: str) -> str:
        """Normalize path for comparison."""
        if not path:
            return ""
        try:
            normalized = str(Path(path).expanduser().resolve(strict=False))
        except Exception:
            normalized = str(path)
        return normalized.replace("\\", "/").casefold()

    def paths_equivalent(self, path_a: str, path_b: str) -> bool:
        """Check if two paths are equivalent."""
        return self.normalize_path_for_compare(
            path_a
        ) == self.normalize_path_for_compare(path_b)

    def asset_path_accessible_locally(self, asset: dict) -> bool:
        """Check if asset file path is accessible locally."""
        path = str(asset.get("file_path") or "")
        if not path:
            return False
        return Path(path).exists()

    def validate_offline_endpoints(self) -> bool:
        """Validate that API and TiTiler endpoints are offline-safe."""
        c = self._controller
        api_ok = self.is_offline_safe_url(c.api.base_url)
        titiler_ok = self.is_offline_safe_url(c.api.titiler_base_url)
        if api_ok and titiler_ok:
            return True

        c.panel.log(
            "Offline guard: API/TiTiler endpoints must be local or private-network addresses."
        )
        if not api_ok:
            c.panel.log(f"Blocked API endpoint: {c.api.base_url}")
        if not titiler_ok:
            c.panel.log(f"Blocked TiTiler endpoint: {c.api.titiler_base_url}")
        self._logger.error(
            "Offline endpoint validation failed api=%s titiler=%s",
            c.api.base_url,
            c.api.titiler_base_url,
        )
        return False

    def require_offline_endpoints(self, action: str) -> bool:
        """Check if offline endpoints are valid before allowing action."""
        c = self._controller
        if c._offline_endpoints_valid:
            return True
        c.panel.log(
            f"{action} blocked by offline guard. Configure local/private API and TiTiler endpoints."
        )
        self._logger.warning("Blocked action by offline guard: %s", action)
        return False

    @staticmethod
    def is_offline_safe_url(url: str) -> bool:
        """Check if URL is safe for offline use (localhost or private network)."""
        try:
            parsed = urlparse(url)
        except ValueError:
            return False

        if parsed.scheme == "file":
            return True
        if parsed.scheme not in {"http", "https"}:
            return False

        host = (parsed.hostname or "").lower()
        if not host:
            return False
        if host in {"localhost", "127.0.0.1", "::1"}:
            return True

        try:
            ip = ipaddress.ip_address(host)
            return ip.is_private or ip.is_loopback or ip.is_link_local
        except ValueError:
            pass

        # Allow .local mDNS hostnames
        return bool(host.endswith(".local"))

    def set_layer_loading(self, active: bool, message: str) -> None:
        """Set layer loading state and update UI."""
        c = self._controller
        c._layer_loading_active = active
        if active:
            c._layer_loading_timeout_timer.start(c._layer_loading_timeout_ms)
        else:
            c._layer_loading_timeout_timer.stop()
            c._layer_loading_timeout_ms = 30000
        c.panel.set_layer_loading(active, message)
        from qtpy.QtWidgets import QApplication
        QApplication.processEvents()

    def on_layer_loading_timeout(self) -> None:
        """Handle layer loading timeout."""
        c = self._controller
        if not c._layer_loading_active:
            return
        self._logger.warning(
            "Layer loading timeout after %sms", c._layer_loading_timeout_ms
        )
        self.set_layer_loading(False, "Layer load timeout")
        c.panel.log(
            "Layer load timed out. Check API/TiTiler availability and source raster path."
        )

    def asset_centroid(self, asset: dict) -> dict[str, float] | None:
        """Calculate asset centroid from bounds."""
        bounds = self.asset_bounds(asset)
        if not bounds:
            return None
        try:
            lon = (float(bounds["west"]) + float(bounds["east"])) / 2.0
            lat = (float(bounds["south"]) + float(bounds["north"])) / 2.0
            return {"lon": lon, "lat": lat}
        except (KeyError, TypeError, ValueError):
            return None

    def asset_bounds(self, asset: dict) -> dict[str, float] | None:
        """Extract bounds from asset metadata."""
        if not isinstance(asset, dict):
            return None
        bounds = asset.get("bounds")
        if bounds is None:
            bounds = asset.get("bbox")
        if isinstance(bounds, dict):
            try:
                return {
                    "west": float(bounds["west"]),
                    "south": float(bounds["south"]),
                    "east": float(bounds["east"]),
                    "north": float(bounds["north"]),
                }
            except (KeyError, TypeError, ValueError):
                pass
        if isinstance(bounds, (list, tuple)) and len(bounds) >= 4:
            try:
                west, south, east, north = map(float, bounds[:4])
                return {
                    "west": west,
                    "south": south,
                    "east": east,
                    "north": north,
                }
            except (TypeError, ValueError):
                pass
        try:
            return {
                "west": float(asset["min_lon"]),
                "south": float(asset["min_lat"]),
                "east": float(asset["max_lon"]),
                "north": float(asset["max_lat"]),
            }
        except (KeyError, TypeError, ValueError):
            pass

        file_path = str(asset.get("file_path") or "").strip()
        if not file_path:
            return None

        try:
            # First attempt: use existing metadata extraction via format handler for point clouds
            ext = Path(file_path).suffix.lower()
            if ext in {".las", ".laz"}:
                from src_new.services.ingestion.format_handlers.las_handler import extract_metadata as las_extract_metadata
                raw_meta = las_extract_metadata(Path(file_path))
                if raw_meta:
                    computed_bounds = {
                        "west": float(raw_meta["bounds"]["min_lon"]),
                        "south": float(raw_meta["bounds"]["min_lat"]),
                        "east": float(raw_meta["bounds"]["max_lon"]),
                        "north": float(raw_meta["bounds"]["max_lat"]),
                    }
                    asset.setdefault("bounds", computed_bounds)
                    return computed_bounds
            # Fallback to GDAL for other raster formats
            from src_new.services.ingestion.gdal_pipelines.metadata_extractor import (
                extract_metadata,
            )
            metadata = extract_metadata(Path(file_path))
            bbox = getattr(metadata, "bbox", None) or getattr(metadata, "bounds", None)
            if bbox is None:
                return None
            computed_bounds = {
                "west": float(getattr(bbox, "min_lon", getattr(bbox, "left", 0.0))),
                "south": float(getattr(bbox, "min_lat", getattr(bbox, "bottom", 0.0))),
                "east": float(getattr(bbox, "max_lon", getattr(bbox, "right", 0.0))),
                "north": float(getattr(bbox, "max_lat", getattr(bbox, "top", 0.0))),
            }
            asset.setdefault("bounds", computed_bounds)
            to_wkt_polygon = getattr(bbox, "to_wkt_polygon", None)
            if callable(to_wkt_polygon):
                asset.setdefault("bounds_wkt", to_wkt_polygon())
            if not asset.get("crs") and getattr(metadata, "crs", None):
                asset["crs"] = metadata.crs
            return computed_bounds
        except Exception as exc:
            self._logger.info(
                "Unable to derive bounds from file metadata for %s: %s",
                file_path,
                exc,
            )
            return None

    @staticmethod
    def utm_epsg_for_lon_lat(lon: float, lat: float) -> int:
        """Calculate UTM EPSG code for given coordinates."""
        zone = int((lon + 180) / 6) + 1
        if lat >= 0:
            return 32600 + zone
        return 32700 + zone

    @staticmethod
    def line_length_m(coords: list[list[float]]) -> float:
        """Calculate line length in meters from coordinates."""
        if len(coords) < 2:
            return 0.0
        total = 0.0
        for i in range(len(coords) - 1):
            lon1, lat1 = coords[i][0], coords[i][1]
            lon2, lat2 = coords[i + 1][0], coords[i + 1][1]
            # Haversine formula
            R = 6371000  # Earth radius in meters
            phi1 = math.radians(lat1)
            phi2 = math.radians(lat2)
            delta_phi = math.radians(lat2 - lat1)
            delta_lambda = math.radians(lon2 - lon1)
            a = (
                math.sin(delta_phi / 2) ** 2
                + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
            )
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            total += R * c
        return total

    def is_dem_asset(self, asset: dict) -> bool:
        """Detect if asset is DEM or RGB imagery using robust band count + data type analysis.

        CRITICAL: Single-band imagery (like JP2 aerials) must NOT be detected as DEM.
        DEM detection requires BOTH single-band AND elevation-like data type/range.
        """
        c = self._controller
        file_path = str(asset.get("file_path") or "")
        if file_path and file_path in c._dem_asset_kind_cache:
            return c._dem_asset_kind_cache[file_path]

        # Step 1: Check explicit kind or filename hints
        kind = str(asset.get("kind", "")).lower()
        file_name = str(asset.get("file_name", "")).lower()

        # Explicit DEM markers (dem, dtm, elevation)
        if any(marker in file_name for marker in ("dem", "dtm", "elevation")) or kind in ("dem", "elevation"):
            if file_path:
                c._dem_asset_kind_cache[file_path] = True
            return True

        # Explicit imagery markers (JP2, RGB, etc.) - NOT DEM
        imagery_extensions = (".jp2", ".j2k", ".jpeg", ".jpg", ".png", ".tif", ".tiff")
        imagery_keywords = ("rgb", "aerial", "ortho", "satellite", "imagery", "photo", "aot", "tci", "wvp", "scl")

        if any(file_name.endswith(ext) for ext in imagery_extensions):
            # Check if filename contains imagery keywords
            if any(keyword in file_name for keyword in imagery_keywords):
                if file_path:
                    c._dem_asset_kind_cache[file_path] = False
                return False

        # Step 2: Analyze raster metadata (band count + data type)
        try:
            info = c.api.get_cog_info(asset["file_path"])
        except Exception:
            if file_path:
                c._dem_asset_kind_cache[file_path] = False
            return False

        try:
            band_count = int(info.get("count", 0) or 0)
            dtype = str(info.get("dtype", "")).lower()

            # Multi-band = RGB imagery (NOT DEM)
            if band_count >= 3:
                if file_path:
                    c._dem_asset_kind_cache[file_path] = False
                return False

            # Single-band: Check data type to distinguish DEM from grayscale imagery DEM typically uses float32/float64 or int16/int32 for elevation values Grayscale imagery typically uses uint8/uint16 for pixel values
            if band_count == 1:
                # Float types = likely DEM (elevation values)
                if "float" in dtype:
                    if file_path:
                        c._dem_asset_kind_cache[file_path] = True
                    return True

                # Signed integer types = likely DEM (elevation can be negative)
                if "int16" in dtype or "int32" in dtype:
                    if file_path:
                        c._dem_asset_kind_cache[file_path] = True
                    return True

                # Unsigned integer types = likely grayscale imagery (NOT DEM)
                if "uint" in dtype:
                    if file_path:
                        c._dem_asset_kind_cache[file_path] = False
                    return False

            # Default: single-band with unknown dtype = assume imagery (safer default)
            if file_path:
                c._dem_asset_kind_cache[file_path] = False
            return False

        except (TypeError, ValueError):
            if file_path:
                c._dem_asset_kind_cache[file_path] = False
            return False

# TODO: Refactor for cognitive complexity
# TODO: Refactor for cognitive complexity
    def dem_bounds_polygon(self, dem_path: str) -> list[tuple[float, float]] | None:
        """Return a bounding-box polygon for the active DEM asset, or None."""
        c = self._controller
        # Try to get bounds from the asset cache
        for _path, asset in c._asset_cache.items():
            if str(asset.get("file_path") or "") == dem_path and self.is_dem_asset(
                asset
            ):
                bounds = self.asset_bounds(asset)
                if bounds:
                    w, s, e, n = (
                        bounds["west"],
                        bounds["south"],
                        bounds["east"],
                        bounds["north"],
                    )
                    return [(w, s), (e, s), (e, n), (w, n), (w, s)]
        for _path, asset in c._search_result_assets_by_path.items():
            if str(asset.get("file_path") or "") == dem_path and self.is_dem_asset(
                asset
            ):
                bounds = self.asset_bounds(asset)
                if bounds:
                    w, s, e, n = (
                        bounds["west"],
                        bounds["south"],
                        bounds["east"],
                        bounds["north"],
                    )
                    return [(w, s), (e, s), (e, n), (w, n), (w, s)]
        # Fallback: read bounds directly from the raster file
        try:
            import rasterio
            from pyproj import Transformer as _T

            with rasterio.open(dem_path) as src:
                b = src.bounds
                crs = src.crs
                if crs and not crs.is_geographic:
                    t = _T.from_crs(crs, "EPSG:4326", always_xy=True)
                    w, s = t.transform(b.left, b.bottom)
                    e, n = t.transform(b.right, b.top)
                else:
                    w, s, e, n = b.left, b.bottom, b.right, b.top
            return [(w, s), (e, s), (e, n), (w, n), (w, s)]
        except Exception:
            return None
