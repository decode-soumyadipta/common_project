"""HTTP API client for the Desktop Ingestion Client.

This module provides ``IngestionApiClient``, the sole HTTP boundary between
the Desktop Ingestion Client (PySide6 UI) and the backend microservices.

Communication targets (Server 1 only):
- **Ingestion Service** (``INGESTION_SERVICE_URL``): file upload, status polling,
  health checks.
- **Tile Service** (``TILE_SERVICE_URL``): tile metadata and preview images for
  displaying ingested rasters.

The client reads both service URLs from the centralized
``src_new.shared.config.settings`` object, which in turn loads them from the
project-root ``.env`` file.  No URLs are hardcoded here.

Design-doc schemas implemented:
- ``UploadResponse``  — ``{raster_id, status, message, bbox}``
- ``IngestionStatus`` — ``{raster_id, status, progress, error}``

Requirements: 7.1, 7.3, 7.5
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Literal, Optional

import httpx
from pydantic import BaseModel, Field

from src_new.shared.config import settings
from src_new.shared.models.bounding_box import BoundingBox

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response schemas (mirrors design-doc / Ingestion Service routes.py)
# ---------------------------------------------------------------------------


class UploadResponse(BaseModel):
    """Response body for ``POST /upload`` on the Ingestion Service.

    Matches the design-doc specification:
        ``{raster_id, status, message, bbox}``
    """

    raster_id: str = Field(description="Original file name used as raster id.")
    status: Literal["processing", "cataloged", "failed"] = Field(
        description="Current ingestion status."
    )
    message: str = Field(description="Human-readable status message.")
    bbox: Optional[BoundingBox] = Field(
        default=None,
        description="Geographic bounding box of the raster in WGS 84 (EPSG:4326).",
    )


class IngestionStatus(BaseModel):
    """Response body for ``GET /status/{raster_id}`` on the Ingestion Service.

    Matches the design-doc specification:
        ``{raster_id, status, progress, error}``
    """

    raster_id: str = Field(description="Raster id (original file name).")
    status: str = Field(description="Current ingestion status string.")
    progress: float = Field(
        ge=0.0,
        le=1.0,
        description="Ingestion progress from 0.0 (queued) to 1.0 (complete).",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if ingestion failed, otherwise None.",
    )


class TileMetadata(BaseModel):
    """Response body for ``GET /metadata/{raster_id}`` on the Tile Service."""

    bounds: Optional[BoundingBox] = None
    minzoom: Optional[int] = None
    maxzoom: Optional[int] = None
    center: Optional[tuple[float, float]] = None


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------


class IngestionApiClient:
    """HTTP client for the Desktop Ingestion Client.

    Communicates exclusively with Server 1:
    - Ingestion Service (``INGESTION_SERVICE_URL``)
    - Tile Service (``TILE_SERVICE_URL``)

    All service URLs are read from ``src_new.shared.config.settings`` so that
    no URLs are hardcoded in this module (Requirement 4.5).

    Usage::

        from src_new.clients.desktop_ingestion.api_client import IngestionApiClient

        client = IngestionApiClient()
        response = client.upload_file("/path/to/raster.tif")
        status = client.get_status(response.raster_id)

    Requirements: 7.1, 7.3, 7.5
    """

    def __init__(
        self,
        ingestion_service_url: str | None = None,
        tile_service_url: str | None = None,
    ) -> None:
        """Initialise the client.

        Args:
            ingestion_service_url: Override for the Ingestion Service base URL.
                Defaults to ``settings.ingestion_service_url``.
            tile_service_url: Override for the Tile Service base URL.
                Defaults to ``settings.tile_service_url``.
        """
        self._ingestion_url = (
            ingestion_service_url or settings.ingestion_service_url
        ).rstrip("/")
        self._tile_url = (tile_service_url or settings.tile_service_url).rstrip("/")

        logger.debug(
            "IngestionApiClient initialised — ingestion=%s tile=%s",
            self._ingestion_url,
            self._tile_url,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def ingestion_service_url(self) -> str:
        """Base URL of the Ingestion Service."""
        return self._ingestion_url

    @property
    def tile_service_url(self) -> str:
        """Base URL of the Tile Service."""
        return self._tile_url

    # ------------------------------------------------------------------
    # Ingestion Service methods
    # ------------------------------------------------------------------

    def upload_file(
        self,
        file_path: str | os.PathLike,
        extra_metadata: dict[str, Any] | None = None,
        timeout: float = 300.0,
    ) -> UploadResponse:
        """Upload a geospatial raster file to the Ingestion Service.

        Sends a multipart ``POST /upload`` request to the Ingestion Service.
        The file is streamed from disk so that large rasters (multi-GB) do not
        need to be loaded into memory.

        Args:
            file_path:      Local path to the raster file (GeoTIFF, JPEG2000,
                            or MBTiles).
            extra_metadata: Optional dict of additional metadata fields to
                            include in the multipart form data.
            timeout:        Request timeout in seconds (default 300 s for large
                            files).

        Returns:
            ``UploadResponse`` with ``raster_id``, ``status``, ``message``,
            and optional ``bbox``.

        Raises:
            httpx.HTTPStatusError: If the server returns a 4xx/5xx response.
            httpx.HTTPError:       On network-level failures.
            FileNotFoundError:     If ``file_path`` does not exist.

        Requirements: 7.1, 7.3
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        logger.info(
            "Uploading '%s' (%.2f MB) to %s/upload",
            path.name,
            path.stat().st_size / (1024 ** 2),
            self._ingestion_url,
        )

        with path.open("rb") as fh:
            files = {"file": (path.name, fh, _mime_type_for(path))}
            data: dict[str, Any] = {}
            if extra_metadata:
                import json
                # Extract tags and description to send as separate form fields
                tags_value = extra_metadata.pop("tags", None)
                description_value = extra_metadata.pop("description", None)
                if tags_value:
                    if isinstance(tags_value, list):
                        data["tags"] = ", ".join(tags_value)
                    else:
                        data["tags"] = str(tags_value)
                if description_value:
                    data["description"] = str(description_value)
                # Remaining metadata (sidecar files) goes as JSON
                if extra_metadata:
                    data["metadata"] = json.dumps(extra_metadata)

            response = httpx.post(
                f"{self._ingestion_url}/upload",
                files=files,
                data=data if data else None,
                timeout=timeout,
            )

        response.raise_for_status()
        payload = response.json()
        logger.info(
            "Upload complete — raster_id=%s status=%s",
            payload.get("raster_id"),
            payload.get("status"),
        )
        return UploadResponse(**payload)

    def get_status(self, raster_id: str, timeout: float = 10.0) -> IngestionStatus:
        """Poll the ingestion status for a previously uploaded raster.

        Sends ``GET /status/{raster_id}`` to the Ingestion Service.

        Args:
            raster_id: UUID returned by a prior ``upload_file()`` call.
            timeout:   Request timeout in seconds (default 10 s).

        Returns:
            ``IngestionStatus`` with ``status``, ``progress`` (0.0–1.0), and
            optional ``error``.

        Raises:
            httpx.HTTPStatusError: 404 if the raster_id is unknown; other
                                   4xx/5xx on server errors.
            httpx.HTTPError:       On network-level failures.

        Requirements: 7.1, 7.3
        """
        logger.debug("GET /status/%s", raster_id)
        response = httpx.get(
            f"{self._ingestion_url}/status/{raster_id}",
            timeout=timeout,
        )
        response.raise_for_status()
        return IngestionStatus(**response.json())

    def get_health(self, timeout: float = 5.0) -> dict[str, Any]:
        """Check the health of the Ingestion Service.

        Sends ``GET /health`` to the Ingestion Service.

        Args:
            timeout: Request timeout in seconds (default 5 s).

        Returns:
            Dict with keys ``status`` (``"healthy"`` | ``"degraded"`` |
            ``"unhealthy"``), ``database`` (bool), and ``disk_space_gb``
            (float).

        Raises:
            httpx.HTTPError: On network-level failures or non-2xx responses.

        Requirements: 7.1
        """
        logger.debug("GET /health → %s", self._ingestion_url)
        response = httpx.get(f"{self._ingestion_url}/health", timeout=timeout)
        response.raise_for_status()
        return response.json()

    def ingestion_service_ready(self) -> bool:
        """Return ``True`` if the Ingestion Service is reachable and healthy.

        Convenience wrapper around ``get_health()`` that swallows network
        errors and returns a simple boolean.  Useful for UI readiness checks.

        Requirements: 7.1
        """
        try:
            health = self.get_health(timeout=3.0)
            logger.debug("Ingestion Service health: %s", health)
            return health.get("status") in {"healthy", "degraded"}
        except httpx.HTTPError as exc:
            logger.warning(
                "Ingestion Service health check failed url=%s error=%s",
                f"{self._ingestion_url}/health",
                exc,
            )
            return False

    def list_assets(self, timeout: float = 10.0) -> list[dict[str, Any]]:
        """Return cataloged assets ordered by upload date (newest first)."""
        logger.debug("GET /assets → %s", self._ingestion_url)
        response = httpx.get(f"{self._ingestion_url}/assets", timeout=timeout)
        response.raise_for_status()
        return response.json()

    def delete_assets(
        self, raster_ids: list[str], timeout: float = 30.0
    ) -> dict[str, Any]:
        """Delete cataloged assets by raster_id."""
        logger.debug("DELETE /assets → %s (%d ids)", self._ingestion_url, len(raster_ids))
        response = httpx.request(
            "DELETE",
            f"{self._ingestion_url}/assets",
            json={"raster_ids": raster_ids},
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    # ------------------------------------------------------------------
    # Tile Service methods
    # ------------------------------------------------------------------

    def get_tile_metadata(
        self, raster_id: str, timeout: float = 10.0
    ) -> dict[str, Any]:
        """Retrieve tile metadata for a cataloged raster from the Tile Service.

        Sends ``GET /metadata/{raster_id}`` to the Tile Service.

        Args:
            raster_id: UUID of the cataloged raster.
            timeout:   Request timeout in seconds (default 10 s).

        Returns:
            Dict with ``bounds``, ``minzoom``, ``maxzoom``, and ``center``.

        Raises:
            httpx.HTTPStatusError: 404 if the raster is not found.
            httpx.HTTPError:       On network-level failures.

        Requirements: 7.3
        """
        logger.debug("GET tile metadata for raster_id=%s", raster_id)
        response = httpx.get(
            f"{self._tile_url}/metadata/{raster_id}",
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    def get_tile_service_health(self, timeout: float = 5.0) -> dict[str, Any]:
        """Check the health of the Tile Service.

        Sends ``GET /health`` to the Tile Service.

        Args:
            timeout: Request timeout in seconds (default 5 s).

        Returns:
            Health dict from the Tile Service.

        Raises:
            httpx.HTTPError: On network-level failures or non-2xx responses.

        Requirements: 7.3
        """
        logger.debug("GET /health → %s", self._tile_url)
        response = httpx.get(f"{self._tile_url}/health", timeout=timeout)
        response.raise_for_status()
        return response.json()

    def tile_service_ready(self) -> bool:
        """Return ``True`` if the Tile Service is reachable and healthy.

        Requirements: 7.3
        """
        try:
            health = self.get_tile_service_health(timeout=3.0)
            logger.debug("Tile Service health: %s", health)
            return health.get("status") in {"healthy", "degraded"}
        except httpx.HTTPError as exc:
            logger.warning(
                "Tile Service health check failed url=%s error=%s",
                f"{self._tile_url}/health",
                exc,
            )
            return False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _mime_type_for(path: Path) -> str:
    """Return a MIME type string for a geospatial raster file.

    Args:
        path: Path to the raster file.

    Returns:
        MIME type string suitable for the ``Content-Type`` header.
    """
    ext = path.suffix.lower()
    _mime_map: dict[str, str] = {
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
        ".jp2": "image/jp2",
        ".j2k": "image/jp2",
        ".mbtiles": "application/x-sqlite3",
    }
    return _mime_map.get(ext, "application/octet-stream")


__all__ = [
    "IngestionApiClient",
    "UploadResponse",
    "IngestionStatus",
    "TileMetadata",
]
