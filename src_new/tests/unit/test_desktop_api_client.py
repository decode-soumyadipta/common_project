from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src_new.clients.desktop_search.api_client import DesktopApiClient


def test_desktop_api_client_resolves_cog_sibling_if_present(tmp_path: Path) -> None:
    client = DesktopApiClient()
    
    # Sibling does not exist
    j2k_path = tmp_path / "scene.j2k"
    j2k_path.write_bytes(b"some-data")
    
    resolved = client._resolve_local_path(str(j2k_path))
    assert resolved == str(j2k_path)
    
    # Sibling exists
    cog_path = tmp_path / "scene.cog.tif"
    cog_path.write_bytes(b"some-cog-data")
    
    resolved_with_sibling = client._resolve_local_path(str(j2k_path))
    assert resolved_with_sibling == str(cog_path.resolve())


@patch("src_new.clients.desktop_search.api_client.httpx.get")
def test_desktop_api_client_calls_resolve_on_titiler_endpoints(mock_get: Mock, tmp_path: Path) -> None:
    client = DesktopApiClient()
    
    # Create files
    j2k_path = tmp_path / "scene.j2k"
    j2k_path.write_bytes(b"some-data")
    cog_path = tmp_path / "scene.cog.tif"
    cog_path.write_bytes(b"some-cog-data")
    
    # Mock the HTTP response
    mock_response = Mock()
    mock_response.json.return_value = {"status": "ok"}
    mock_response.raise_for_status = Mock()
    mock_get.return_value = mock_response
    
    # Call get_tilejson with the .j2k file
    client.get_tilejson(str(j2k_path))
    
    # Check that mock_get was called with the cog.tif path in query parameter, not .j2k!
    args, kwargs = mock_get.call_args
    url_called = args[0]
    expected_path = str(cog_path.resolve()).replace("\\", "/")
    assert expected_path in url_called
    assert "scene.j2k" not in url_called
