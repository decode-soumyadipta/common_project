from __future__ import annotations

from typing import Any

from core_shared.db.models import RasterAsset
from server_vm.server_backend.catalog.catalog_repository import CatalogRepository
from core_shared.ingestion.services.tile_url_builder import build_xyz_url


class CatalogService:
    """Business-layer operations for catalog listing and spatial searches."""

    def __init__(self, repo: CatalogRepository):
        self._repo = repo

    def list_assets(self) -> list[dict[str, Any]]:
        return [self._serialize_asset(asset) for asset in self._repo.list_assets()]

    def search_by_point(self, lon: float, lat: float) -> list[dict[str, Any]]:
        assets = self._repo.search_assets_by_point(lon, lat)
        return [self._serialize_asset(asset) for asset in assets]

    def search_by_bbox(
        self, west: float, south: float, east: float, north: float
    ) -> list[dict[str, Any]]:
        assets = self._repo.search_assets_by_bbox(
            west=west, south=south, east=east, north=north
        )
        return [self._serialize_asset(asset) for asset in assets]

    def search_by_polygon(
        self, points: list[tuple[float, float]], buffer_meters: float = 0.0
    ) -> list[dict[str, Any]]:
        assets = self._repo.search_assets_by_polygon(
            points, buffer_meters=buffer_meters
        )
        return [self._serialize_asset(asset) for asset in assets]

    @staticmethod
    def _serialize_asset(item: RasterAsset) -> dict[str, Any]:
        created_at = getattr(item, "created_at", None)
        return {
            "id": item.id,
            "file_name": item.file_name,
            "file_path": item.file_path,
            "kind": item.raster_kind.value,
            "crs": item.crs,
            "bounds_wkt": item.bounds_wkt,
            "tile_url": build_xyz_url(item.file_path),
            "created_at": created_at.isoformat() if created_at else None,
        }
