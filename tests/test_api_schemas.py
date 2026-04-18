import pytest
from pydantic import ValidationError

from offline_gis_app.api.schemas import BBoxSearchRequest, CoordinateSearchRequest, ProfileRequest


def test_coordinate_search_request_rejects_invalid_lon_lat():
    with pytest.raises(ValidationError):
        CoordinateSearchRequest(lon=181.0, lat=10.0)

    with pytest.raises(ValidationError):
        CoordinateSearchRequest(lon=10.0, lat=-91.0)


def test_bbox_search_request_rejects_zero_area():
    with pytest.raises(ValidationError):
        BBoxSearchRequest(west=10.0, south=20.0, east=10.0, north=30.0)

    with pytest.raises(ValidationError):
        BBoxSearchRequest(west=10.0, south=20.0, east=30.0, north=20.0)


def test_profile_request_uses_raster_point_range_validation():
    with pytest.raises(ValidationError):
        ProfileRequest(
            path="/tmp/dem.tif",
            line_points=[{"lon": 77.0, "lat": 12.0}, {"lon": 77.1, "lat": 95.0}],
            samples=10,
        )
