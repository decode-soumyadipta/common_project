from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock


from src_new.services.ingestion.gdal_pipelines.cog_converter import CogConverter
from src_new.shared.config import settings


def test_cog_converter_successful_conversion(monkeypatch, tmp_path: Path) -> None:
    # Setup paths
    source_path = tmp_path / "scene.tif"
    source_path.write_bytes(b"fake-tiff-content")
    
    cog_path = tmp_path / "scene.cog.tif"
    temp_cog_path = tmp_path / "scene.cog.tif.tmp"

    # Mock settings to enable COG conversion
    monkeypatch.setattr(settings, "ingest_enable_cog_conversion", True)
    monkeypatch.setattr(settings, "ingest_cog_overwrite", True)

    # Mock looks_like_cog to return False
    monkeypatch.setattr(CogConverter, "_looks_like_cog", lambda self, p: False)

    # Mock rasterio functions directly
    import rasterio
    import rasterio.shutil
    from contextlib import contextmanager

    mock_src = MagicMock()
    
    @contextmanager
    def fake_open(path, mode="r", *args, **kwargs):
        yield mock_src

    def fake_rio_copy(src, dst, **kwargs):
        # rio_copy should write to temp_cog_path
        assert Path(dst) == temp_cog_path
        # Simulate writing the file
        Path(dst).write_bytes(b"converted-cog-content")

    monkeypatch.setattr(rasterio, "open", fake_open)
    monkeypatch.setattr(rasterio.shutil, "copy", fake_rio_copy)

    converter = CogConverter()
    result = converter.convert(source_path)

    assert result.converted is True
    assert result.working_path == cog_path
    assert cog_path.exists()
    assert cog_path.read_bytes() == b"converted-cog-content"
    assert not temp_cog_path.exists()


def test_cog_converter_fallback_cleans_up_temp_on_failure(monkeypatch, tmp_path: Path) -> None:
    source_path = tmp_path / "scene.tif"
    source_path.write_bytes(b"fake-tiff-content")
    
    cog_path = tmp_path / "scene.cog.tif"
    temp_cog_path = tmp_path / "scene.cog.tif.tmp"

    # Mock settings to enable COG conversion
    monkeypatch.setattr(settings, "ingest_enable_cog_conversion", True)
    monkeypatch.setattr(settings, "ingest_cog_overwrite", True)
    monkeypatch.setattr(CogConverter, "_looks_like_cog", lambda self, p: False)

    import rasterio
    import rasterio.shutil
    from contextlib import contextmanager

    # Force all attempts to fail Attempt 1 (rio_copy) raises an error
    def failing_rio_copy(src, dst, **kwargs):
        # Write temporary file to check if it gets cleaned up
        Path(dst).write_bytes(b"partial-cog-content")
        raise RuntimeError("rasterio failure")

    mock_src = MagicMock()
    mock_src.profile = {"driver": "GTiff", "count": 1, "dtypes": ["uint8"]}
    mock_src.block_windows.return_value = []
    
    @contextmanager
    def fake_open(path, mode="r", *args, **kwargs):
        if mode == "w" and str(path) == str(temp_cog_path):
            # Create the temp file first to simulate partial output
            Path(path).write_bytes(b"partial-fallback-content")
            raise RuntimeError("fallback write failure")
        yield mock_src

    monkeypatch.setattr(rasterio, "open", fake_open)
    monkeypatch.setattr(rasterio.shutil, "copy", failing_rio_copy)

    converter = CogConverter()
    result = converter.convert(source_path)

    # Verify that the final converted is False and target paths are cleaned up
    assert result.converted is False
    assert result.working_path == source_path.resolve()
    assert not cog_path.exists()
    assert not temp_cog_path.exists()
