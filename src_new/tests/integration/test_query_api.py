"""Integration tests for Query Service API.

Tests the Query Service REST API endpoints with real FastAPI test client
and database fixtures.

Task 7.3: Write integration tests for Query Service API
- Test POST /query/point returns correct rasters for known coordinates
- Test POST /query/bbox with bounding box covering test fixture
- Test GET /health returns healthy status

Requirements: 14.2, 19.3
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from src_new.shared.models.raster_metadata import RasterMetadata, RasterKind
from src_new.shared.models.bounding_box import BoundingBox


@pytest.fixture
def test_app():
    """Create a test FastAPI app without LAN security middleware."""
    from fastapi import FastAPI
    from src_new.services.query.api.routes import router
    from src_new.shared.utils.error_handlers import register_exception_handlers
    
    # Create a clean app without middleware for testing
    test_app = FastAPI(title="Query Service Test")
    test_app.include_router(router)
    register_exception_handlers(test_app)
    
    return test_app


@pytest.fixture
def test_client(test_app, mock_raster_repository, mock_db_session) -> TestClient:
    """Create a FastAPI test client for the Query Service.
    
    Uses a test app without LAN security middleware and with mocked dependencies
    to avoid authentication and database issues in tests.
    """
    # Override the dependencies to use mocks
    from src_new.services.query.api import routes as query_routes

    test_app.dependency_overrides[query_routes.get_db] = lambda: mock_db_session
    test_app.dependency_overrides[
        query_routes.get_raster_repository
    ] = lambda: mock_raster_repository

    client = TestClient(test_app)

    yield client

    test_app.dependency_overrides.clear()


@pytest.fixture
def mock_raster_repository():
    """Mock RasterRepository for testing without database dependency."""
    mock_repo = MagicMock()
    
    # Sample test raster metadata
    test_raster = RasterMetadata(
        raster_id="test-raster-550e8400-e29b-41d4-a716-446655440000",
        file_path="/data/test_imagery/sample.tif",
        file_name="sample.tif",
        kind=RasterKind.GEOTIFF,
        crs="EPSG:4326",
        bbox=BoundingBox(
            min_lon=72.5,
            min_lat=18.5,
            max_lon=73.5,
            max_lat=19.5
        ),
        resolution_x=0.00002,
        resolution_y=0.00002,
        width=50000,
        height=50000,
        upload_date=None,
        updated_at=None
    )
    
    # Configure mock methods
    mock_repo.find_by_point.return_value = [test_raster]
    mock_repo.find_by_bbox.return_value = [test_raster]
    mock_repo.find_by_id.return_value = test_raster
    
    return mock_repo


@pytest.fixture
def mock_db_session():
    """Mock database session for health check tests."""
    mock_session = MagicMock()
    mock_session.execute = MagicMock()
    return mock_session


class TestQueryPointEndpoint:
    """Tests for POST /query/point endpoint."""
    
    def test_query_point_returns_matching_rasters(
        self, 
        test_client: TestClient,
        mock_raster_repository: MagicMock
    ):
        """Test that POST /query/point returns correct rasters for known coordinates.
        
        **Validates: Requirements 14.2, 19.3**
        
        Given a point query with coordinates inside a known raster's extent,
        the endpoint should return that raster in the results.
        """
        # Query a point inside the test raster's bbox (72.5-73.5, 18.5-19.5)
        response = test_client.post(
            "/query/point",
            json={
                "lat": 19.0,
                "lon": 73.0,
                "crs": "EPSG:4326"
            }
        )
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        
        # Check QueryResult structure
        assert "rasters" in data
        assert "count" in data
        assert data["count"] == 1
        assert len(data["rasters"]) == 1
        
        # Verify raster metadata
        raster = data["rasters"][0]
        assert raster["raster_id"] == "test-raster-550e8400-e29b-41d4-a716-446655440000"
        assert raster["file_name"] == "sample.tif"
        assert raster["kind"] == "geotiff"
        assert raster["crs"] == "EPSG:4326"
        
        # Verify bbox structure
        assert "bbox" in raster
        assert raster["bbox"]["min_lon"] == 72.5
        assert raster["bbox"]["min_lat"] == 18.5
        assert raster["bbox"]["max_lon"] == 73.5
        assert raster["bbox"]["max_lat"] == 19.5
        
        # Verify repository was called with correct parameters
        mock_raster_repository.find_by_point.assert_called_once_with(
            lon=73.0,
            lat=19.0
        )
    
    def test_query_point_with_no_results(
        self,
        test_client: TestClient,
        mock_raster_repository: MagicMock
    ):
        """Test that POST /query/point returns empty results when no rasters match."""
        # Configure mock to return empty list
        mock_raster_repository.find_by_point.return_value = []
        
        response = test_client.post(
            "/query/point",
            json={
                "lat": 0.0,
                "lon": 0.0,
                "crs": "EPSG:4326"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert len(data["rasters"]) == 0
    
    def test_query_point_validates_latitude_range(self, test_client: TestClient):
        """Test that invalid latitude values are rejected."""
        # Test latitude > 90
        response = test_client.post(
            "/query/point",
            json={
                "lat": 91.0,
                "lon": 0.0,
                "crs": "EPSG:4326"
            }
        )
        assert response.status_code == 422  # Validation error
        
        # Test latitude < -90
        response = test_client.post(
            "/query/point",
            json={
                "lat": -91.0,
                "lon": 0.0,
                "crs": "EPSG:4326"
            }
        )
        assert response.status_code == 422
    
    def test_query_point_validates_longitude_range(self, test_client: TestClient):
        """Test that invalid longitude values are rejected."""
        # Test longitude > 180
        response = test_client.post(
            "/query/point",
            json={
                "lat": 0.0,
                "lon": 181.0,
                "crs": "EPSG:4326"
            }
        )
        assert response.status_code == 422
        
        # Test longitude < -180
        response = test_client.post(
            "/query/point",
            json={
                "lat": 0.0,
                "lon": -181.0,
                "crs": "EPSG:4326"
            }
        )
        assert response.status_code == 422


class TestQueryBBoxEndpoint:
    """Tests for POST /query/bbox endpoint."""
    
    def test_query_bbox_returns_intersecting_rasters(
        self,
        test_client: TestClient,
        mock_raster_repository: MagicMock
    ):
        """Test that POST /query/bbox returns rasters intersecting the bounding box.
        
        **Validates: Requirements 14.2, 19.3**
        
        Given a bounding box query that overlaps with a known raster's extent,
        the endpoint should return that raster in the results.
        """
        with patch(
            "src_new.services.query.api.routes.get_raster_repository",
            return_value=mock_raster_repository
        ):
            # Query a bbox that overlaps with test raster (72.5-73.5, 18.5-19.5)
            response = test_client.post(
                "/query/bbox",
                json={
                    "min_lon": 72.0,
                    "min_lat": 18.0,
                    "max_lon": 74.0,
                    "max_lat": 20.0,
                    "crs": "EPSG:4326"
                }
            )
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        
        # Check QueryResult structure
        assert "rasters" in data
        assert "count" in data
        assert data["count"] == 1
        assert len(data["rasters"]) == 1
        
        # Verify raster metadata
        raster = data["rasters"][0]
        assert raster["raster_id"] == "test-raster-550e8400-e29b-41d4-a716-446655440000"
        assert raster["file_name"] == "sample.tif"
        
        # Verify repository was called with correct parameters
        mock_raster_repository.find_by_bbox.assert_called_once_with(
            min_lon=72.0,
            min_lat=18.0,
            max_lon=74.0,
            max_lat=20.0
        )
    
    def test_query_bbox_with_no_results(
        self,
        test_client: TestClient,
        mock_raster_repository: MagicMock
    ):
        """Test that POST /query/bbox returns empty results when no rasters intersect."""
        # Configure mock to return empty list
        mock_raster_repository.find_by_bbox.return_value = []
        
        with patch(
            "src_new.services.query.api.routes.get_raster_repository",
            return_value=mock_raster_repository
        ):
            response = test_client.post(
                "/query/bbox",
                json={
                    "min_lon": 0.0,
                    "min_lat": 0.0,
                    "max_lon": 1.0,
                    "max_lat": 1.0,
                    "crs": "EPSG:4326"
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert len(data["rasters"]) == 0
    
    def test_query_bbox_validates_coordinate_order(self, test_client: TestClient):
        """Test that bbox with min >= max is rejected."""
        # Test min_lon >= max_lon
        response = test_client.post(
            "/query/bbox",
            json={
                "min_lon": 74.0,
                "min_lat": 18.0,
                "max_lon": 72.0,  # max < min
                "max_lat": 20.0,
                "crs": "EPSG:4326"
            }
        )
        assert response.status_code == 422
        assert "min_lon must be strictly less than max_lon" in response.json()["detail"]
        
        # Test min_lat >= max_lat
        response = test_client.post(
            "/query/bbox",
            json={
                "min_lon": 72.0,
                "min_lat": 20.0,  # min > max
                "max_lon": 74.0,
                "max_lat": 18.0,
                "crs": "EPSG:4326"
            }
        )
        assert response.status_code == 422
        assert "min_lat must be strictly less than max_lat" in response.json()["detail"]
    
    def test_query_bbox_validates_coordinate_ranges(self, test_client: TestClient):
        """Test that bbox coordinates are within valid ranges."""
        # Test invalid longitude
        response = test_client.post(
            "/query/bbox",
            json={
                "min_lon": -200.0,  # Invalid
                "min_lat": 18.0,
                "max_lon": 74.0,
                "max_lat": 20.0,
                "crs": "EPSG:4326"
            }
        )
        assert response.status_code == 422
        
        # Test invalid latitude
        response = test_client.post(
            "/query/bbox",
            json={
                "min_lon": 72.0,
                "min_lat": -100.0,  # Invalid
                "max_lon": 74.0,
                "max_lat": 20.0,
                "crs": "EPSG:4326"
            }
        )
        assert response.status_code == 422


class TestElevationProfileEndpoint:
    """Tests for POST /profile/elevation endpoint."""

    def test_profile_elevation_samples_a_tiny_dem(
        self,
        test_client: TestClient,
        tmp_path,
    ):
        """Test that the profile endpoint returns sampled elevation values."""
        rasterio = pytest.importorskip("rasterio")
        import numpy as np
        from rasterio.transform import from_origin

        dem_path = tmp_path / "dem.tif"
        data = np.array(
            [
                [1.0, 2.0, 3.0],
                [4.0, 5.0, 6.0],
                [7.0, 8.0, 9.0],
            ],
            dtype=np.float32,
        )

        with rasterio.open(
            dem_path,
            "w",
            driver="GTiff",
            height=3,
            width=3,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(0.0, 3.0, 1.0, 1.0),
            nodata=-9999.0,
        ) as dst:
            dst.write(data, 1)

        response = test_client.post(
            "/profile/elevation",
            json={
                "path": str(dem_path),
                "line_points": [
                    {"lon": 0.5, "lat": 2.5},
                    {"lon": 2.5, "lat": 0.5},
                ],
                "samples": 3,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["samples"] == 3
        assert data["path"] == str(dem_path)
        assert data["values"] == [1.0, 5.0, 9.0]


class TestGetRasterMetadataEndpoint:
    """Tests for GET /raster/{raster_id} endpoint."""
    
    def test_get_raster_by_id_returns_metadata(
        self,
        test_client: TestClient,
        mock_raster_repository: MagicMock
    ):
        """Test that GET /raster/{raster_id} returns correct metadata."""
        with patch(
            "src_new.services.query.api.routes.get_raster_repository",
            return_value=mock_raster_repository
        ):
            response = test_client.get(
                "/raster/test-raster-550e8400-e29b-41d4-a716-446655440000"
            )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify metadata structure
        assert data["raster_id"] == "test-raster-550e8400-e29b-41d4-a716-446655440000"
        assert data["file_name"] == "sample.tif"
        assert data["kind"] == "geotiff"
        assert data["crs"] == "EPSG:4326"
        assert "bbox" in data
        
        # Verify repository was called
        mock_raster_repository.find_by_id.assert_called_once_with(
            "test-raster-550e8400-e29b-41d4-a716-446655440000"
        )
    
    def test_get_raster_by_id_returns_404_when_not_found(
        self,
        test_client: TestClient,
        mock_raster_repository: MagicMock
    ):
        """Test that GET /raster/{raster_id} returns 404 for non-existent raster."""
        # Configure mock to return None
        mock_raster_repository.find_by_id.return_value = None
        
        with patch(
            "src_new.services.query.api.routes.get_raster_repository",
            return_value=mock_raster_repository
        ):
            response = test_client.get("/raster/non-existent-id")
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestHealthEndpoint:
    """Tests for GET /health endpoint."""
    
    def test_health_returns_healthy_status(
        self,
        test_client: TestClient,
        mock_db_session: MagicMock
    ):
        """Test that GET /health returns healthy status when all checks pass.
        
        **Validates: Requirements 14.2, 19.3**
        
        The health endpoint should return:
        - status: "healthy"
        - database: True (when DB is reachable)
        - disk_space_gb: positive float value
        """
        with patch(
            "src_new.services.query.api.routes.get_db",
            return_value=mock_db_session
        ):
            response = test_client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify health response structure
        assert "status" in data
        assert "database" in data
        assert "disk_space_gb" in data
        
        # Verify healthy status
        assert data["status"] == "healthy"
        assert data["database"] is True
        assert isinstance(data["disk_space_gb"], (int, float))
        assert data["disk_space_gb"] >= 0.0
    
    def test_health_returns_degraded_when_database_unreachable(
        self,
        test_client: TestClient,
        mock_db_session: MagicMock
    ):
        """Test that GET /health returns degraded status when database is unreachable."""
        # Configure mock to raise exception on execute
        mock_db_session.execute.side_effect = Exception("Database connection failed")
        
        with patch(
            "src_new.services.query.api.routes.get_db",
            return_value=mock_db_session
        ):
            response = test_client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify degraded status
        assert data["status"] == "degraded"
        assert data["database"] is False
        assert "disk_space_gb" in data
    
    def test_health_includes_disk_space_information(
        self,
        test_client: TestClient,
        mock_db_session: MagicMock
    ):
        """Test that GET /health includes disk space information."""
        with patch(
            "src_new.services.query.api.routes.get_db",
            return_value=mock_db_session
        ):
            response = test_client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify disk space is reported
        assert "disk_space_gb" in data
        disk_space = data["disk_space_gb"]
        assert isinstance(disk_space, (int, float))
        # Disk space should be a reasonable value (not negative, not absurdly large)
        assert 0.0 <= disk_space <= 1_000_000.0  # Up to 1 PB


class TestAPIErrorHandling:
    """Tests for API error handling and edge cases."""
    
    def test_query_point_handles_repository_errors(
        self,
        test_client: TestClient,
        mock_raster_repository: MagicMock
    ):
        """Test that repository errors are handled gracefully."""
        # Configure mock to raise exception
        mock_raster_repository.find_by_point.side_effect = Exception("Database error")
        
        with patch(
            "src_new.services.query.api.routes.get_raster_repository",
            return_value=mock_raster_repository
        ):
            response = test_client.post(
                "/query/point",
                json={
                    "lat": 19.0,
                    "lon": 73.0,
                    "crs": "EPSG:4326"
                }
            )
        
        assert response.status_code == 500
        assert "failed" in response.json()["detail"].lower()
    
    def test_query_bbox_handles_repository_errors(
        self,
        test_client: TestClient,
        mock_raster_repository: MagicMock
    ):
        """Test that repository errors are handled gracefully."""
        # Configure mock to raise exception
        mock_raster_repository.find_by_bbox.side_effect = Exception("Database error")
        
        with patch(
            "src_new.services.query.api.routes.get_raster_repository",
            return_value=mock_raster_repository
        ):
            response = test_client.post(
                "/query/bbox",
                json={
                    "min_lon": 72.0,
                    "min_lat": 18.0,
                    "max_lon": 74.0,
                    "max_lat": 20.0,
                    "crs": "EPSG:4326"
                }
            )
        
        assert response.status_code == 500
        assert "failed" in response.json()["detail"].lower()
    
    def test_get_raster_handles_repository_errors(
        self,
        test_client: TestClient,
        mock_raster_repository: MagicMock
    ):
        """Test that repository errors are handled gracefully."""
        # Configure mock to raise exception
        mock_raster_repository.find_by_id.side_effect = Exception("Database error")
        
        with patch(
            "src_new.services.query.api.routes.get_raster_repository",
            return_value=mock_raster_repository
        ):
            response = test_client.get("/raster/test-id")
        
        assert response.status_code == 500
        assert "failed" in response.json()["detail"].lower()


class TestAPIRequestValidation:
    """Tests for API request validation."""
    
    def test_query_point_requires_all_fields(self, test_client: TestClient):
        """Test that missing required fields are rejected."""
        # Missing lat
        response = test_client.post(
            "/query/point",
            json={
                "lon": 73.0,
                "crs": "EPSG:4326"
            }
        )
        assert response.status_code == 422
        
        # Missing lon
        response = test_client.post(
            "/query/point",
            json={
                "lat": 19.0,
                "crs": "EPSG:4326"
            }
        )
        assert response.status_code == 422
    
    def test_query_bbox_requires_all_fields(self, test_client: TestClient):
        """Test that missing required fields are rejected."""
        # Missing max_lon
        response = test_client.post(
            "/query/bbox",
            json={
                "min_lon": 72.0,
                "min_lat": 18.0,
                "max_lat": 20.0,
                "crs": "EPSG:4326"
            }
        )
        assert response.status_code == 422
    
    def test_query_point_uses_default_crs(
        self,
        test_client: TestClient,
        mock_raster_repository: MagicMock
    ):
        """Test that CRS defaults to EPSG:4326 when not provided."""
        with patch(
            "src_new.services.query.api.routes.get_raster_repository",
            return_value=mock_raster_repository
        ):
            response = test_client.post(
                "/query/point",
                json={
                    "lat": 19.0,
                    "lon": 73.0
                    # crs omitted
                }
            )
        
        assert response.status_code == 200
        # The request should succeed with default CRS
    
    def test_query_bbox_uses_default_crs(
        self,
        test_client: TestClient,
        mock_raster_repository: MagicMock
    ):
        """Test that CRS defaults to EPSG:4326 when not provided."""
        with patch(
            "src_new.services.query.api.routes.get_raster_repository",
            return_value=mock_raster_repository
        ):
            response = test_client.post(
                "/query/bbox",
                json={
                    "min_lon": 72.0,
                    "min_lat": 18.0,
                    "max_lon": 74.0,
                    "max_lat": 20.0
                    # crs omitted
                }
            )
        
        assert response.status_code == 200
        # The request should succeed with default CRS
