from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from offline_gis_app.db.models import IngestJob, IngestJobItem, IngestJobItemStatus, IngestJobStatus


class IngestJobRepository:
    """Persistence helper for queued ingest jobs and items."""

    def __init__(self, session: Session):
        self._session = session

    def create_job(self, file_paths: list[str]) -> IngestJob:
        job = IngestJob(
            id=str(uuid4()),
            status=IngestJobStatus.QUEUED,
            total_items=len(file_paths),
            processed_items=0,
            failed_items=0,
            checkpoint_item_index=0,
        )
        self._session.add(job)
        self._session.flush()

        for index, path in enumerate(file_paths, start=1):
            item = IngestJobItem(
                id=str(uuid4()),
                job_id=job.id,
                item_index=index,
                file_path=path,
                status=IngestJobItemStatus.PENDING,
                attempts=0,
                checkpoint_stage=None,
                stage_attempt=0,
            )
            self._session.add(item)

        self._session.commit()
        self._session.refresh(job)
        return job

    def get_job(self, job_id: str) -> IngestJob | None:
        stmt = select(IngestJob).where(IngestJob.id == job_id)
        return self._session.scalar(stmt)

    def list_recoverable_jobs(self) -> list[IngestJob]:
        stmt = (
            select(IngestJob)
            .where(IngestJob.status.in_([IngestJobStatus.QUEUED, IngestJobStatus.RUNNING, IngestJobStatus.PAUSED]))
            .order_by(IngestJob.created_at.asc())
        )
        return list(self._session.scalars(stmt))

    def list_pending_or_failed_items(self, job_id: str) -> list[IngestJobItem]:
        stmt = (
            select(IngestJobItem)
            .where(
                IngestJobItem.job_id == job_id,
                IngestJobItem.status.in_([IngestJobItemStatus.PENDING, IngestJobItemStatus.FAILED]),
            )
            .order_by(IngestJobItem.item_index.asc())
        )
        return list(self._session.scalars(stmt))

    def get_item(self, item_id: str) -> IngestJobItem | None:
        stmt = select(IngestJobItem).where(IngestJobItem.id == item_id)
        return self._session.scalar(stmt)

    def mark_job_running(self, job: IngestJob) -> None:
        now = datetime.utcnow()
        job.status = IngestJobStatus.RUNNING
        if job.started_at is None:
            job.started_at = now
        job.updated_at = now
        self._session.add(job)
        self._session.commit()

    def set_job_status(self, job: IngestJob, status: IngestJobStatus, *, last_error: str | None = None) -> None:
        job.status = status
        job.last_error = last_error
        job.updated_at = datetime.utcnow()
        self._session.add(job)
        self._session.commit()

    def mark_job_checkpoint(self, job: IngestJob, checkpoint_item_index: int) -> None:
        now = datetime.utcnow()
        job.checkpoint_item_index = checkpoint_item_index
        job.last_checkpoint_at = now
        job.updated_at = now
        self._session.add(job)
        self._session.commit()

    def mark_job_terminal(self, job: IngestJob, status: IngestJobStatus, last_error: str | None = None) -> None:
        now = datetime.utcnow()
        job.status = status
        job.last_error = last_error
        job.completed_at = now
        job.updated_at = now
        self._session.add(job)
        self._session.commit()

    def update_item_status(
        self,
        item: IngestJobItem,
        status: IngestJobItemStatus,
        *,
        attempts: int | None = None,
        stage_attempt: int | None = None,
        checkpoint_stage: str | None = None,
        last_error: str | None = None,
        asset_id: str | None = None,
    ) -> None:
        item.status = status
        if attempts is not None:
            item.attempts = attempts
        if stage_attempt is not None:
            item.stage_attempt = stage_attempt
        if checkpoint_stage is not None:
            item.checkpoint_stage = checkpoint_stage
        item.last_error = last_error
        item.asset_id = asset_id
        item.updated_at = datetime.utcnow()
        self._session.add(item)
        self._session.commit()

    def update_item_status_by_id(
        self,
        item_id: str,
        status: IngestJobItemStatus,
        *,
        attempts: int | None = None,
        stage_attempt: int | None = None,
        checkpoint_stage: str | None = None,
        last_error: str | None = None,
        asset_id: str | None = None,
    ) -> None:
        item = self.get_item(item_id)
        if item is None:
            return
        self.update_item_status(
            item,
            status,
            attempts=attempts,
            stage_attempt=stage_attempt,
            checkpoint_stage=checkpoint_stage,
            last_error=last_error,
            asset_id=asset_id,
        )

    def mark_item_stage_checkpoint(self, item_id: str, stage_name: str) -> None:
        item = self.get_item(item_id)
        if item is None:
            return
        item.checkpoint_stage = stage_name
        item.stage_attempt = int(item.stage_attempt or 0) + 1
        item.last_checkpoint_at = datetime.utcnow()
        item.updated_at = datetime.utcnow()
        self._session.add(item)
        self._session.commit()

    def refresh_job_counters(self, job: IngestJob) -> None:
        stmt = select(IngestJobItem.status).where(IngestJobItem.job_id == job.id)
        statuses = list(self._session.scalars(stmt))
        job.processed_items = sum(1 for status in statuses if status == IngestJobItemStatus.SUCCEEDED)
        job.failed_items = sum(1 for status in statuses if status == IngestJobItemStatus.FAILED)
        job.total_items = len(statuses)
        job.updated_at = datetime.utcnow()
        self._session.add(job)
        self._session.commit()
