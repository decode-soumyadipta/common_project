from fastapi.testclient import TestClient

from offline_gis_app.server_backend.app import create_app


def test_profile_endpoint(monkeypatch):
    client = TestClient(create_app())

    monkeypatch.setattr(
        "offline_gis_app.server_backend.routes.profile.sample_profile",
        lambda *_args, **_kwargs: [1.0, 2.0, 3.0],
    )

    payload = {
        "path": "/tmp/dem.tif",
        "line_points": [{"lon": 77.0, "lat": 12.0}, {"lon": 77.1, "lat": 12.1}],
        "samples": 3,
    }
    response = client.post("/profile/elevation", json=payload)
    assert response.status_code == 200
    assert response.json()["values"] == [1.0, 2.0, 3.0]
