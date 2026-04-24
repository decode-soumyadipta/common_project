from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from offline_gis_app.server_ingestion.services.metadata_extractor import (
    extract_metadata,
)


def test_extract_metadata_transforms_bounds_to_wgs84(tmp_path: Path):
    raster_path = tmp_path / "utm_sample.tif"
    data = np.ones((20, 20), dtype=np.uint16)
    transform = from_origin(500000.0, 2600000.0, 10.0, 10.0)

    with rasterio.open(
        raster_path,
        "w",
        driver="GTiff",
        height=20,
        width=20,
        count=1,
        dtype=data.dtype,
        crs="EPSG:32643",
        transform=transform,
    ) as dst:
        dst.write(data, 1)

    metadata = extract_metadata(raster_path)
    lon, lat = metadata.bounds.centroid()
    assert -180.0 <= lon <= 180.0
    assert -90.0 <= lat <= 90.0
