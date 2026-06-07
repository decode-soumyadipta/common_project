from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path

import httpx
from qtpy.QtCore import QTimer, Qt
from qtpy.QtWidgets import QFileDialog

from src_new.clients.desktop_search.app_mode import DesktopAppMode


class AssetCoordinator:
    """Encapsulate asset catalog management operations for desktop controller."""

    def __init__(self, controller):
        self._controller = controller
        self._logger = logging.getLogger("client_desktop.asset_coordinator")

    def browse_files(self) -> None:
        """Browse and select multiple raster files based on selected format."""
        c = self._controller

        # Get selected format from dropdown
        format_index = c.panel.format_combo.currentIndex()

        # Define file filters based on format
        if format_index == 0:  # GeoTIFF
            file_filter = (
                "GeoTIFF and world files (*.tif *.tiff *.tfw *.tifw);;All Files (*)"
            )
            dialog_title = "Select GeoTIFF files and optional .tfw world files"
        elif format_index == 1:  # JPEG2000 + PRJ
            # Include world files (.j2w, .jgw) in the filter
            file_filter = "JPEG2000 and auxiliary files (*.jp2 *.j2k *.prj *.j2w *.jgw);;All Files (*)"
            dialog_title = "Select JPEG2000 files and their .prj/.j2w files"
        elif format_index == 2:  # MBTiles
            file_filter = "MBTiles (*.mbtiles);;All Files (*)"
            dialog_title = "Select MBTiles files"
        else:
            file_filter = (
                "Raster Files (*.tif *.tiff *.jp2 *.j2k *.mbtiles);;All Files (*)"
            )
            dialog_title = "Select raster files"

        files, _ = QFileDialog.getOpenFileNames(
            c.panel, dialog_title, "", file_filter
        )

        if files:
            c.panel.add_selected_files(files)

            # Count valid files after validation
            valid_count = c.panel.selected_files_list.count()

            if valid_count > 0:
                c.panel.log(f"Selected {valid_count} valid file(s) for ingestion")

                # Log file details (first 5)
                for i in range(min(5, valid_count)):
                    item = c.panel.selected_files_list.item(i)
                    if item:
                        c.panel.log(f"  - {item.text()}")

                if valid_count > 5:
                    c.panel.log(f"  ... and {valid_count - 5} more files")
            else:
                c.panel.log("No valid files selected after validation")

    def clear_file_selection(self) -> None:
        """Clear the current file selection."""
        c = self._controller
        c.panel.clear_selected_files()
        c.panel.log("File selection cleared")

    def enqueue_selected_files(self) -> None:
        """Enqueue the selected files for ingestion."""
        c = self._controller
        if not c._require_offline_endpoints("Ingest files"):
            return
        if not c.api.api_ready():
            c.panel.log(
                f"API unavailable at {c.api.base_url}. Start API/server desktop, then retry 'Ingest files'."
            )
            return

        selected_files = c.panel.get_selected_files()
        if not selected_files:
            c.panel.log(
                "No files selected. Use 'Select Files' or 'Select Folder' first."
            )
            return

        # Validate files exist
        valid_files = []
        for file_path in selected_files:
            path_obj = Path(file_path)
            if not path_obj.exists():
                c.panel.log(f"File not found: {path_obj.name}")
                continue
            if not path_obj.is_file():
                c.panel.log(f"Not a file: {path_obj.name}")
                continue
            valid_files.append(file_path)

        if not valid_files:
            c.panel.log("No valid files to ingest")
            return

        try:
            c.panel.log(f"Starting ingestion of {len(valid_files)} file(s)...")
            # Set progress bar to 0% initially (not infinite loading)
            c.panel.ingest_progress_bar.setRange(0, 100)
            c.panel.ingest_progress_bar.setValue(0)
            c.panel.ingest_status_value.setText("QUEUING")
            c.panel.ingest_step_value.setText("Submitting files for ingestion")

            # Submit to ingestion queue
            job_response = c.api.enqueue_ingest_job(valid_files)
            job_id = job_response.get("id")

            if job_id:
                c.panel.log(f"Ingestion job queued: {job_id}")
                c.panel.log(
                    f"Processing {len(valid_files)} file(s) in background..."
                )

                # Start monitoring the job
                c._start_ingest_monitoring(job_id)

                # Clear selection after successful submission
                c.panel.clear_selected_files()
                c.panel.validation_status_label.clear()
            else:
                c.panel.log("Failed to queue ingestion job")
                c.panel.ingest_progress_bar.setRange(0, 100)
                c.panel.ingest_progress_bar.setValue(0)
                c.panel.ingest_status_value.setText("FAILED")

        except Exception as e:
            c._logger.error(
                "Failed to enqueue files for ingestion: %s", e, exc_info=True
            )
            c.panel.log(f"Ingestion failed: {e}")
            c.panel.ingest_progress_bar.setRange(0, 100)
            c.panel.ingest_progress_bar.setValue(0)
            c.panel.ingest_status_value.setText("FAILED")

    def delete_asset(self, asset_data: dict) -> None:
        """Delete an asset from the database and catalog."""
        c = self._controller
        if not c._require_offline_endpoints("Delete asset"):
            return
        if not c.api.api_ready():
            c.panel.log(
                f"API unavailable at {c.api.base_url}. Start API/server desktop, then retry."
            )
            return

        asset_id = asset_data.get("id")
        filename = asset_data.get("file_name", "Unknown")

        if not asset_id:
            c.panel.log(f"Cannot delete asset: missing ID for {filename}")
            return

        try:
            c.panel.log(f"Deleting asset: {filename}...")

            # Call delete API endpoint
            success = c.api.delete_asset(asset_id)

            if success:
                c.panel.log(f"Asset deleted successfully: {filename}")

                # Clear caches and refresh the assets list
                c._clear_asset_caches()

                # Refresh the uploaded assets list to reflect the deletion
                if c.app_mode == DesktopAppMode.SERVER:
                    QTimer.singleShot(100, c.panel.refresh_uploaded_assets)

                # Also refresh the main assets combo if in unified/client mode
                if c.app_mode in [DesktopAppMode.UNIFIED, DesktopAppMode.CLIENT]:
                    QTimer.singleShot(200, c.refresh_assets)

            else:
                c.panel.log(f"Failed to delete asset: {filename}")

        except Exception as e:
            c._logger.error(
                "Failed to delete asset %s: %s", filename, e, exc_info=True
            )
            c.panel.log(f"Delete failed: {e}")

    def refresh_assets(self) -> None:
        """Refresh the asset catalog from the API."""
        c = self._controller
        if not c._require_offline_endpoints("Catalog refresh"):
            return

        # Clear all caches first to ensure fresh data
        c._clear_asset_caches()

        try:
            # Force a fresh API call without any caching
            assets = c.api.list_assets()
            # Use SearchResultsCoordinator's dedupe method
            if hasattr(c, '_search_results') and c._search_results:
                assets = c._search_results._dedupe_assets(assets)

            # Log the API response for debugging
            c._logger.info(f"API returned {len(assets) if assets else 0} assets")

        except httpx.HTTPError as exc:
            c._handle_api_error("Catalog refresh", exc)
            return

        # Clear only asset-catalog caches — do NOT touch search layer state
        c.panel.assets_combo.clear()
        c._asset_cache.clear()
        c._dem_asset_kind_cache.clear()
        # NOTE: _search_result_assets_by_path and _search_layer_visibility are intentionally preserved so that the Search Results table is unaffected by a catalog refresh.

        # Check if assets is empty or None
        if not assets:
            c.panel.log("Catalog refreshed: 0 assets (database is empty)")
            c._logger.info("Catalog refreshed: database is empty")

            # Force refresh uploaded assets list to show empty state
            if c.app_mode == DesktopAppMode.SERVER:
                QTimer.singleShot(100, c.panel.refresh_uploaded_assets)
            return

        for asset in assets:
            c._asset_cache[asset["file_path"]] = asset
            name_suffix = ""
            if not c._asset_path_accessible_locally(asset):
                name_suffix = " (remote)"
            label = f"{asset['file_name']} [{asset['kind']}]"
            label += name_suffix
            c.panel.assets_combo.addItem(label, asset)

        # Force refresh uploaded assets list on server mode
        if c.app_mode == DesktopAppMode.SERVER:
            # Use a small delay to ensure the API has processed any recent changes
            QTimer.singleShot(100, lambda: c.panel.refresh_uploaded_assets())

        shown = c.panel.assets_combo.count()
        recommendation = c.performance.recommend_policy(
            asset_count=shown,
            dem_loaded=bool(c._explicit_dem_layer_visible),
        )
        c.panel.log(f"Catalog refreshed: {shown} assets")
        c.panel.log(
            "Render policy: "
            f"cache={recommendation.tile_cache_size}/terrain={recommendation.terrain_cache_size} "
            f"lod={recommendation.lod_mode}"
        )
        c._logger.info("Catalog refreshed visible=%s total=%s", shown, len(assets))
        c._logger.info("Render policy recommendation: %s", recommendation.reason)

    def preview_selected_uploaded_asset(self) -> None:
        """Load and flyto the selected asset from uploaded assets table."""
        c = self._controller
        row = c.panel.uploaded_assets_list.currentRow()
        if row < 0:
            return

        # Get asset data from the first column (serial number column)
        item = c.panel.uploaded_assets_list.item(row, 0)
        if item is None:
            return

        asset = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(asset, dict):
            return

        file_path = str(asset.get("file_path") or "")
        file_name = str(asset.get("file_name") or "Unknown")
        kind = str(asset.get("kind") or "Unknown").upper()

        if not file_path:
            return

        # Cache the asset
        c._asset_cache[file_path] = asset
        c.state.selected_asset = asset

        # Load the asset layer
        loaded_asset = c._load_asset_layer(asset)
        if not loaded_asset:
            c.panel.log(f"Failed to load asset: {file_name}")
            return

        c.panel.log(f"Loading {kind}: {file_name}")

        # Smooth flyto the asset region
        c._flyto_asset_bounds(asset, kind)

        c._logger.info(
            "Asset loaded and camera moved: name=%s kind=%s",
            file_name,
            kind,
        )

    def stop_ingest_polling(self) -> None:
        """Manually stop ingest job polling."""
        c = self._controller
        if c._ingest_poll_timer.isActive():
            c._ingest_poll_timer.stop()
            c.state.active_ingest_job_id = None
            c._ingest_poll_start_time = None
            c.panel.log("Ingest polling stopped manually")
            c.panel.ingest_status_value.setText("STOPPED")
            c.panel.ingest_step_value.setText("Polling stopped by user")

    def create_raster_asset_from_path(self, file_path: str) -> dict | None:
        """Create a raster asset from a file path."""
        c = self._controller
        path = Path(str(file_path)).expanduser()
        if not path.exists():
            c.panel.log(f"Raster not found: {path}")
            return None
        if c.api.api_ready():
            try:
                from src_new.clients.desktop_search.tile_url_builder import build_xyz_url
                asset = c.api.register_raster(str(path))
                if isinstance(asset, dict):
                    if "tile_url" not in asset:
                        asset["tile_url"] = build_xyz_url(str(path))
                    return asset
            except Exception as exc:
                c.panel.log(f"Raster registration failed: {path.name}. {exc}")
                c._logger.warning("Raster registration failed: %s", exc)
        try:
            from src_new.services.ingestion.gdal_pipelines.metadata_extractor import (
                extract_metadata,
            )
            from src_new.clients.desktop_search.tile_url_builder import build_xyz_url
            metadata = extract_metadata(path)
        except Exception as exc:
            c.panel.log(f"Metadata extraction failed: {path.name}. {exc}")
            c._logger.warning("Metadata extraction failed: %s", exc)
            return None

        bbox = getattr(metadata, "bbox", None) or getattr(metadata, "bounds", None)
        if bbox is None:
            c.panel.log(f"Metadata extraction failed: {path.name}. Missing bbox information")
            c._logger.warning("Metadata extraction failed: missing bbox information")
            return None
        bounds_wkt = bbox.to_wkt_polygon()
        return {
            "file_path": str(metadata.file_path),
            "file_name": metadata.file_name,
            "kind": metadata.kind.value,
            "crs": metadata.crs or "-",
            "bounds_wkt": bounds_wkt,
            "resolution_x": metadata.resolution_x,
            "resolution_y": metadata.resolution_y,
            "width": metadata.width,
            "height": metadata.height,
            "tile_url": build_xyz_url(str(metadata.file_path)),
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
