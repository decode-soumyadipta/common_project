from pathlib import Path
import base64
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src_new.services.tile_serving.pointcloud_endpoints import router

@pytest.fixture
def test_app():
    app = FastAPI()
    app.include_router(router)
    return app

@pytest.fixture
def test_client(test_app):
    return TestClient(test_app)

def test_pointcloud_endpoints_missing_file(test_client):
    file_path = "/nonexistent/file.las"
    b64 = base64.urlsafe_b64encode(file_path.encode("utf-8")).rstrip(b"=").decode("ascii")
    response = test_client.get(f"/pointcloud/tileset/{b64}/tileset.json")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

def test_pointcloud_endpoints_invalid_extension(test_client, tmp_path):
    file_path = tmp_path / "test.txt"
    file_path.write_text("not a las file")
    b64 = base64.urlsafe_b64encode(str(file_path).encode("utf-8")).rstrip(b"=").decode("ascii")
    response = test_client.get(f"/pointcloud/tileset/{b64}/tileset.json")
    assert response.status_code == 400
    assert "only .las/.laz files are supported" in response.json()["detail"].lower()
