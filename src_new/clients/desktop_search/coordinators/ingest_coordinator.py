from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path

import httpx
from qtpy.QtCore import QTimer

from src_new.clients.desktop_search.app_mode import DesktopAppMode


class IngestCoordinator:
    """Encapsulate ingestion monitoring and progress tracking for desktop controller."""

    def __init__(self, controller):
        self._controller = controller
        self._logger = logging.getLogger("client_desktop.ingest_coordinator")

    def start_ingest_monitoring(self, job_id: str) -> None:
        """Start monitoring an ingestion job by setting up the polling timer."""
        c = self._controller
        # Set the active job ID in state
        c.state.active_ingest_job_id = str(job_id)

        # Record polling start time for timeout tracking
        c._ingest_poll_start_time = dt.datetime.now(dt.timezone.utc)

        # Start the polling timer (polls every 500ms)
        c._ingest_poll_timer.start()

        self._logger.info("Started monitoring ingestion job: %s", job_id)

    def select_asset_in_combo(self, file_path: str) -> bool:
        """Select an asset in the combo box by file path."""
        c = self._controller
        if not file_path:
            return False
        for index in range(c.panel.assets_combo.count()):
            item = c.panel.assets_combo.itemData(index)
            if not isinstance(item, dict):
                continue
            if str(item.get("file_path") or "") == file_path:
                c.panel.assets_combo.setCurrentIndex(index)
                return True
        return False

    def poll_active_ingest_job(self) -> None:
        """Poll the active ingestion job for progress updates."""
        c = self._controller
        if not c._require_offline_endpoints("Ingest progress refresh"):
            c._ingest_poll_timer.stop()
            return
        job_id = c.state.active_ingest_job_id
        if not job_id:
            c._ingest_poll_timer.stop()
            return

        # Check for polling timeout (max 2 hours)
        if c._ingest_poll_start_time:
            elapsed = dt.datetime.now(dt.timezone.utc) - c._ingest_poll_start_time
            if elapsed.total_seconds() > 7200:  # 2 hours
                self._logger.warning(
                    "Ingest polling timeout after 2 hours, stopping polling for job %s",
                    job_id,
                )
                c.panel.log("Ingest polling timed out - job may have completed")
                c.panel.ingest_status_value.setText("TIMEOUT")
                c.panel.ingest_step_value.setText(
                    "Polling timed out - check job status manually"
                )
                c._ingest_poll_timer.stop()
                c.state.active_ingest_job_id = None
                c._ingest_poll_start_time = None
                return

        try:
            job = c.api.get_ingest_job(job_id)
        except httpx.HTTPError as exc:
            # Handle different types of HTTP errors
            if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
                status_code = exc.response.status_code
                if status_code == 404:
                    # Job not found - it was likely completed and cleaned up
                    self._logger.info("Ingest job completed and cleaned up: %s", job_id)

                    # Check if any new assets were actually added to the database
                    try:
                        current_asset_count = len(c.api.list_assets())
                        if hasattr(c, "_pre_ingest_asset_count"):
                            new_assets = (
                                current_asset_count - c._pre_ingest_asset_count
                            )
                            if new_assets > 0:
                                c.panel.log(
                                    f"Ingest completed: {new_assets} new assets added to database"
                                )
                                c.panel.ingest_step_value.setText(
                                    f"Completed: {new_assets} new assets added"
                                )
                            else:
                                c.panel.log(
                                    "Ingest completed: No new assets (files may already be in database)"
                                )
                                c.panel.ingest_step_value.setText(
                                    "Completed: No new files (duplicates skipped)"
                                )
                        else:
                            c.panel.log("Ingest job completed successfully")
                            c.panel.ingest_step_value.setText(
                                "Job completed and cleaned up"
                            )
                    except Exception:
                        c.panel.log("Ingest job completed successfully")
                        c.panel.ingest_step_value.setText(
                            "Job completed and cleaned up"
                        )

                    # Update UI to show completion
                    c.panel.ingest_status_value.setText("COMPLETED")
                    c.panel.ingest_progress_bar.setValue(100)

                    # Add informative completion message
                    c.panel.append_ingest_detail(
                        f"[COMPLETED] Job finished - check asset count for new additions"
                    )

                    # Stop polling and clear job ID
                    c._ingest_poll_timer.stop()
                    c.state.active_ingest_job_id = None
                    c._ingest_poll_start_time = None

                    # Auto-refresh the uploaded assets table when ingestion completes
                    if c.app_mode == DesktopAppMode.SERVER:
                        QTimer.singleShot(
                            500, lambda: c.panel.refresh_uploaded_assets()
                        )

                    return
                elif status_code >= 500:
                    # Server error - log but continue polling
                    self._logger.warning(
                        "Ingest progress refresh failed with server error %s, continuing to poll",
                        status_code,
                    )
                    return
            # For other errors, handle normally and stop polling
            c._handle_api_error("Ingest progress refresh", exc)
            c._ingest_poll_timer.stop()
            c.state.active_ingest_job_id = None
            c._ingest_poll_start_time = None
            return

        self.update_ingest_progress_ui(job, emit_detail=True)
        status = str(job.get("status") or "").lower()
        if status in {"completed", "failed", "partial"}:
            c._ingest_poll_timer.stop()
            c.state.active_ingest_job_id = None
            c._ingest_poll_start_time = None

            # Auto-refresh the uploaded assets table when ingestion completes
            if c.app_mode == DesktopAppMode.SERVER and status in {
                "completed",
                "partial",
            }:
                QTimer.singleShot(500, lambda: c.panel.refresh_uploaded_assets())

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

    def update_ingest_progress_ui(self, job: dict, *, emit_detail: bool) -> None:
        """Update the UI with ingestion progress information."""
        c = self._controller
        status = str(job.get("status") or "unknown").lower()
        total_items = int(job.get("total_items") or 0)
        processed_items = int(job.get("processed_items") or 0)
        failed_items = int(job.get("failed_items") or 0)
        checkpoint = int(job.get("checkpoint_item_index") or 0)
        progress_percent = int(job.get("progress_percent") or 0)
        current_step = str(
            job.get("current_step") or self.default_step_for_status(status)
        )
        current_item_path = str(job.get("current_item_path") or "")
        elapsed_seconds = job.get("elapsed_seconds")

        # Extract just the filename from the full path
        current_filename = Path(current_item_path).name if current_item_path else "-"

        # Ensure progress bar shows actual progress
        c.panel.ingest_progress_bar.setValue(max(0, min(progress_percent, 100)))
        c.panel.ingest_status_value.setText(status.upper())
        c.panel.ingest_step_value.setText(current_step)
        # Enhanced progress display with duplicate detection info
        if status.lower() == "completed" and processed_items == 0 and total_items > 0:
            # Likely all files were duplicates
            c.panel.ingest_counts_value.setText(
                f"Analyzed: {total_items} files | New: 0 | Duplicates skipped: {total_items}"
            )
        elif status.lower() == "completed" and processed_items < total_items:
            # Some files were duplicates
            skipped = total_items - processed_items - failed_items
            c.panel.ingest_counts_value.setText(
                f"Processed: {processed_items}/{total_items} | Failed: {failed_items} | Skipped: {skipped}"
            )
        else:
            # Normal progress display
            c.panel.ingest_counts_value.setText(
                f"Processed: {processed_items}/{total_items} | Failed: {failed_items}"
            )
        c.panel.ingest_item_value.setText(f"Current: {current_filename}")
        c.panel.ingest_elapsed_value.setText(
            f"Elapsed: {self.format_elapsed(elapsed_seconds)}"
        )

        # Log progress updates for debugging
        if emit_detail:
            self._logger.debug(
                "Progress update: %d%% (%d/%d processed, %d failed) - %s",
                progress_percent,
                processed_items,
                total_items,
                failed_items,
                current_step,
            )

        if emit_detail and (
            c._last_ingest_step != current_step or c._last_ingest_status != status
        ):
            c.panel.append_ingest_detail(
                f"[{self.format_elapsed(elapsed_seconds)}] {status.upper()} - {current_step}"
            )
            c._last_ingest_step = current_step
            c._last_ingest_status = status

        if emit_detail and status in {"completed", "failed", "partial"}:
            c.panel.log(
                f"Ingest job {job.get('id')} finished | Status: {status.upper()} | "
                f"Processed: {processed_items}/{total_items} | Failed: {failed_items}"
            )
            # Auto-refresh the uploaded assets table when ingestion completes
            if c.app_mode == DesktopAppMode.SERVER and status in {
                "completed",
                "partial",
            }:
                QTimer.singleShot(500, c.panel.refresh_uploaded_assets)

    @staticmethod
    def default_step_for_status(status: str) -> str:
        """Get default step message for a given status."""
        mapping = {
            "queued": "Queued for metadata ingest",
            "running": "Processing source metadata",
            "completed": "Metadata indexing completed",
            "partial": "Completed with partial failures",
            "failed": "Ingest failed",
            "paused": "Ingest paused",
        }
        return mapping.get(status, "Ingest status updated")

    @staticmethod
    def format_elapsed(elapsed_seconds: float | int | None) -> str:
        """Format elapsed time in HH:MM:SS or MM:SS format."""
        if elapsed_seconds is None:
            return "00:00"
        elapsed = max(0.0, float(elapsed_seconds))
        if 0.0 < elapsed < 1.0:
            return "<1s"

        total_seconds = max(0, int(round(elapsed)))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"
