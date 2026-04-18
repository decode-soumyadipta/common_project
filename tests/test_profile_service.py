from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from offline_gis_app.services.profile_service import sample_profile


def test_sample_profile_reprojects_from_wgs84_to_dataset_crs(tmp_path: Path):
    raster_path = tmp_path / "dem_3857.tif"
    data = np.arange(400, dtype=np.float32).reshape((20, 20))

    # Raster extent in EPSG:3857 meters: x=[100000,120000], y=[100000,120000].
    transform = from_origin(100000.0, 120000.0, 1000.0, 1000.0)
    with rasterio.open(
        raster_path,
        "w",
        driver="GTiff",
        height=20,
        width=20,
        count=1,
        dtype=data.dtype,
        crs="EPSG:3857",
        transform=transform,
    ) as dst:
        dst.write(data, 1)

    # Input points are lon/lat (EPSG:4326) and should be transformed before sampling.
    values = sample_profile(raster_path, [(1.0, 1.0), (1.05, 1.05)], samples=5)

    assert len(values) == 5
    assert all(np.isfinite(values))


def test_sample_profile_rejects_missing_raster_crs(tmp_path: Path):
    raster_path = tmp_path / "dem_no_crs.tif"
    data = np.ones((10, 10), dtype=np.float32)
    transform = from_origin(0.0, 10.0, 1.0, 1.0)

    with rasterio.open(
        raster_path,
        "w",
        driver="GTiff",
        height=10,
        width=10,
        count=1,
        dtype=data.dtype,
        transform=transform,
    ) as dst:
        dst.write(data, 1)

    with pytest.raises(ValueError, match="Raster CRS is missing"):
        sample_profile(raster_path, [(0.0, 0.0), (0.1, 0.1)], samples=2)
