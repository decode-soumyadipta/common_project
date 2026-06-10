from __future__ import annotations

import logging
import platform
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from src_new.shared.config import settings

_logger = logging.getLogger(__name__)


class DesktopApiClient:
    """HTTP client wrapper for desktop calls to Query and Tile services.
    
    In the new microservices architecture:
    - Query Service: http://127.0.0.1:8003 (spatial queries)
    - Tile Service: http://127.0.0.1:8002 (tile serving)
    - Ingestion Service: http://127.0.0.1:8001 (data upload)
    """

    def __init__(self, base_url: str | None = None):
        self._base_url = (base_url or settings.query_service_url).rstrip("/")
        tile_base = settings.tile_service_url.rstrip("/")
        if not tile_base.endswith("/titiler"):
            tile_base = f"{tile_base}/titiler"
        self._titiler_base = tile_base
        self._ingestion_url = settings.ingestion_service_url.rstrip("/")

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def titiler_base_url(self) -> str:
        return self._titiler_base

    @property
    def tile_service_base_url(self) -> str:
        return settings.tile_service_url.rstrip("/")

    def api_ready(self) -> bool:
        try:
            response = httpx.get(f"{self._base_url}/health", timeout=2.0)
            return response.is_success
        except httpx.HTTPError:
            return False

    def register_raster(self, path: str) -> dict[str, Any]:
        # In new architecture, registration goes to Ingestion Service
        response = httpx.post(
            f"{self._ingestion_url}/ingest/register", json={"path": path}, timeout=30.0
        )
        response.raise_for_status()
        return response.json()

    def list_assets(self) -> list[dict[str, Any]]:
        # In new architecture, asset listing comes from Query Service
        response = httpx.get(f"{self._base_url}/rasters", timeout=15.0)
        response.raise_for_status()
        result = response.json()
        # Extract the rasters list from the QueryResult response
        return result.get("rasters", []) if isinstance(result, dict) else []

    def search_assets_by_point(self, lon: float, lat: float) -> list[dict[str, Any]]:
        payload = {"lon": lon, "lat": lat}
        _logger.debug("API POST %s/query/point payload=%s", self._base_url, payload)
        response = httpx.post(
            f"{self._base_url}/query/point",
            json=payload,
            timeout=20.0,
        )
        response.raise_for_status()
        result = response.json()
        rasters = result.get("rasters", []) if isinstance(result, dict) else []
        _logger.info("API search_assets_by_point returned %d rasters for %s,%s", len(rasters), lon, lat)
        return rasters

    def search_assets_by_bbox(
        self, west: float, south: float, east: float, north: float
    ) -> list[dict[str, Any]]:
        response = httpx.post(
            f"{self._base_url}/query/bbox",
            json={
                "min_lon": west,
                "min_lat": south,
                "max_lon": east,
                "max_lat": north,
            },
            timeout=20.0,
        )
        response.raise_for_status()
        result = response.json()
        return result.get("rasters", []) if isinstance(result, dict) else []

    def search_assets_by_polygon(
        self, points: list[tuple[float, float]], buffer_meters: float = 0.0
    ) -> list[dict[str, Any]]:
        payload = {
            "points": [{"lon": lon, "lat": lat} for lon, lat in points],
            "buffer_meters": buffer_meters,
        }
        _logger.debug("API POST %s/search/polygon payload_points=%d buffer=%s", self._base_url, len(points), buffer_meters)
        response = httpx.post(
            f"{self._base_url}/search/polygon", json=payload, timeout=30.0
        )
        response.raise_for_status()
        result = response.json()
        rasters = result.get("rasters", []) if isinstance(result, dict) else []
        _logger.info("API search_assets_by_polygon returned %d rasters for buffer=%s", len(rasters), buffer_meters)
        return rasters

    def enqueue_ingest_job(self, paths: list[str]) -> dict[str, Any]:
        response = httpx.post(
            f"{self._base_url}/ingest/queue", json={"paths": paths}, timeout=30.0
        )
        response.raise_for_status()
        return response.json()

    def get_ingest_job(self, job_id: str) -> dict[str, Any]:
        response = httpx.get(f"{self._base_url}/ingest/jobs/{job_id}", timeout=20.0)
        response.raise_for_status()
        return response.json()

    def resume_ingest_job(self, job_id: str) -> dict[str, Any]:
        response = httpx.post(
            f"{self._base_url}/ingest/jobs/{job_id}/resume", timeout=20.0
        )
        response.raise_for_status()
        return response.json()

    def delete_asset(self, asset_id: str) -> bool:
        """Delete an asset from the catalog and database."""
        try:
            response = httpx.delete(
                f"{self._base_url}/search/assets/{asset_id}", timeout=30.0
            )
            response.raise_for_status()
            return True
        except httpx.HTTPError:
            return False

    def extract_profile(
        self,
        path: str,
        line_points: list[tuple[float, float]],
        samples: int = 200,
    ) -> dict[str, Any]:
        payload = {
            "path": path,
            "line_points": [{"lon": lon, "lat": lat} for lon, lat in line_points],
            "samples": samples,
        }
        response = httpx.post(
            f"{self._base_url}/profile/elevation", json=payload, timeout=60.0
        )
        response.raise_for_status()
        return response.json()

    def _resolve_local_path(self, file_path: str) -> str:
        """Resolve a local file path to its COG sibling if present."""
        path_str = file_path.strip().replace("\\", "/")
        if path_str.startswith("file:///"):
            path_str = path_str[8:]
        elif path_str.startswith("file://"):
            path_str = path_str[7:]
        elif path_str.startswith("file:"):
            path_str = path_str[5:]
            
        try:
            p = Path(path_str)
            cog_sibling = p.parent / f"{p.stem}.cog.tif"
            if cog_sibling.is_file():
                return str(cog_sibling.resolve())
        except Exception:
            pass
        return file_path

    def get_tilejson(self, file_path: str) -> dict[str, Any]:
        resolved_path = self._resolve_local_path(file_path)
        encoded_path = quote(self._to_file_url(resolved_path), safe="/:")
        endpoint = (
            f"{self._titiler_base}/cog/{settings.titiler_tile_matrix_set_id}/tilejson.json"
            f"?url={encoded_path}"
        )
        response = httpx.get(endpoint, timeout=20.0)
        response.raise_for_status()
        return response.json()

    def get_cog_info(self, file_path: str) -> dict[str, Any]:
        resolved_path = self._resolve_local_path(file_path)
        encoded_path = quote(self._to_file_url(resolved_path), safe="/:")
        endpoint = f"{self._titiler_base}/cog/info?url={encoded_path}"
        response = httpx.get(endpoint, timeout=20.0)
        response.raise_for_status()
        return response.json()

    def get_cog_statistics(self, file_path: str) -> dict[str, Any]:
        resolved_path = self._resolve_local_path(file_path)
        encoded_path = quote(self._to_file_url(resolved_path), safe="/:")
        endpoint = f"{self._titiler_base}/cog/statistics?url={encoded_path}"
        response = httpx.get(endpoint, timeout=30.0)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _to_file_url(file_path: str) -> str:
        """Convert a local file path to a URL suitable for TiTiler's GDAL backend.

        On Windows, GDAL/rasterio cannot reliably open ``file:///C:/path with spaces/``
        URLs.  The raw ``C:/...`` form (the same approach used by TiTilerUrlPolicy)
        works correctly because GDAL treats a leading drive letter as an absolute
        Windows path without needing the ``file://`` scheme.

        On macOS/Linux, ``file:///abs/path`` is standard and works fine.
        UNC network paths (``//server/share``) keep the ``file:`` scheme on all
        platforms.
        """
        normalized = file_path.strip().replace("\\", "/")
        if not normalized:
            raise ValueError("file_path cannot be empty")

        # Strip any existing file:// prefix so we start from a clean path.
        if normalized.startswith("file:///"):
            normalized = normalized[8:]
        elif normalized.startswith("file://"):
            normalized = normalized[7:]
        elif normalized.startswith("file:"):
            normalized = normalized[5:]

        # Collapse accidental double-slashes (preserve UNC ``//server/share``).
        if normalized.startswith("//"):
            tail = normalized[2:]
            while "//" in tail:
                tail = tail.replace("//", "/")
            normalized = "//" + tail
        else:
            while "//" in normalized:
                normalized = normalized.replace("//", "/")

        # Windows absolute path: ``C:/...`` On Windows: return the raw path — GDAL handles it natively and spaces are safe because the caller will percent-encode the whole string.
        if len(normalized) >= 3 and normalized[1] == ":" and normalized[2] == "/":
            if platform.system() == "Windows":
                return normalized  # e.g. "C:/Users/Foo Bar/data.tif"
            return f"file:///{normalized}"  # macOS/Linux cross-test compatibility

        # UNC network path: ``//server/share/...``
        if normalized.startswith("//"):
            return f"file:{normalized}"

        # Absolute POSIX path: ``/abs/path``
        if normalized.startswith("/"):
            return f"file://{normalized}"

        # Relative or unknown — best-effort.
        return f"file:///{normalized}"
