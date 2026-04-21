from offline_gis_app.server_ingestion.services.ingest_queue_service import IngestJobView
from fastapi.testclient import TestClient

from offline_gis_app.server_backend.app import create_app


def test_enqueue_ingest_job(monkeypatch):
    app = create_app()
    client = TestClient(app)

    def fake_enqueue(paths):
        assert paths == ["/tmp/a.tif"]
        return IngestJobView(
            id="job-1",
            status="queued",
            total_items=1,
            processed_items=0,
            failed_items=0,
            checkpoint_item_index=0,
            started_at=None,
            completed_at=None,
            last_checkpoint_at=None,
            last_error=None,
        )

    monkeypatch.setattr("offline_gis_app.server_backend.routes.ingest.ingest_queue_service.enqueue_paths", fake_enqueue)

    response = client.post("/ingest/queue", json={"paths": ["/tmp/a.tif"]})
    assert response.status_code == 200
    assert response.json()["id"] == "job-1"


def test_get_ingest_job(monkeypatch):
    app = create_app()
    client = TestClient(app)

    monkeypatch.setattr(
        "offline_gis_app.server_backend.routes.ingest.ingest_queue_service.get_job",
        lambda job_id: IngestJobView(
            id=job_id,
            status="running",
            total_items=2,
            processed_items=1,
            failed_items=0,
            checkpoint_item_index=1,
            started_at=None,
            completed_at=None,
            last_checkpoint_at=None,
            last_error=None,
        ),
    )

    response = client.get("/ingest/jobs/job-1")
    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_resume_ingest_job(monkeypatch):
    app = create_app()
    client = TestClient(app)

    monkeypatch.setattr(
        "offline_gis_app.server_backend.routes.ingest.ingest_queue_service.resume_job",
        lambda job_id: IngestJobView(
            id=job_id,
            status="queued",
            total_items=2,
            processed_items=1,
            failed_items=1,
            checkpoint_item_index=1,
            started_at=None,
            completed_at=None,
            last_checkpoint_at=None,
            last_error=None,
        ),
    )

    response = client.post("/ingest/jobs/job-2/resume")
    assert response.status_code == 200
    assert response.json()["id"] == "job-2"
