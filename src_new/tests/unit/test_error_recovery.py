from __future__ import annotations

import pytest
from unittest.mock import MagicMock
import numpy as np
from pathlib import Path
from contextlib import contextmanager

def test_cog_converter_lock():
    from src_new.services.ingestion.gdal_pipelines.cog_converter import CogConverter
    # Verify CogConverter has a class-level Semaphore lock
    assert hasattr(CogConverter, "_lock")
    from threading import Semaphore
    assert isinstance(CogConverter._lock, Semaphore)

def test_tile_endpoint_reproject_error_fallback(monkeypatch):
    import src_new.services.tile_serving.tile_endpoints as tile_endpoints
    import rasterio
    
    # Mock dependencies
    monkeypatch.setattr(tile_endpoints, "_RASTERIO_AVAILABLE", True)
    monkeypatch.setattr(tile_endpoints, "_PIL_AVAILABLE", True)
    
    # Mock rasterio.open context manager
    mock_src = MagicMock()
    mock_src.count = 3
    mock_src.bounds = MagicMock()
    mock_src.crs = "EPSG:3857"
    mock_src.width = 100
    mock_src.height = 100
    
    @contextmanager
    def fake_open(*args, **kwargs):
        yield mock_src
        
    monkeypatch.setattr(rasterio, "open", fake_open)
    monkeypatch.setattr(rasterio, "band", lambda src, band_idx: MagicMock())
    
    # Mock calculate_default_transform
    monkeypatch.setattr(
        tile_endpoints,
        "calculate_default_transform",
        lambda *args, **kwargs: (None, 100, 100)
    )
    
    # Mock reproject to raise an exception
    reproject_calls = []
    def fake_reproject(*args, **kwargs):
        reproject_calls.append(args)
        raise RuntimeError("GDAL signalled an error: offset at 12345")
        
    monkeypatch.setattr(tile_endpoints, "reproject", fake_reproject)
    
    # Call the private helper
    tile_data = tile_endpoints._read_tile_from_raster(
        raster_path=Path("dummy.tif"),
        z=1,
        x=1,
        y=1,
        tile_size=256
    )
    
    # Verify it handled the error and returned 256x256 zeros (4 bands: RGBA)
    assert tile_data.shape == (4, 256, 256)
    assert np.all(tile_data == 0)
    assert len(reproject_calls) == 3

def test_preview_endpoint_read_error_fallback(monkeypatch):
    import src_new.services.tile_serving.tile_endpoints as tile_endpoints
    import rasterio
    
    monkeypatch.setattr(tile_endpoints, "_RASTERIO_AVAILABLE", True)
    
    mock_src = MagicMock()
    mock_src.count = 3
    
    read_calls = []
    def fake_read(*args, **kwargs):
        read_calls.append(args)
        raise RuntimeError("GDAL signalled an error: offset at 12345")
    mock_src.read = fake_read
    
    @contextmanager
    def fake_open(*args, **kwargs):
        yield mock_src
        
    monkeypatch.setattr(rasterio, "open", fake_open)
    
    preview_data = tile_endpoints._read_preview_from_raster(
        raster_path=Path("dummy.tif"),
        preview_size=512
    )
    
    assert preview_data.shape == (4, 512, 512)
    assert np.all(preview_data == 0)
    assert len(read_calls) == 3

def test_elevation_profile_sample_error_fallback(monkeypatch):
    import src_new.services.query.api.routes as query_routes
    from src_new.services.query.api.routes import ElevationProfilePoint
    import rasterio
    import os
    
    mock_src = MagicMock()
    mock_src.crs = "EPSG:32644"
    mock_src.nodata = -9999
    
    def fake_sample(*args, **kwargs):
        raise RuntimeError("GDAL signalled an error: offset at 12345")
    mock_src.sample = fake_sample
    
    @contextmanager
    def fake_open(*args, **kwargs):
        yield mock_src
        
    monkeypatch.setattr(rasterio, "open", fake_open)
    monkeypatch.setattr(os.path, "exists", lambda path: True)
    
    line_points = [
        ElevationProfilePoint(lon=70.0, lat=30.0),
        ElevationProfilePoint(lon=70.1, lat=30.1)
    ]
    
    values = query_routes._sample_elevation_profile(
        path="dummy.tif",
        line_points=line_points,
        samples=10
    )
    
    # Verify it handled the error and returned 10 None values
    assert len(values) == 10
    assert all(v is None for v in values)
