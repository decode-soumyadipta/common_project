from fastapi.testclient import TestClient

from offline_gis_app.server_backend.app import create_app


def test_health_endpoint():
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("status") == "ok"
    assert isinstance(payload.get("api_build"), str)
    assert payload.get("api_build")
