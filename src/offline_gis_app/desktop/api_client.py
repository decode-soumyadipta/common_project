from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from offline_gis_app.config.settings import settings


class DesktopApiClient:
    def __init__(self, base_url: str | None = None):
        self._base_url = (base_url or f"http://{settings.api_host}:{settings.api_port}").rstrip("/")
        self._titiler_base = settings.titiler_base_url.rstrip("/")

    def register_raster(self, path: str) -> dict[str, Any]:
        response = httpx.post(f"{self._base_url}/ingest/register", json={"path": path}, timeout=30.0)
        response.raise_for_status()
        return response.json()

    def list_assets(self) -> list[dict[str, Any]]:
        response = httpx.get(f"{self._base_url}/search/assets", timeout=15.0)
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
        response = httpx.post(f"{self._base_url}/profile/elevation", json=payload, timeout=60.0)
        response.raise_for_status()
        return response.json()

    def titiler_ready(self) -> bool:
        try:
            response = httpx.get(f"{self._titiler_base}/healthz", timeout=3.0)
            return response.is_success
        except httpx.HTTPError:
            return False

    def get_tilejson(self, file_path: str) -> dict[str, Any]:
        encoded_path = quote(file_path, safe="/:")
        endpoint = (
            f"{self._titiler_base}/cog/{settings.titiler_tile_matrix_set_id}/tilejson.json"
            f"?url=file://{encoded_path}"
        )
        response = httpx.get(endpoint, timeout=20.0)
        response.raise_for_status()
        return response.json()

    def get_cog_info(self, file_path: str) -> dict[str, Any]:
        encoded_path = quote(file_path, safe="/:")
        endpoint = f"{self._titiler_base}/cog/info?url=file://{encoded_path}"
        response = httpx.get(endpoint, timeout=20.0)
        response.raise_for_status()
        return response.json()

    def get_cog_statistics(self, file_path: str) -> dict[str, Any]:
        encoded_path = quote(file_path, safe="/:")
        endpoint = f"{self._titiler_base}/cog/statistics?url=file://{encoded_path}"
        response = httpx.get(endpoint, timeout=30.0)
        response.raise_for_status()
        return response.json()
