from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
from PySide6.QtWidgets import QFileDialog
from PySide6.QtWebEngineWidgets import QWebEngineView

from offline_gis_app.desktop.api_client import DesktopApiClient
from offline_gis_app.desktop.bridge import WebBridge
from offline_gis_app.desktop.control_panel import ControlPanel
from offline_gis_app.desktop.state import DesktopState
from offline_gis_app.desktop.titiler_manager import TiTilerManager


class DesktopController:
    def __init__(
        self,
        panel: ControlPanel,
        web_view: QWebEngineView,
        bridge: WebBridge,
        api_client: DesktopApiClient | None = None,
        titiler_manager: TiTilerManager | None = None,
    ):
        self.panel = panel
        self.web_view = web_view
        self.bridge = bridge
        self.api = api_client or DesktopApiClient()
        self.titiler = titiler_manager or TiTilerManager()
        self.state = DesktopState()
        self._logger = logging.getLogger("desktop.controller")
        self._asset_cache: dict[str, dict] = {}
        self._connect_signals()
        self.refresh_assets()

    def _connect_signals(self) -> None:
        self.panel.browse_btn.clicked.connect(self.browse_path)
        self.panel.register_btn.clicked.connect(self.register_selected_path)
        self.panel.refresh_assets_btn.clicked.connect(self.refresh_assets)
        self.panel.add_layer_btn.clicked.connect(self.add_selected_layer)
        self.panel.fly_to_btn.clicked.connect(self.fly_to_selected_asset)
        self.panel.apply_visual_btn.clicked.connect(self.apply_visual_settings)
        self.panel.apply_dem_btn.clicked.connect(self.apply_dem_settings)
        self.panel.rotate_left_btn.clicked.connect(lambda: self.rotate_camera(-10.0))
        self.panel.rotate_right_btn.clicked.connect(lambda: self.rotate_camera(10.0))
        self.panel.pitch_slider.valueChanged.connect(self.set_pitch)
        self.panel.add_annotation_btn.clicked.connect(self.add_annotation)
        self.panel.extract_profile_btn.clicked.connect(self.extract_dem_profile)
        self.bridge.mapClicked.connect(self.on_map_click)
        self.bridge.measurementUpdated.connect(self.on_measurement)
        self.bridge.jsLogReceived.connect(self.on_js_log)

    def browse_path(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self.panel,
            "Select raster file",
            "",
            "Raster Files (*.tif *.tiff *.jp2 *.j2k *.mbtiles);;All Files (*)",
        )
        if not path:
            return
        self.panel.path_edit.setText(path)
        self.panel.log(f"Selected file: {path}")
        self._logger.info("Selected file path: %s", path)

    def register_selected_path(self) -> None:
        path = self.panel.path_edit.text().strip()
        if not path:
            self.panel.log("Select a file path first.")
            self._logger.warning("Register attempted without path")
            return
        if not Path(path).exists():
            self.panel.log(f"Path does not exist: {path}")
            self._logger.warning("Register path does not exist: %s", path)
            return
        try:
            asset = self.api.register_raster(path)
        except httpx.HTTPError as exc:
            self.panel.log(f"Register failed: {exc}")
            self._logger.exception("Register failed for path=%s", path)
            return
        self._asset_cache[asset["file_path"]] = asset
        self.state.selected_asset = asset
        self.panel.log(f"Registered: {asset['file_name']} ({asset['kind']})")
        self._logger.info("Registered asset id=%s name=%s kind=%s", asset["id"], asset["file_name"], asset["kind"])
        if not self.titiler.ensure_running():
            self.panel.log("Warning: TiTiler could not start. Layer may not draw.")
            self._logger.error("TiTiler unavailable after ensure_running")
        self.refresh_assets()
        bounds = self._asset_bounds(asset)
        options = self._layer_options(asset, bounds)
        self._add_layer(asset, options)
        self._fly_to_asset(asset)

    def refresh_assets(self) -> None:
        try:
            assets = self.api.list_assets()
        except httpx.HTTPError as exc:
            self.panel.log(f"Could not load catalog: {exc}")
            self._logger.exception("Catalog refresh failed")
            return
        self.panel.assets_combo.clear()
        missing_assets = 0
        for asset in assets:
            if not Path(asset["file_path"]).exists():
                missing_assets += 1
                self._logger.warning("Skipping missing catalog asset path=%s", asset["file_path"])
                continue
            self._asset_cache[asset["file_path"]] = asset
            label = f"{asset['file_name']} [{asset['kind']}]"
            self.panel.assets_combo.addItem(label, asset)
        shown = self.panel.assets_combo.count()
        self.panel.log(f"Catalog refreshed: {shown} assets")
        if missing_assets:
            self.panel.log(f"Skipped missing files from catalog: {missing_assets}")
        if self.state.selected_asset and not Path(self.state.selected_asset.get("file_path", "")).exists():
            self._logger.warning("Clearing stale selected asset path=%s", self.state.selected_asset.get("file_path"))
            self.state.selected_asset = None
        self._logger.info("Catalog refreshed visible=%s missing=%s total=%s", shown, missing_assets, len(assets))

    def _selected_asset(self) -> dict | None:
        item = self.panel.assets_combo.currentData()
        if isinstance(item, dict):
            if Path(item.get("file_path", "")).exists():
                return item
            self._logger.warning("Combo selected asset missing on disk path=%s", item.get("file_path"))
            return None
        if isinstance(self.state.selected_asset, dict):
            path = self.state.selected_asset.get("file_path", "")
            if Path(path).exists():
                return self.state.selected_asset
            self._logger.warning("Ignoring stale selected asset path=%s", path)
            self.state.selected_asset = None
        return None

    def add_selected_layer(self) -> None:
        asset = self._selected_asset()
        if not asset:
            self.panel.log("No selected asset.")
            self._logger.warning("Add layer requested with no selected asset")
            return
        if not Path(asset["file_path"]).exists():
            self.panel.log(f"File not found on disk: {asset['file_path']}")
            self._logger.error("Cannot add layer; file missing path=%s", asset["file_path"])
            return
        if not self.titiler.ensure_running():
            self.panel.log("Warning: TiTiler could not start. Layer may not draw.")
            self._logger.error("TiTiler unavailable before add layer")
        bounds = self._asset_bounds(asset)
        if bounds is None:
            try:
                fresh = self.api.register_raster(asset["file_path"])
                self._asset_cache[fresh["file_path"]] = fresh
                asset = fresh
                bounds = self._asset_bounds(asset)
                self._logger.info("Refreshed metadata for selected asset before layer add")
            except httpx.HTTPError:
                self._logger.exception("Failed to refresh metadata before layer add")
        options = self._layer_options(asset, bounds)
        self._add_layer(asset, options)
        self.panel.log(f"Layer added: {asset['file_name']}")
        self._logger.info("Layer add requested name=%s kind=%s url=%s", asset["file_name"], asset["kind"], asset["tile_url"])

    def fly_to_selected_asset(self) -> None:
        asset = self._selected_asset()
        if not asset:
            self.panel.log("No selected asset.")
            self._logger.warning("Fly-to requested with no selected asset")
            return
        if not self._fly_to_asset(asset):
            try:
                fresh = self.api.register_raster(asset["file_path"])
            except httpx.HTTPError as exc:
                self.panel.log(f"Fly-to failed: {exc}")
                self._logger.exception("Fly-to failed for %s", asset["file_path"])
                return
            self._asset_cache[fresh["file_path"]] = fresh
            asset = fresh
            self._fly_to_asset(asset)
        self.panel.log(f"Fly-to: {asset['file_name']}")
        self._logger.info("Fly-to requested for asset=%s", asset["file_name"])

    def apply_visual_settings(self) -> None:
        brightness = self.panel.brightness_slider.value() / 100.0
        contrast = self.panel.contrast_slider.value() / 100.0
        self._run_js_call("setImageryProperties", brightness, contrast)
        self.panel.log(f"Applied imagery settings brightness={brightness:.2f}, contrast={contrast:.2f}")
        self._logger.info("Applied imagery settings brightness=%.2f contrast=%.2f", brightness, contrast)

    def apply_dem_settings(self, _checked: bool | None = None, log_to_panel: bool = True) -> None:
        exaggeration = self.panel.dem_exaggeration_slider.value() / 100.0
        hillshade_strength = self.panel.dem_hillshade_slider.value() / 100.0
        azimuth = int(self.panel.dem_azimuth_slider.value())
        altitude = int(self.panel.dem_altitude_slider.value())
        self._run_js_call("setDemProperties", exaggeration, hillshade_strength, azimuth, altitude)
        if log_to_panel:
            self.panel.log(
                "Applied DEM settings "
                f"exaggeration={exaggeration:.2f}, hillshade={hillshade_strength:.2f}, "
                f"azimuth={azimuth}, altitude={altitude}"
            )
        self._logger.info(
            "Applied DEM settings exaggeration=%.2f hillshade=%.2f azimuth=%s altitude=%s",
            exaggeration,
            hillshade_strength,
            azimuth,
            altitude,
        )

    def rotate_camera(self, degrees: float) -> None:
        self._run_js_call("rotateCamera", degrees)
        self._logger.debug("Rotate camera degrees=%s", degrees)

    def set_pitch(self, degrees: int) -> None:
        self._run_js_call("setPitch", float(degrees))
        self._logger.debug("Set camera pitch degrees=%s", degrees)

    def on_map_click(self, lon: float, lat: float) -> None:
        self.state.clicked_points.append((lon, lat))
        self.state.clicked_points = self.state.clicked_points[-2:]
        self.panel.click_label.setText(f"Last click: lon={lon:.6f}, lat={lat:.6f}")
        self._logger.debug("Map click lon=%.6f lat=%.6f", lon, lat)

    def on_measurement(self, meters: float) -> None:
        self.panel.measure_label.setText(f"Last distance: {meters:.2f} m")
        self._logger.info("Measurement updated distance_m=%.2f", meters)

    def add_annotation(self) -> None:
        if not self.state.clicked_points:
            self.panel.log("Click on the globe first to place annotation.")
            self._logger.warning("Annotation requested without click")
            return
        text = self.panel.annotation_edit.text().strip()
        if not text:
            self.panel.log("Enter annotation text.")
            self._logger.warning("Annotation requested without text")
            return
        lon, lat = self.state.clicked_points[-1]
        self._run_js_call("addAnnotation", text, lon, lat)
        self.panel.log(f"Annotation added at {lon:.5f}, {lat:.5f}")
        self._logger.info("Annotation added lon=%.5f lat=%.5f text=%s", lon, lat, text)

    def extract_dem_profile(self) -> None:
        asset = self._selected_asset()
        if not asset:
            self.panel.log("Select a DEM asset first.")
            self._logger.warning("Profile requested without selected asset")
            return
        if len(self.state.clicked_points) < 2:
            self.panel.log("Click two points on the globe to define transect.")
            self._logger.warning("Profile requested without two clicks")
            return
        samples = int(self.panel.profile_samples.value())
        try:
            result = self.api.extract_profile(asset["file_path"], self.state.clicked_points[-2:], samples=samples)
        except httpx.HTTPError as exc:
            self.panel.log(f"Profile extraction failed: {exc}")
            self._logger.exception("Profile extraction failed path=%s", asset["file_path"])
            return
        values = result.get("values", [])
        if not values:
            self.panel.log("Profile extraction returned no values.")
            self._logger.warning("Profile returned empty values path=%s", asset["file_path"])
            return
        preview = ", ".join(f"{v:.2f}" for v in values[:10])
        self.panel.log(f"Profile extracted ({len(values)} samples). First values: {preview}")
        self._logger.info("Profile extracted samples=%s path=%s", len(values), asset["file_path"])

    def _run_js_call(self, method: str, *args) -> None:
        encoded = ", ".join(json.dumps(arg) for arg in args)
        script = f"window.offlineGIS && window.offlineGIS.{method}({encoded});"
        self._logger.debug("JS call: %s args=%s", method, args)
        self.web_view.page().runJavaScript(script)

    def _asset_centroid(self, asset: dict) -> dict[str, float] | None:
        cached = self._asset_cache.get(asset["file_path"])
        if cached and isinstance(cached.get("centroid"), dict):
            c = cached["centroid"]
            if self._is_valid_lon_lat(c.get("lon"), c.get("lat")):
                return c
        bounds_wkt = asset.get("bounds_wkt")
        if not bounds_wkt:
            return None
        from offline_gis_app.utils.geometry import parse_bounds_wkt_polygon

        bounds = parse_bounds_wkt_polygon(bounds_wkt)
        lon, lat = bounds.centroid()
        if not self._is_valid_lon_lat(lon, lat):
            return None
        return {"lon": lon, "lat": lat}

    def _asset_bounds(self, asset: dict) -> dict[str, float] | None:
        bounds_wkt = asset.get("bounds_wkt")
        if not bounds_wkt:
            return None
        from offline_gis_app.utils.geometry import parse_bounds_wkt_polygon

        b = parse_bounds_wkt_polygon(bounds_wkt)
        if not self._is_valid_lon_lat(b.min_x, b.min_y) or not self._is_valid_lon_lat(b.max_x, b.max_y):
            self._logger.warning(
                "Skipping invalid bounds for file=%s min=(%s,%s) max=(%s,%s)",
                asset.get("file_path"),
                b.min_x,
                b.min_y,
                b.max_x,
                b.max_y,
            )
            return None
        return {"west": b.min_x, "south": b.min_y, "east": b.max_x, "north": b.max_y}

    def _fly_to_asset(self, asset: dict) -> bool:
        bounds = self._asset_bounds(asset)
        if bounds is not None:
            self._run_js_call(
                "flyToBounds",
                bounds["west"],
                bounds["south"],
                bounds["east"],
                bounds["north"],
            )
            return True
        center = self._asset_centroid(asset)
        if center is None:
            c = asset.get("centroid", {})
            self._logger.error("No valid fly-to target for asset=%s centroid=%s", asset.get("file_name"), c)
            return False
        self._run_js_call("flyTo", center["lon"], center["lat"], 9000)
        return True

    def _layer_options(self, asset: dict, bounds: dict[str, float] | None) -> dict:
        options: dict = {"bounds": bounds, "is_dem": self._is_dem_asset(asset)}
        try:
            tilejson = self.api.get_tilejson(asset["file_path"])
        except httpx.HTTPError as exc:
            self._logger.warning("TileJSON unavailable for %s: %s", asset["file_name"], exc)
            return options

        minzoom = tilejson.get("minzoom")
        maxzoom = tilejson.get("maxzoom")
        if isinstance(minzoom, int):
            options["minzoom"] = minzoom
        if isinstance(maxzoom, int):
            options["maxzoom"] = maxzoom

        # TileJSON bounds: [west, south, east, north] in EPSG:4326
        b = tilejson.get("bounds")
        if isinstance(b, list) and len(b) == 4:
            w, s, e, n = b
            if self._is_valid_lon_lat(w, s) and self._is_valid_lon_lat(e, n):
                options["bounds"] = {"west": float(w), "south": float(s), "east": float(e), "north": float(n)}

        raster_query = self._raster_render_query(asset)
        if raster_query:
            options["query"] = raster_query
        self._logger.info("Layer options for %s: %s", asset["file_name"], options)
        return options

    def _add_layer(self, asset: dict, options: dict) -> None:
        is_dem = bool(options.get("is_dem"))
        if is_dem:
            self._run_js_call("addDemLayer", asset["file_name"], asset["tile_url"], options)
            if not self._dem_settings_are_default():
                self.apply_dem_settings(log_to_panel=False)
            self._logger.info("DEM terrain layer requested name=%s", asset["file_name"])
            return
        self._run_js_call("addTileLayer", asset["file_name"], asset["tile_url"], asset["kind"], options)

    def _dem_settings_are_default(self) -> bool:
        return (
            int(self.panel.dem_exaggeration_slider.value()) == 150
            and int(self.panel.dem_hillshade_slider.value()) == 75
            and int(self.panel.dem_azimuth_slider.value()) == 45
            and int(self.panel.dem_altitude_slider.value()) == 45
        )

    def _is_dem_asset(self, asset: dict) -> bool:
        kind = str(asset.get("kind", "")).lower()
        file_name = str(asset.get("file_name", "")).lower()
        if kind == "dem" or "dem" in file_name:
            return True
        try:
            info = self.api.get_cog_info(asset["file_path"])
        except (httpx.HTTPError, KeyError, TypeError):
            return False
        try:
            return int(info.get("count", 0) or 0) == 1
        except (TypeError, ValueError):
            return False

    def _raster_render_query(self, asset: dict) -> dict[str, object]:
        try:
            info = self.api.get_cog_info(asset["file_path"])
        except httpx.HTTPError:
            return {}
        band_count = int(info.get("count", 1) or 1)
        is_dem = str(asset.get("kind", "")).lower() == "dem" or "dem" in str(asset.get("file_name", "")).lower()
        query: dict[str, object] = {}

        # Always constrain multi-band non-DEM rasters to RGB to avoid TiTiler PNG encoding failures.
        if band_count >= 3 and not is_dem:
            query["bidx"] = [1, 2, 3]

        try:
            stats = self.api.get_cog_statistics(asset["file_path"])
        except httpx.HTTPError as exc:
            self._logger.warning("Statistics unavailable for %s: %s", asset["file_name"], exc)
            return query

        if not isinstance(stats, dict) or not stats:
            return query

        if band_count >= 3 and not is_dem:
            lows = []
            highs = []
            for i in range(1, min(3, band_count) + 1):
                stat = stats.get(f"b{i}")
                if not isinstance(stat, dict):
                    continue
                low = stat.get("percentile_2", stat.get("min"))
                high = stat.get("percentile_98", stat.get("max"))
                if low is None or high is None:
                    continue
                lows.append(float(low))
                highs.append(float(high))
            if len(lows) == 3 and max(highs) > min(lows):
                query["rescale"] = f"{min(lows)},{max(highs)}"
            return query

        first_band = stats.get("b1") if isinstance(stats.get("b1"), dict) else next(iter(stats.values()))
        if not isinstance(first_band, dict):
            return {}
        low = first_band.get("percentile_2", first_band.get("min"))
        high = first_band.get("percentile_98", first_band.get("max"))
        if low is None or high is None or float(high) <= float(low):
            return query
        if is_dem:
            return {"rescale": f"{float(low)},{float(high)}", "colormap_name": "terrain"}
        return {"rescale": f"{float(low)},{float(high)}"}

    @staticmethod
    def _is_valid_lon_lat(lon, lat) -> bool:
        if lon is None or lat is None:
            return False
        try:
            lon_v = float(lon)
            lat_v = float(lat)
        except (TypeError, ValueError):
            return False
        return -180.0 <= lon_v <= 180.0 and -90.0 <= lat_v <= 90.0

    def on_js_log(self, level: str, message: str) -> None:
        normalized = level.lower().strip()
        if "Tile provider error for" in message:
            self._logger.warning("JS: %s", message)
            return
        if normalized == "debug":
            self._logger.debug("JS: %s", message)
            return
        if normalized in {"warn", "warning"}:
            self._logger.warning("JS: %s", message)
            return
        if normalized == "error":
            self._logger.error("JS: %s", message)
            return
        self._logger.info("JS: %s", message)
