from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from src_new.services.ingestion.gdal_pipelines import metadata_extractor


def test_extract_metadata_uses_external_prj_for_jpeg2000_bounds(
    monkeypatch, tmp_path: Path
) -> None:
    source_path = tmp_path / "scene.j2k"
    source_path.write_bytes(b"fake-jpeg2000")

    fake_dataset = SimpleNamespace(
        crs=None,
        bounds=SimpleNamespace(left=500000.0, bottom=4100000.0, right=500500.0, top=4100500.0),
        width=2,
        height=2,
        count=1,
        res=(5.0, 5.0),
        dtypes=["Byte"],
    )

    monkeypatch.setattr(
        metadata_extractor,
        "_read_with_rasterio",
        lambda _path: nullcontext(fake_dataset),
    )
    monkeypatch.setattr(
        metadata_extractor,
        "_read_auxiliary_crs_and_log",
        lambda _path, _log: "EPSG:32644",
    )
    monkeypatch.setattr(
        metadata_extractor.settings.__class__,
        "apply_gdal_env",
        lambda self: None,
        raising=False,
    )

    transform_calls: list[tuple] = []

    def fake_transform_bounds(src_crs, dst_crs, left, bottom, right, top, densify_pts=21):
        transform_calls.append((src_crs, dst_crs, left, bottom, right, top, densify_pts))
        return (-10.0, -20.0, 30.0, 40.0)

    monkeypatch.setattr(
        "rasterio.warp.transform_bounds",
        fake_transform_bounds,
    )

    metadata = metadata_extractor.extract_metadata(source_path)

    assert transform_calls, "Expected the sidecar CRS to be used for bounds transformation"
    assert metadata.crs == "EPSG:32644"
    assert metadata.bbox.min_lon == pytest.approx(-10.0)
    assert metadata.bbox.min_lat == pytest.approx(-20.0)
    assert metadata.bbox.max_lon == pytest.approx(30.0)
    assert metadata.bbox.max_lat == pytest.approx(40.0)


def test_read_auxiliary_crs_and_log_resolves_cog_stem(tmp_path: Path) -> None:
    # Scenario 1: File is scene.cog.tif, sidecar is scene.prj
    cog_path = tmp_path / "scene.cog.tif"
    prj_path = tmp_path / "scene.prj"
    prj_path.write_text("EPSG:32643")
    
    # Also create a world file for the base name
    tfw_path = tmp_path / "scene.tfw"
    tfw_path.write_text("1.0\n0.0\n0.0\n-1.0\n100.0\n500.0\n")
    
    import logging
    logger = logging.getLogger("test_metadata")
    
    crs = metadata_extractor._read_auxiliary_crs_and_log(cog_path, logger)
    assert crs == "EPSG:32643"
    
    # Scenario 2: File is scene.cog.tif, sidecar is scene.cog.prj (exact match)
    prj_path.unlink()
    tfw_path.unlink()
    
    cog_prj_path = tmp_path / "scene.cog.prj"
    cog_prj_path.write_text("EPSG:3857")
    crs = metadata_extractor._read_auxiliary_crs_and_log(cog_path, logger)
    assert crs == "EPSG:3857"