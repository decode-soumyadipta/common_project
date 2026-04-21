from __future__ import annotations

import logging
from datetime import datetime
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Callable

from offline_gis_app.config.settings import settings
from offline_gis_app.server_ingestion.repository.ingest_job_repository import IngestJobRepository
from offline_gis_app.db.models import IngestJob, IngestJobItemStatus, IngestJobStatus
from offline_gis_app.db.session import SessionLocal
from offline_gis_app.server_ingestion.services.ingest_service import register_raster

LOGGER = logging.getLogger("services.ingest_queue")


@dataclass(frozen=True)
class IngestJobView:
    """Serializable view model exposed by ingest API endpoints."""
    id: str
    status: str
    total_items: int
    processed_items: int
    failed_items: int
    checkpoint_item_index: int
    progress_percent: int = 0
    current_step: str | None = None
    current_item_path: str | None = None
    elapsed_seconds: float | None = None
    started_at: str | None = None
    completed_at: str | None = None
    last_checkpoint_at: str | None = None
    last_error: str | None = None


@dataclass
class _RuntimeProgress:
    current_step: str | None = None
    current_item_path: str | None = None


class IngestQueueService:
    """Background ingest queue coordinator with retry/checkpoint support."""
    def __init__(
        self,
        session_factory: Callable[[], Any],
        *,
        max_workers: int,
        checkpoint_interval: int,
        item_max_retries: int,
    ):
        self._session_factory = session_factory
        self._max_workers = max(1, min(int(max_workers), 5))
        self._checkpoint_interval = max(1, int(checkpoint_interval))
        self._item_max_retries = max(1, int(item_max_retries))
        self._executor: ThreadPoolExecutor | None = None
        self._lock = Lock()
        self._active_futures: dict[str, Future] = {}
        self._runtime_progress: dict[str, _RuntimeProgress] = {}

    def start(self) -> None:
        """Start the queue executor if it is not already running."""
        with self._lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=self._max_workers, thread_name_prefix="ingest-queue")

    def shutdown(self) -> None:
        """Stop accepting new queue work and tear down executor state."""
        with self._lock:
            executor = self._executor
            self._executor = None
            self._active_futures = {}
            self._runtime_progress = {}
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=False)

    def enqueue_paths(self, paths: list[str]) -> IngestJobView:
        """Create a new ingest job for provided paths and submit it."""
        cleaned = [str(Path(path).expanduser()) for path in paths if str(path).strip()]
        if not cleaned:
            raise ValueError("No ingest paths provided")

        with self._session_factory() as session:
            repo = IngestJobRepository(session)
            job = repo.create_job(cleaned)
            view = _job_to_view(job)

        self._set_runtime_progress(job.id, "Queued for metadata ingest", None)

        self._submit_job(job.id)
        return self._attach_runtime_progress(view)

    def get_job(self, job_id: str) -> IngestJobView | None:
        """Return current job view, or None if the job does not exist."""
        with self._session_factory() as session:
            repo = IngestJobRepository(session)
            job = repo.get_job(job_id)
            if job is None:
                return None
            repo.refresh_job_counters(job)
            job = repo.get_job(job_id)
            if job is None:
                return None
            return self._attach_runtime_progress(_job_to_view(job))

    def resume_job(self, job_id: str) -> IngestJobView:
        """Resume a paused or recoverable job by id."""
        with self._session_factory() as session:
            repo = IngestJobRepository(session)
            job = repo.get_job(job_id)
            if job is None:
                raise ValueError(f"Ingest job not found: {job_id}")
            if job.status == IngestJobStatus.COMPLETED:
                return _job_to_view(job)
            repo.set_job_status(job, IngestJobStatus.QUEUED)
            refreshed = repo.get_job(job_id)
            if refreshed is None:
                raise ValueError(f"Ingest job not found after status update: {job_id}")
            view = _job_to_view(refreshed)

        self._set_runtime_progress(job_id, "Queued for resume", None)

        self._submit_job(job_id)
        return self._attach_runtime_progress(view)

    def resume_recoverable_jobs(self) -> None:
        """Auto-resume jobs left in recoverable states after restart."""
        with self._session_factory() as session:
            repo = IngestJobRepository(session)
            jobs = repo.list_recoverable_jobs()
            for job in jobs:
                if job.status == IngestJobStatus.RUNNING:
                    repo.set_job_status(job, IngestJobStatus.QUEUED)
                    self._set_runtime_progress(job.id, "Recovering interrupted ingest job", None)

        with self._session_factory() as session:
            repo = IngestJobRepository(session)
            for job in repo.list_recoverable_jobs():
                if job.status in {IngestJobStatus.QUEUED, IngestJobStatus.PAUSED}:
                    self._submit_job(job.id)

    def _submit_job(self, job_id: str) -> None:
        self.start()
        with self._lock:
            if job_id in self._active_futures:
                future = self._active_futures[job_id]
                if not future.done():
                    return
                self._active_futures.pop(job_id, None)
            if self._executor is None:
                raise RuntimeError("Ingest queue executor is not available")
            future = self._executor.submit(self._run_job, job_id)
            self._active_futures[job_id] = future

    def _run_job(self, job_id: str) -> None:
        LOGGER.info("Starting ingest job id=%s", job_id)
        processed_since_checkpoint = 0

        while True:
            with self._session_factory() as session:
                repo = IngestJobRepository(session)
                job = repo.get_job(job_id)
                if job is None:
                    LOGGER.error("Ingest job disappeared id=%s", job_id)
                    return
                if job.status == IngestJobStatus.PAUSED:
                    LOGGER.info("Ingest job paused id=%s", job_id)
                    return
                repo.mark_job_running(job)
                items = repo.list_pending_or_failed_items(job_id)

            retryable_items = [
                queued_item
                for queued_item in items
                if queued_item.status == IngestJobItemStatus.PENDING
                or int(queued_item.attempts) < self._item_max_retries
            ]

            if not retryable_items:
                self._finish_job(job_id)
                LOGGER.info("Ingest job completed id=%s", job_id)
                return

            item = retryable_items[0]
            attempts = item.attempts + 1
            if item.status == IngestJobItemStatus.FAILED:
                self._set_runtime_progress(
                    job_id,
                    f"Retrying failed item (attempt {attempts}/{self._item_max_retries})",
                    item.file_path,
                )
            self._set_runtime_progress(job_id, "Validating source file", item.file_path)

            with self._session_factory() as session:
                repo = IngestJobRepository(session)
                repo.update_item_status_by_id(
                    item.id,
                    IngestJobItemStatus.PROCESSING,
                    attempts=attempts,
                    last_error=None,
                )

            try:
                with self._session_factory() as session:
                    result = register_raster(
                        Path(item.file_path),
                        session,
                        progress_callback=lambda step: self._set_runtime_progress(job_id, step, item.file_path),
                    )
                with self._session_factory() as session:
                    repo = IngestJobRepository(session)
                    repo.update_item_status_by_id(
                        item.id,
                        IngestJobItemStatus.SUCCEEDED,
                        attempts=attempts,
                        last_error=None,
                        asset_id=result.get("id"),
                    )
                    tracked_job = repo.get_job(job_id)
                    if tracked_job is not None:
                        repo.refresh_job_counters(tracked_job)
                self._set_runtime_progress(job_id, "Catalog entry indexed", item.file_path)
                processed_since_checkpoint += 1
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("Ingest item failed job=%s path=%s", job_id, item.file_path)
                retry_allowed = attempts < self._item_max_retries
                if retry_allowed:
                    runtime_step = f"Retry scheduled after failure ({attempts}/{self._item_max_retries})"
                    next_status = IngestJobItemStatus.PENDING
                    error_text = str(exc)
                else:
                    runtime_step = f"Marked failed after max retries ({attempts}/{self._item_max_retries})"
                    next_status = IngestJobItemStatus.FAILED
                    error_text = f"{exc} (max retries reached)"

                self._set_runtime_progress(job_id, runtime_step, item.file_path)
                with self._session_factory() as session:
                    repo = IngestJobRepository(session)
                    repo.update_item_status_by_id(
                        item.id,
                        next_status,
                        attempts=attempts,
                        last_error=error_text,
                    )
                    tracked_job = repo.get_job(job_id)
                    if tracked_job is not None:
                        repo.refresh_job_counters(tracked_job)

            if processed_since_checkpoint >= self._checkpoint_interval:
                with self._session_factory() as session:
                    repo = IngestJobRepository(session)
                    job = repo.get_job(job_id)
                    if job is not None:
                        self._set_runtime_progress(job_id, "Checkpoint saved", item.file_path)
                        repo.mark_job_checkpoint(job, checkpoint_item_index=item.item_index)
                processed_since_checkpoint = 0

    def _finish_job(self, job_id: str) -> None:
        with self._session_factory() as session:
            repo = IngestJobRepository(session)
            job = repo.get_job(job_id)
            if job is None:
                return
            repo.refresh_job_counters(job)
            refreshed = repo.get_job(job_id)
            if refreshed is None:
                return

            if refreshed.failed_items > 0 and refreshed.processed_items > 0:
                repo.mark_job_terminal(refreshed, IngestJobStatus.PARTIAL)
                self._set_runtime_progress(job_id, "Completed with partial failures", None)
            elif refreshed.failed_items > 0 and refreshed.processed_items == 0:
                repo.mark_job_terminal(refreshed, IngestJobStatus.FAILED, last_error=refreshed.last_error)
                self._set_runtime_progress(job_id, "Failed", None)
            else:
                repo.mark_job_terminal(refreshed, IngestJobStatus.COMPLETED)
                self._set_runtime_progress(job_id, "Completed", None)

    def _set_runtime_progress(self, job_id: str, step: str | None, item_path: str | None) -> None:
        with self._lock:
            self._runtime_progress[job_id] = _RuntimeProgress(current_step=step, current_item_path=item_path)

    def _attach_runtime_progress(self, view: IngestJobView) -> IngestJobView:
        with self._lock:
            runtime = self._runtime_progress.get(view.id)

        total = max(0, int(view.total_items))
        done = min(total, int(view.processed_items) + int(view.failed_items))
        progress_percent = int((done * 100) / total) if total > 0 else 0

        elapsed_seconds: float | None = None
        if view.started_at:
            try:
                started = datetime.fromisoformat(view.started_at)
                anchor = datetime.fromisoformat(view.completed_at) if view.completed_at else datetime.utcnow()
                elapsed_seconds = max(0.0, (anchor - started).total_seconds())
            except ValueError:
                elapsed_seconds = None

        return IngestJobView(
            id=view.id,
            status=view.status,
            total_items=view.total_items,
            processed_items=view.processed_items,
            failed_items=view.failed_items,
            checkpoint_item_index=view.checkpoint_item_index,
            progress_percent=progress_percent,
            current_step=runtime.current_step if runtime else None,
            current_item_path=runtime.current_item_path if runtime else None,
            elapsed_seconds=elapsed_seconds,
            started_at=view.started_at,
            completed_at=view.completed_at,
            last_checkpoint_at=view.last_checkpoint_at,
            last_error=view.last_error,
        )



def _job_to_view(job: IngestJob) -> IngestJobView:
    """Convert ORM ingest job model into API view payload."""
    return IngestJobView(
        id=job.id,
        status=job.status.value,
        total_items=job.total_items,
        processed_items=job.processed_items,
        failed_items=job.failed_items,
        checkpoint_item_index=job.checkpoint_item_index,
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        last_checkpoint_at=job.last_checkpoint_at.isoformat() if job.last_checkpoint_at else None,
        last_error=job.last_error,
    )


ingest_queue_service = IngestQueueService(
    session_factory=SessionLocal,
    max_workers=settings.max_ingest_workers,
    checkpoint_interval=settings.ingest_checkpoint_interval,
    item_max_retries=settings.ingest_item_max_retries,
)
