"""Unit tests for the Desktop Ingestion Client API client.

This module provides unit tests for the ``IngestionApiClient`` class, which
handles HTTP communication with the Ingestion Service and Tile Service.

Requirements: 7.1, 7.3, 7.5
"""
from __future__ import annotations

import pytest
from unittest.mock import Mock, patch
from pathlib import Path

from src_new.clients.desktop_ingestion.api_client import (
    IngestionApiClient,
    UploadResponse,
    IngestionStatus,
)


class TestIngestionApiClient:
    """Test suite for IngestionApiClient."""

    def test_init_default_urls(self) -> None:
        """Test that the client initializes with default URLs from settings."""
        client = IngestionApiClient()
        assert client.ingestion_service_url
        assert client.tile_service_url
        assert isinstance(client.ingestion_service_url, str)
        assert isinstance(client.tile_service_url, str)

    def test_init_custom_urls(self) -> None:
        """Test that the client accepts custom service URLs."""
        custom_ingestion = "http://custom-ingestion:8001"
        custom_tile = "http://custom-tile:8002"
        client = IngestionApiClient(
            ingestion_service_url=custom_ingestion,
            tile_service_url=custom_tile,
        )
        assert client.ingestion_service_url == custom_ingestion
        assert client.tile_service_url == custom_tile

    @patch("src_new.clients.desktop_ingestion.api_client.httpx.post")
    def test_upload_file_success(self, mock_post: Mock, tmp_path: Path) -> None:
        """Test successful file upload."""
        # Create a temporary test file
        test_file = tmp_path / "test.tif"
        test_file.write_bytes(b"fake geotiff data")

        # Mock the HTTP response
        mock_response = Mock()
        mock_response.json.return_value = {
            "raster_id": "test-raster-123",
            "status": "processing",
            "message": "Upload successful",
            "bbox": {
                "min_lon": -180.0,
                "min_lat": -90.0,
                "max_lon": 180.0,
                "max_lat": 90.0,
            },
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        # Test upload
        client = IngestionApiClient()
        response = client.upload_file(test_file)

        assert isinstance(response, UploadResponse)
        assert response.raster_id == "test-raster-123"
        assert response.status == "processing"
        assert response.message == "Upload successful"
        assert response.bbox is not None

    @patch("src_new.clients.desktop_ingestion.api_client.httpx.post")
    def test_upload_file_not_found(self, mock_post: Mock) -> None:
        """Test upload with non-existent file."""
        client = IngestionApiClient()
        with pytest.raises(FileNotFoundError):
            client.upload_file("/nonexistent/file.tif")

    @patch("src_new.clients.desktop_ingestion.api_client.httpx.get")
    def test_get_status_success(self, mock_get: Mock) -> None:
        """Test successful status retrieval."""
        # Mock the HTTP response
        mock_response = Mock()
        mock_response.json.return_value = {
            "raster_id": "test-raster-123",
            "status": "cataloged",
            "progress": 1.0,
            "error": None,
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Test status retrieval
        client = IngestionApiClient()
        status = client.get_status("test-raster-123")

        assert isinstance(status, IngestionStatus)
        assert status.raster_id == "test-raster-123"
        assert status.status == "cataloged"
        assert status.progress == 1.0
        assert status.error is None

    @patch("src_new.clients.desktop_ingestion.api_client.httpx.get")
    def test_get_health_success(self, mock_get: Mock) -> None:
        """Test successful health check."""
        # Mock the HTTP response
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "healthy",
            "database": True,
            "disk_space_gb": 500.0,
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Test health check
        client = IngestionApiClient()
        health = client.get_health()

        assert health["status"] == "healthy"
        assert health["database"] is True
        assert health["disk_space_gb"] == 500.0

    @patch("src_new.clients.desktop_ingestion.api_client.httpx.get")
    def test_ingestion_service_ready_healthy(self, mock_get: Mock) -> None:
        """Test service readiness check when service is healthy."""
        # Mock the HTTP response
        mock_response = Mock()
        mock_response.json.return_value = {"status": "healthy"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Test readiness
        client = IngestionApiClient()
        assert client.ingestion_service_ready() is True

    @patch("src_new.clients.desktop_ingestion.api_client.httpx.get")
    def test_ingestion_service_ready_unhealthy(self, mock_get: Mock) -> None:
        """Test service readiness check when service is unhealthy."""
        # Mock the HTTP response
        mock_response = Mock()
        mock_response.json.return_value = {"status": "unhealthy"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Test readiness
        client = IngestionApiClient()
        assert client.ingestion_service_ready() is False

    @patch("src_new.clients.desktop_ingestion.api_client.httpx.get")
    def test_ingestion_service_ready_network_error(self, mock_get: Mock) -> None:
        """Test service readiness check when network error occurs."""
        # Mock network error
        import httpx
        mock_get.side_effect = httpx.ConnectError("Connection refused")

        # Test readiness
        client = IngestionApiClient()
        assert client.ingestion_service_ready() is False

    @patch("src_new.clients.desktop_ingestion.api_client.httpx.get")
    def test_get_tile_metadata_success(self, mock_get: Mock) -> None:
        """Test successful tile metadata retrieval."""
        # Mock the HTTP response
        mock_response = Mock()
        mock_response.json.return_value = {
            "bounds": {
                "min_lon": -180.0,
                "min_lat": -90.0,
                "max_lon": 180.0,
                "max_lat": 90.0,
            },
            "minzoom": 0,
            "maxzoom": 18,
            "center": [0.0, 0.0],
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Test metadata retrieval
        client = IngestionApiClient()
        metadata = client.get_tile_metadata("test-raster-123")

        assert "bounds" in metadata
        assert metadata["minzoom"] == 0
        assert metadata["maxzoom"] == 18
        assert metadata["center"] == [0.0, 0.0]

    @patch("src_new.clients.desktop_ingestion.api_client.httpx.get")
    def test_tile_service_ready_healthy(self, mock_get: Mock) -> None:
        """Test tile service readiness check when service is healthy."""
        # Mock the HTTP response
        mock_response = Mock()
        mock_response.json.return_value = {"status": "healthy"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Test readiness
        client = IngestionApiClient()
        assert client.tile_service_ready() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
