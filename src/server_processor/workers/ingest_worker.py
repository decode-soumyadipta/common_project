import time
import logging
import signal
from pathlib import Path
from platform_core.config.settings import settings
from platform_core.db.session import SessionLocal
from platform_core.ingestion.repository.ingest_job_repository import IngestJobRepository
from platform_core.db.models import IngestJobStatus, IngestJobItemStatus

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("server_processor.worker")

class IngestWorker:
    """Server B Worker: Polls the shared DB and processes heavy raster tasks."""
    
    def __init__(self):
        self.running = True
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

    def stop(self, *args):
        logger.info("Stopping worker...")
        self.running = False

    def run_loop(self):
        logger.info("Processor Node started. Polling for tasks...")
        while self.running:
            try:
                self.process_next_job()
            except Exception as e:
                logger.error("Error in worker loop: %s", e)
            time.sleep(2)

    def process_next_job(self):
        with SessionLocal() as session:
            repo = IngestJobRepository(session)
            jobs = repo.list_recoverable_jobs()
            
            # Find a QUEUED job to work on
            queued_jobs = [j for j in jobs if j.status == IngestJobStatus.QUEUED]
            if not queued_jobs:
                return

            job = queued_jobs[0]
            logger.info("Picking up job %s", job.id)
            repo.mark_job_running(job)
            
            items = repo.list_pending_or_failed_items(job.id)
            for item in items:
                if not self.running: break
                self.process_item(item, repo)
                
            repo.mark_job_terminal(job, IngestJobStatus.COMPLETED)
            logger.info("Job %s finished", job.id)

    def process_item(self, item, repo):
        logger.info("Processing item %s: %s", item.id, item.file_path)
        repo.update_item_status(item, IngestJobItemStatus.PROCESSING)
        
        try:
            # HEAVY GDAL WORK HERE
            # In a real implementation, we would call our GDAL pipelines
            from platform_core.ingestion.services.ingest_service import register_raster
            with SessionLocal() as session:
                register_raster(Path(item.file_path), session)
            
            repo.update_item_status(item, IngestJobItemStatus.SUCCEEDED)
            logger.info("Successfully processed %s", item.file_path)
        except Exception as e:
            logger.error("Failed to process %s: %s", item.file_path, e)
            repo.update_item_status(item, IngestJobItemStatus.FAILED, last_error=str(e))

if __name__ == "__main__":
    worker = IngestWorker()
    worker.run_loop()
