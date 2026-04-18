from types import SimpleNamespace

from fastapi.testclient import TestClient

from offline_gis_app.api.app import create_app
from offline_gis_app.db.catalog import CatalogRepository
from offline_gis_app.utils.geometry import Bounds


class _Kind:
    def __init__(self, value: str):
        self.value = value


def _asset(name: str, bounds: Bounds):
    return SimpleNamespace(
        id=name,
        file_name=name,
        file_path=f"/tmp/{name}.tif",
        raster_kind=_Kind("geotiff"),
        crs="EPSG:4326",
        bounds_wkt=bounds.to_wkt_polygon(),
    )


def test_search_by_point(monkeypatch):
    assets = [
        _asset("a", Bounds(10, 10, 20, 20)),
        _asset("b", Bounds(30, 30, 40, 40)),
    ]
    monkeypatch.setattr(CatalogRepository, "search_assets_by_point", lambda self, lon, lat: assets[:1])

    client = TestClient(create_app())
    response = client.post("/search/point", json={"lon": 15, "lat": 15})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["file_name"] == "a"


def test_search_by_bbox(monkeypatch):
    assets = [
        _asset("a", Bounds(10, 10, 20, 20)),
        _asset("b", Bounds(30, 30, 40, 40)),
    ]
    monkeypatch.setattr(
        CatalogRepository,
        "search_assets_by_bbox",
        lambda self, west, south, east, north: assets,
    )

    client = TestClient(create_app())
    response = client.post(
        "/search/bbox",
        json={"west": 12, "south": 12, "east": 35, "north": 35},
    )

    assert response.status_code == 200
    payload = response.json()
    assert {item["file_name"] for item in payload} == {"a", "b"}


def test_search_by_polygon_with_buffer(monkeypatch):
    assets = [
        _asset("a", Bounds(10, 10, 20, 20)),
        _asset("b", Bounds(30, 30, 40, 40)),
    ]
    monkeypatch.setattr(
        CatalogRepository,
        "search_assets_by_polygon",
        lambda self, polygon_points, buffer_meters=0.0: assets[:1],
    )

    client = TestClient(create_app())
    response = client.post(
        "/search/polygon",
        json={
            "points": [
                {"lon": 21.0, "lat": 21.0},
                {"lon": 22.0, "lat": 21.0},
                {"lon": 22.0, "lat": 22.0},
            ],
            "buffer_meters": 150000.0,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["file_name"] == "a"
