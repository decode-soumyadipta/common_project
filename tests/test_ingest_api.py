from pathlib import Path

from fastapi.testclient import TestClient

from offline_gis_app.server_backend.app import create_app


def test_register_endpoint(monkeypatch):
    app = create_app()
    client = TestClient(app)

    def fake_register(path: Path, _session):
        return {
            "id": "x1",
            "file_name": path.name,
            "file_path": str(path),
            "kind": "geotiff",
            "crs": "EPSG:4326",
            "centroid": {"lon": 20, "lat": 30},
            "bounds_wkt": "POLYGON((10 20,30 20,30 40,10 40,10 20))",
            "tile_url": "http://127.0.0.1:8081/cog/tiles/{z}/{x}/{y}?url=file:///tmp/a.tif",
        }

    monkeypatch.setattr(
        "offline_gis_app.server_backend.routes.ingest.register_raster", fake_register
    )
    response = client.post("/ingest/register", json={"path": "/tmp/a.tif"})
    assert response.status_code == 200
    assert response.json()["file_name"] == "a.tif"
