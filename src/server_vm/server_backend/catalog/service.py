from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from core_shared.db.models import RasterAsset
from server_vm.server_backend.catalog.catalog_repository import CatalogRepository
from core_shared.ingestion.services.tile_url_builder import build_xyz_url

LOGGER = logging.getLogger("catalog.service")


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
    def _resolve_tile_path(file_path: str) -> str:
        """Return the best available path for tiling.

        When the DB stores a COG path (e.g. ``dem.cog.tif``) that no longer
        exists on disk — because the COG was deleted or never written — fall
        back to the original source file so TiTiler doesn't 500.

        Resolution order:
        1. Registered path exists → use it as-is.
        2. Registered path is a ``.cog.tif`` → try the original ``.tif``.
        3. Nothing found → return registered path (TiTiler will 500 with a
           clear "No such file" message rather than a silent blank layer).
        """
        p = Path(file_path)
        if p.exists():
            return file_path

        # COG naming convention: ``stem.cog.tif`` → original is ``stem.tif``
        name = p.name
        if name.endswith(".cog.tif"):
            original_stem = name[: -len(".cog.tif")]
            candidate = p.with_name(f"{original_stem}.tif")
            if candidate.exists():
                LOGGER.warning(
                    "COG file missing (%s); falling back to source %s",
                    file_path,
                    candidate,
                )
                return str(candidate)
            # Also try .tiff extension
            candidate_tiff = p.with_name(f"{original_stem}.tiff")
            if candidate_tiff.exists():
                LOGGER.warning(
                    "COG file missing (%s); falling back to source %s",
                    file_path,
                    candidate_tiff,
                )
                return str(candidate_tiff)

        # Nothing found — return as-is so the error is visible
        LOGGER.warning("Registered asset file not found on disk: %s", file_path)
        return file_path

    @staticmethod
    def _serialize_asset(item: RasterAsset) -> dict[str, Any]:
        created_at = getattr(item, "created_at", None)
        tile_path = CatalogService._resolve_tile_path(item.file_path)
        return {
            "id": item.id,
            "file_name": item.file_name,
            "file_path": item.file_path,
            "kind": item.raster_kind.value,
            "crs": item.crs,
            "bounds_wkt": item.bounds_wkt,
            "tile_url": build_xyz_url(tile_path),
            "created_at": created_at.isoformat() if created_at else None,
        }
