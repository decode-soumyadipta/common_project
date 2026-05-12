import httpx
import logging
from src_new.shared.config import settings

logger = logging.getLogger("client.api_service")

class ApiService:
    """Service layer for Desktop clients to communicate with Server A (Gateway)."""
    
    def __init__(self, base_url: str = None):
        self.base_url = (base_url or settings.gateway_url).rstrip("/")
        self.client = httpx.Client(base_url=self.base_url, timeout=30.0)

    def api_ready(self):
        try:
            resp = self.client.get("/health")
            return resp.status_code == 200
        except Exception:
            return False

    def list_assets(self):
        resp = self.client.get("/search/assets")
        resp.raise_for_status()
        return resp.json()

    def search_assets(self, query: dict):
        resp = self.client.post("/search/assets", json=query)
        resp.raise_for_status()
        return resp.json()

    def enqueue_ingest_job(self, paths: list[str]):
        resp = self.client.post("/ingest/queue", json={"paths": paths})
        resp.raise_for_status()
        return resp.json()

    def get_ingest_job(self, job_id: str):
        """Legacy alias for get_ingest_job_status."""
        resp = self.client.get(f"/ingest/jobs/{job_id}")
        resp.raise_for_status()
        return resp.json()

    def get_ingest_job_status(self, job_id: str):
        return self.get_ingest_job(job_id)

    def delete_asset(self, asset_id: str):
        # Placeholder for asset deletion
        return {"status": "success"}
