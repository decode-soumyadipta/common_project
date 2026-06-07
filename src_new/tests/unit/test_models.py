"""Unit tests for shared Pydantic models.

Tests all models in src_new/shared/models/ including:
- BoundingBox validation and methods
- RasterMetadata serialization
- QueryResult with empty and populated rasters
- CoordinateReferenceSystem parsing
- TileRequest validation

**Validates: Requirements 19.2**
"""
from datetime import datetime

import pytest
from pydantic import ValidationError

from src_new.shared.models.bounding_box import BoundingBox
from src_new.shared.models.crs import CoordinateReferenceSystem
from src_new.shared.models.query_result import QueryResult
from src_new.shared.models.raster_metadata import RasterKind, RasterMetadata
from src_new.shared.models.tile_request import TileRequest


# ============================================================================= BoundingBox Tests =============================================================================

class TestBoundingBox:
    """Test suite for BoundingBox model validation and methods."""

    def test_valid_bounding_box(self):
        """Test creating a valid bounding box."""
        bbox = BoundingBox(
            min_lon=72.0,
            min_lat=18.0,
            max_lon=73.0,
            max_lat=19.0
        )
        assert bbox.min_lon == 72.0
        assert bbox.min_lat == 18.0
        assert bbox.max_lon == 73.0
        assert bbox.max_lat == 19.0

    def test_invalid_coordinate_ranges_longitude(self):
        """Test that longitude values outside [-180, 180] are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            BoundingBox(
                min_lon=-181.0,
                min_lat=18.0,
                max_lon=73.0,
                max_lat=19.0
            )
        assert "min_lon" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            BoundingBox(
                min_lon=72.0,
                min_lat=18.0,
                max_lon=181.0,
                max_lat=19.0
            )
        assert "max_lon" in str(exc_info.value)

    def test_invalid_coordinate_ranges_latitude(self):
        """Test that latitude values outside [-90, 90] are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            BoundingBox(
                min_lon=72.0,
                min_lat=-91.0,
                max_lon=73.0,
                max_lat=19.0
            )
        assert "min_lat" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            BoundingBox(
                min_lon=72.0,
                min_lat=18.0,
                max_lon=73.0,
                max_lat=91.0
            )
        assert "max_lat" in str(exc_info.value)

    def test_min_lon_equals_max_lon_rejected(self):
        """Test that min_lon == max_lon is rejected (zero-width box)."""
        with pytest.raises(ValidationError) as exc_info:
            BoundingBox(
                min_lon=72.0,
                min_lat=18.0,
                max_lon=72.0,
                max_lat=19.0
            )
        assert "min_lon" in str(exc_info.value)
        assert "max_lon" in str(exc_info.value)

    def test_min_lat_equals_max_lat_rejected(self):
        """Test that min_lat == max_lat is rejected (zero-height box)."""
        with pytest.raises(ValidationError) as exc_info:
            BoundingBox(
                min_lon=72.0,
                min_lat=18.0,
                max_lon=73.0,
                max_lat=18.0
            )
        assert "min_lat" in str(exc_info.value)
        assert "max_lat" in str(exc_info.value)

    def test_min_greater_than_max_rejected(self):
        """Test that min > max is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            BoundingBox(
                min_lon=73.0,
                min_lat=18.0,
                max_lon=72.0,
                max_lat=19.0
            )
        assert "min_lon" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            BoundingBox(
                min_lon=72.0,
                min_lat=19.0,
                max_lon=73.0,
                max_lat=18.0
            )
        assert "min_lat" in str(exc_info.value)

    def test_contains_point_inside(self):
        """Test contains_point returns True for points inside the box."""
        bbox = BoundingBox(
            min_lon=72.0,
            min_lat=18.0,
            max_lon=73.0,
            max_lat=19.0
        )
        assert bbox.contains_point(72.5, 18.5) is True

    def test_contains_point_on_edge(self):
        """Test contains_point returns True for points on the edge."""
        bbox = BoundingBox(
            min_lon=72.0,
            min_lat=18.0,
            max_lon=73.0,
            max_lat=19.0
        )
        assert bbox.contains_point(72.0, 18.0) is True
        assert bbox.contains_point(73.0, 19.0) is True
        assert bbox.contains_point(72.5, 18.0) is True

    def test_contains_point_outside(self):
        """Test contains_point returns False for points outside the box."""
        bbox = BoundingBox(
            min_lon=72.0,
            min_lat=18.0,
            max_lon=73.0,
            max_lat=19.0
        )
        assert bbox.contains_point(71.0, 18.5) is False
        assert bbox.contains_point(74.0, 18.5) is False
        assert bbox.contains_point(72.5, 17.0) is False
        assert bbox.contains_point(72.5, 20.0) is False

    def test_intersects_overlapping(self):
        """Test intersects returns True for overlapping boxes."""
        bbox1 = BoundingBox(
            min_lon=72.0,
            min_lat=18.0,
            max_lon=73.0,
            max_lat=19.0
        )
        bbox2 = BoundingBox(
            min_lon=72.5,
            min_lat=18.5,
            max_lon=73.5,
            max_lat=19.5
        )
        assert bbox1.intersects(bbox2) is True
        assert bbox2.intersects(bbox1) is True

    def test_intersects_touching_edges(self):
        """Test intersects returns True for boxes touching at edges."""
        bbox1 = BoundingBox(
            min_lon=72.0,
            min_lat=18.0,
            max_lon=73.0,
            max_lat=19.0
        )
        bbox2 = BoundingBox(
            min_lon=73.0,
            min_lat=18.0,
            max_lon=74.0,
            max_lat=19.0
        )
        assert bbox1.intersects(bbox2) is True

    def test_intersects_non_overlapping(self):
        """Test intersects returns False for non-overlapping boxes."""
        bbox1 = BoundingBox(
            min_lon=72.0,
            min_lat=18.0,
            max_lon=73.0,
            max_lat=19.0
        )
        bbox2 = BoundingBox(
            min_lon=74.0,
            min_lat=20.0,
            max_lon=75.0,
            max_lat=21.0
        )
        assert bbox1.intersects(bbox2) is False
        assert bbox2.intersects(bbox1) is False

    def test_to_wkt_polygon(self):
        """Test WKT polygon generation."""
        bbox = BoundingBox(
            min_lon=72.0,
            min_lat=18.0,
            max_lon=73.0,
            max_lat=19.0
        )
        wkt = bbox.to_wkt_polygon()
        assert wkt == "POLYGON((72.0 18.0, 73.0 18.0, 73.0 19.0, 72.0 19.0, 72.0 18.0))"

    def test_from_wsen(self):
        """Test construction from west/south/east/north ordering."""
        bbox = BoundingBox.from_wsen(
            west=72.0,
            south=18.0,
            east=73.0,
            north=19.0
        )
        assert bbox.min_lon == 72.0
        assert bbox.min_lat == 18.0
        assert bbox.max_lon == 73.0
        assert bbox.max_lat == 19.0

    def test_serialization_round_trip(self):
        """Test JSON serialization and deserialization."""
        bbox = BoundingBox(
            min_lon=72.0,
            min_lat=18.0,
            max_lon=73.0,
            max_lat=19.0
        )
        json_data = bbox.model_dump()
        bbox_restored = BoundingBox(**json_data)
        assert bbox_restored == bbox


# ============================================================================= CoordinateReferenceSystem Tests =============================================================================

class TestCoordinateReferenceSystem:
    """Test suite for CoordinateReferenceSystem model."""

    def test_valid_crs_epsg_only(self):
        """Test creating CRS with only EPSG code."""
        crs = CoordinateReferenceSystem(epsg_code=4326)
        assert crs.epsg_code == 4326
        assert crs.wkt is None

    def test_valid_crs_with_wkt(self):
        """Test creating CRS with EPSG code and WKT."""
        wkt_string = 'GEOGCS["WGS 84",DATUM["WGS_1984"]]'
        crs = CoordinateReferenceSystem(epsg_code=4326, wkt=wkt_string)
        assert crs.epsg_code == 4326
        assert crs.wkt == wkt_string

    def test_invalid_epsg_code_zero(self):
        """Test that EPSG code 0 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            CoordinateReferenceSystem(epsg_code=0)
        assert "epsg_code" in str(exc_info.value)

    def test_invalid_epsg_code_negative(self):
        """Test that negative EPSG codes are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            CoordinateReferenceSystem(epsg_code=-1)
        assert "epsg_code" in str(exc_info.value)

    def test_invalid_wkt_empty_string(self):
        """Test that empty WKT string is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            CoordinateReferenceSystem(epsg_code=4326, wkt="")
        assert "wkt" in str(exc_info.value)

    def test_invalid_wkt_whitespace_only(self):
        """Test that whitespace-only WKT is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            CoordinateReferenceSystem(epsg_code=4326, wkt="   ")
        assert "wkt" in str(exc_info.value)

    def test_authority_code_property(self):
        """Test authority_code property returns correct format."""
        crs = CoordinateReferenceSystem(epsg_code=4326)
        assert crs.authority_code == "EPSG:4326"

        crs = CoordinateReferenceSystem(epsg_code=32644)
        assert crs.authority_code == "EPSG:32644"

    def test_from_authority_string_valid(self):
        """Test parsing valid authority strings."""
        crs = CoordinateReferenceSystem.from_authority_string("EPSG:4326")
        assert crs.epsg_code == 4326

        crs = CoordinateReferenceSystem.from_authority_string("epsg:32644")
        assert crs.epsg_code == 32644

        crs = CoordinateReferenceSystem.from_authority_string("  EPSG:3857  ")
        assert crs.epsg_code == 3857

    def test_from_authority_string_invalid_format(self):
        """Test that invalid authority string formats are rejected."""
        with pytest.raises(ValueError) as exc_info:
            CoordinateReferenceSystem.from_authority_string("4326")
        assert "Cannot parse" in str(exc_info.value)

        with pytest.raises(ValueError) as exc_info:
            CoordinateReferenceSystem.from_authority_string("WGS84:4326")
        assert "Cannot parse" in str(exc_info.value)

    def test_from_authority_string_invalid_code(self):
        """Test that non-integer EPSG codes are rejected."""
        with pytest.raises(ValueError) as exc_info:
            CoordinateReferenceSystem.from_authority_string("EPSG:abc")
        assert "not a valid integer" in str(exc_info.value)


# ============================================================================= RasterMetadata Tests =============================================================================

class TestRasterMetadata:
    """Test suite for RasterMetadata model."""

    def test_valid_raster_metadata_minimal(self):
        """Test creating RasterMetadata with minimal required fields."""
        bbox = BoundingBox(
            min_lon=72.0,
            min_lat=18.0,
            max_lon=73.0,
            max_lat=19.0
        )
        meta = RasterMetadata(
            raster_id="550e8400-e29b-41d4-a716-446655440000",
            file_path="/data/imagery/scene_001.tif",
            file_name="scene_001.tif",
            kind=RasterKind.GEOTIFF,
            crs="EPSG:4326",
            bbox=bbox,
            resolution_x=0.00002,
            resolution_y=0.00002,
            width=50000,
            height=50000
        )
        assert meta.raster_id == "550e8400-e29b-41d4-a716-446655440000"
        assert meta.file_path == "/data/imagery/scene_001.tif"
        assert meta.kind == RasterKind.GEOTIFF
        assert meta.upload_date is None
        assert meta.updated_at is None

    def test_valid_raster_metadata_with_dates(self):
        """Test creating RasterMetadata with optional date fields."""
        bbox = BoundingBox(
            min_lon=72.0,
            min_lat=18.0,
            max_lon=73.0,
            max_lat=19.0
        )
        upload_date = datetime(2024, 1, 1, 12, 0, 0)
        updated_at = datetime(2024, 1, 2, 12, 0, 0)
        
        meta = RasterMetadata(
            raster_id="test-123",
            file_path="/data/test.tif",
            file_name="test.tif",
            kind=RasterKind.GEOTIFF,
            crs="EPSG:4326",
            bbox=bbox,
            resolution_x=0.5,
            resolution_y=0.5,
            width=1000,
            height=1000,
            upload_date=upload_date,
            updated_at=updated_at
        )
        assert meta.upload_date == upload_date
        assert meta.updated_at == updated_at

    def test_invalid_empty_file_path(self):
        """Test that empty file_path is rejected."""
        bbox = BoundingBox(
            min_lon=72.0,
            min_lat=18.0,
            max_lon=73.0,
            max_lat=19.0
        )
        with pytest.raises(ValidationError) as exc_info:
            RasterMetadata(
                raster_id="test-123",
                file_path="",
                file_name="test.tif",
                kind=RasterKind.GEOTIFF,
                crs="EPSG:4326",
                bbox=bbox,
                resolution_x=0.5,
                resolution_y=0.5,
                width=1000,
                height=1000
            )
        assert "file_path" in str(exc_info.value)

    def test_invalid_empty_file_name(self):
        """Test that empty file_name is rejected."""
        bbox = BoundingBox(
            min_lon=72.0,
            min_lat=18.0,
            max_lon=73.0,
            max_lat=19.0
        )
        with pytest.raises(ValidationError) as exc_info:
            RasterMetadata(
                raster_id="test-123",
                file_path="/data/test.tif",
                file_name="",
                kind=RasterKind.GEOTIFF,
                crs="EPSG:4326",
                bbox=bbox,
                resolution_x=0.5,
                resolution_y=0.5,
                width=1000,
                height=1000
            )
        assert "file_name" in str(exc_info.value)

    def test_invalid_zero_resolution(self):
        """Test that zero or negative resolution is rejected."""
        bbox = BoundingBox(
            min_lon=72.0,
            min_lat=18.0,
            max_lon=73.0,
            max_lat=19.0
        )
        with pytest.raises(ValidationError) as exc_info:
            RasterMetadata(
                raster_id="test-123",
                file_path="/data/test.tif",
                file_name="test.tif",
                kind=RasterKind.GEOTIFF,
                crs="EPSG:4326",
                bbox=bbox,
                resolution_x=0.0,
                resolution_y=0.5,
                width=1000,
                height=1000
            )
        assert "resolution_x" in str(exc_info.value)

    def test_invalid_zero_dimensions(self):
        """Test that zero or negative width/height is rejected."""
        bbox = BoundingBox(
            min_lon=72.0,
            min_lat=18.0,
            max_lon=73.0,
            max_lat=19.0
        )
        with pytest.raises(ValidationError) as exc_info:
            RasterMetadata(
                raster_id="test-123",
                file_path="/data/test.tif",
                file_name="test.tif",
                kind=RasterKind.GEOTIFF,
                crs="EPSG:4326",
                bbox=bbox,
                resolution_x=0.5,
                resolution_y=0.5,
                width=0,
                height=1000
            )
        assert "width" in str(exc_info.value)

    def test_raster_kind_enum_values(self):
        """Test all RasterKind enum values."""
        bbox = BoundingBox(
            min_lon=72.0,
            min_lat=18.0,
            max_lon=73.0,
            max_lat=19.0
        )
        
        for kind in [RasterKind.GEOTIFF, RasterKind.JPEG2000, RasterKind.MBTILES, RasterKind.DEM, RasterKind.UNKNOWN]:
            meta = RasterMetadata(
                raster_id="test-123",
                file_path="/data/test.tif",
                file_name="test.tif",
                kind=kind,
                crs="EPSG:4326",
                bbox=bbox,
                resolution_x=0.5,
                resolution_y=0.5,
                width=1000,
                height=1000
            )
            assert meta.kind == kind

    def test_serialization_round_trip(self):
        """Test JSON serialization and deserialization of RasterMetadata."""
        bbox = BoundingBox(
            min_lon=72.0,
            min_lat=18.0,
            max_lon=73.0,
            max_lat=19.0
        )
        upload_date = datetime(2024, 1, 1, 12, 0, 0)
        
        meta = RasterMetadata(
            raster_id="test-123",
            file_path="/data/test.tif",
            file_name="test.tif",
            kind=RasterKind.GEOTIFF,
            crs="EPSG:4326",
            bbox=bbox,
            resolution_x=0.5,
            resolution_y=0.5,
            width=1000,
            height=1000,
            upload_date=upload_date
        )
        
        # Serialize to dict
        json_data = meta.model_dump()
        
        # Deserialize back
        meta_restored = RasterMetadata(**json_data)
        
        assert meta_restored.raster_id == meta.raster_id
        assert meta_restored.file_path == meta.file_path
        assert meta_restored.kind == meta.kind
        assert meta_restored.bbox == meta.bbox
        assert meta_restored.upload_date == meta.upload_date


# ============================================================================= QueryResult Tests =============================================================================

class TestQueryResult:
    """Test suite for QueryResult model."""

    def test_empty_query_result(self):
        """Test creating QueryResult with empty rasters list."""
        result = QueryResult(rasters=[], count=0)
        assert result.rasters == []
        assert result.count == 0

    def test_query_result_with_rasters(self):
        """Test creating QueryResult with populated rasters list."""
        bbox = BoundingBox(
            min_lon=72.0,
            min_lat=18.0,
            max_lon=73.0,
            max_lat=19.0
        )
        meta1 = RasterMetadata(
            raster_id="test-1",
            file_path="/data/test1.tif",
            file_name="test1.tif",
            kind=RasterKind.GEOTIFF,
            crs="EPSG:4326",
            bbox=bbox,
            resolution_x=0.5,
            resolution_y=0.5,
            width=1000,
            height=1000
        )
        meta2 = RasterMetadata(
            raster_id="test-2",
            file_path="/data/test2.tif",
            file_name="test2.tif",
            kind=RasterKind.JPEG2000,
            crs="EPSG:4326",
            bbox=bbox,
            resolution_x=0.5,
            resolution_y=0.5,
            width=1000,
            height=1000
        )
        
        result = QueryResult(rasters=[meta1, meta2], count=2)
        assert len(result.rasters) == 2
        assert result.count == 2
        assert result.rasters[0].raster_id == "test-1"
        assert result.rasters[1].raster_id == "test-2"

    def test_count_mismatch_rejected(self):
        """Test that count != len(rasters) is rejected."""
        bbox = BoundingBox(
            min_lon=72.0,
            min_lat=18.0,
            max_lon=73.0,
            max_lat=19.0
        )
        meta = RasterMetadata(
            raster_id="test-1",
            file_path="/data/test1.tif",
            file_name="test1.tif",
            kind=RasterKind.GEOTIFF,
            crs="EPSG:4326",
            bbox=bbox,
            resolution_x=0.5,
            resolution_y=0.5,
            width=1000,
            height=1000
        )
        
        with pytest.raises(ValidationError) as exc_info:
            QueryResult(rasters=[meta], count=2)
        assert "count" in str(exc_info.value)

    def test_from_rasters_convenience_constructor(self):
        """Test from_rasters convenience constructor sets count automatically."""
        bbox = BoundingBox(
            min_lon=72.0,
            min_lat=18.0,
            max_lon=73.0,
            max_lat=19.0
        )
        meta1 = RasterMetadata(
            raster_id="test-1",
            file_path="/data/test1.tif",
            file_name="test1.tif",
            kind=RasterKind.GEOTIFF,
            crs="EPSG:4326",
            bbox=bbox,
            resolution_x=0.5,
            resolution_y=0.5,
            width=1000,
            height=1000
        )
        meta2 = RasterMetadata(
            raster_id="test-2",
            file_path="/data/test2.tif",
            file_name="test2.tif",
            kind=RasterKind.JPEG2000,
            crs="EPSG:4326",
            bbox=bbox,
            resolution_x=0.5,
            resolution_y=0.5,
            width=1000,
            height=1000
        )
        
        result = QueryResult.from_rasters([meta1, meta2])
        assert result.count == 2
        assert len(result.rasters) == 2

    def test_from_rasters_empty_list(self):
        """Test from_rasters with empty list."""
        result = QueryResult.from_rasters([])
        assert result.count == 0
        assert result.rasters == []


# ============================================================================= TileRequest Tests =============================================================================

class TestTileRequest:
    """Test suite for TileRequest model."""

    def test_valid_tile_request_minimal(self):
        """Test creating TileRequest with minimal required fields."""
        req = TileRequest(
            z=10,
            x=512,
            y=384,
            raster_id="abc-123"
        )
        assert req.z == 10
        assert req.x == 512
        assert req.y == 384
        assert req.raster_id == "abc-123"
        assert req.contrast == 1.0
        assert req.brightness == 1.0
        assert req.colormap is None

    def test_valid_tile_request_with_styling(self):
        """Test creating TileRequest with image manipulation parameters."""
        req = TileRequest(
            z=12,
            x=2048,
            y=1536,
            raster_id="abc-123",
            contrast=1.2,
            brightness=0.9,
            colormap="viridis"
        )
        assert req.contrast == 1.2
        assert req.brightness == 0.9
        assert req.colormap == "viridis"

    def test_invalid_zoom_level_negative(self):
        """Test that negative zoom level is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TileRequest(
                z=-1,
                x=512,
                y=384,
                raster_id="abc-123"
            )
        assert "z" in str(exc_info.value)

    def test_invalid_zoom_level_too_high(self):
        """Test that zoom level > 30 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TileRequest(
                z=31,
                x=512,
                y=384,
                raster_id="abc-123"
            )
        assert "z" in str(exc_info.value)

    def test_invalid_tile_coordinates_negative(self):
        """Test that negative tile coordinates are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TileRequest(
                z=10,
                x=-1,
                y=384,
                raster_id="abc-123"
            )
        assert "x" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            TileRequest(
                z=10,
                x=512,
                y=-1,
                raster_id="abc-123"
            )
        assert "y" in str(exc_info.value)

    def test_invalid_empty_raster_id(self):
        """Test that empty raster_id is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TileRequest(
                z=10,
                x=512,
                y=384,
                raster_id=""
            )
        assert "raster_id" in str(exc_info.value)

    def test_invalid_contrast_zero(self):
        """Test that contrast <= 0 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TileRequest(
                z=10,
                x=512,
                y=384,
                raster_id="abc-123",
                contrast=0.0
            )
        assert "contrast" in str(exc_info.value)

    def test_invalid_brightness_zero(self):
        """Test that brightness <= 0 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TileRequest(
                z=10,
                x=512,
                y=384,
                raster_id="abc-123",
                brightness=0.0
            )
        assert "brightness" in str(exc_info.value)

    def test_boundary_zoom_levels(self):
        """Test boundary zoom levels 0 and 30."""
        req_min = TileRequest(z=0, x=0, y=0, raster_id="abc-123")
        assert req_min.z == 0

        req_max = TileRequest(z=30, x=0, y=0, raster_id="abc-123")
        assert req_max.z == 30
