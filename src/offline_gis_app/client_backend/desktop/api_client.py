from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from offline_gis_app.config.settings import settings


class DesktopApiClient:
    """HTTP client wrapper for desktop calls to local API and TiTiler endpoints."""

    def __init__(self, base_url: str | None = None):
        api_host = settings.api_host
        if api_host in {"0.0.0.0", "::"}:
            api_host = "127.0.0.1"
        default_base = (
            settings.server_api_base_url or f"http://{api_host}:{settings.api_port}"
        )
        self._base_url = (base_url or default_base).rstrip("/")
        self._titiler_base = settings.titiler_base_url.rstrip("/")

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def titiler_base_url(self) -> str:
        return self._titiler_base

    def api_ready(self) -> bool:
        try:
            response = httpx.get(f"{self._base_url}/health", timeout=2.0)
            return response.is_success
        except httpx.HTTPError:
            return False

    def register_raster(self, path: str) -> dict[str, Any]:
        response = httpx.post(
            f"{self._base_url}/ingest/register", json={"path": path}, timeout=30.0
        )
        response.raise_for_status()
        return response.json()

    def list_assets(self) -> list[dict[str, Any]]:
        response = httpx.get(f"{self._base_url}/search/assets", timeout=15.0)
        response.raise_for_status()
        return response.json()

    def search_assets_by_point(self, lon: float, lat: float) -> list[dict[str, Any]]:
        response = httpx.post(
            f"{self._base_url}/search/point",
            json={"lon": lon, "lat": lat},
            timeout=20.0,
        )
        response.raise_for_status()
        return response.json()

    def search_assets_by_bbox(
        self, west: float, south: float, east: float, north: float
    ) -> list[dict[str, Any]]:
        response = httpx.post(
            f"{self._base_url}/search/bbox",
            json={"west": west, "south": south, "east": east, "north": north},
            timeout=20.0,
        )
        response.raise_for_status()
        return response.json()

    def search_assets_by_polygon(
        self, points: list[tuple[float, float]], buffer_meters: float = 0.0
    ) -> list[dict[str, Any]]:
        payload = {
            "points": [{"lon": lon, "lat": lat} for lon, lat in points],
            "buffer_meters": buffer_meters,
        }
        response = httpx.post(
            f"{self._base_url}/search/polygon", json=payload, timeout=30.0
        )
        response.raise_for_status()
        return response.json()

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

    def get_tilejson(self, file_path: str) -> dict[str, Any]:
        encoded_path = quote(self._to_file_url(file_path), safe="/:")
        endpoint = (
            f"{self._titiler_base}/cog/{settings.titiler_tile_matrix_set_id}/tilejson.json"
            f"?url={encoded_path}"
        )
        response = httpx.get(endpoint, timeout=20.0)
        response.raise_for_status()
        return response.json()

    def get_cog_info(self, file_path: str) -> dict[str, Any]:
        encoded_path = quote(self._to_file_url(file_path), safe="/:")
        endpoint = f"{self._titiler_base}/cog/info?url={encoded_path}"
        response = httpx.get(endpoint, timeout=20.0)
        response.raise_for_status()
        return response.json()

    def get_cog_statistics(self, file_path: str) -> dict[str, Any]:
        encoded_path = quote(self._to_file_url(file_path), safe="/:")
        endpoint = f"{self._titiler_base}/cog/statistics?url={encoded_path}"
        response = httpx.get(endpoint, timeout=30.0)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _to_file_url(file_path: str) -> str:
        normalized = file_path.strip().replace("\\", "/")
        if not normalized:
            raise ValueError("file_path cannot be empty")

        if normalized.startswith("//"):
            tail = normalized[2:]
            while "//" in tail:
                tail = tail.replace("//", "/")
            normalized = "//" + tail
        else:
            while "//" in normalized:
                normalized = normalized.replace("//", "/")

        if normalized.startswith("file://"):
            return normalized

        if len(normalized) >= 3 and normalized[1] == ":" and normalized[2] == "/":
            return f"file:///{normalized}"

        if normalized.startswith("//"):
            return f"file:{normalized}"

        if normalized.startswith("/"):
            return f"file://{normalized}"

        return f"file:///{normalized}"
