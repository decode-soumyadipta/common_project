"""
Pytest configuration and fixtures for src_new/ test suite.

This module provides shared fixtures for:
- PostGIS test database setup/teardown
- Mock service instances
- Sample geospatial test data paths
"""

import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


# Database fixtures
@pytest.fixture(scope="session")
def db_session() -> Generator:
    """
    Provides a PostGIS test database session with setup and teardown.
    
    This fixture:
    - Creates a test database with PostGIS extension
    - Sets up test schema and tables
    - Yields a database session for tests
    - Cleans up all test data on teardown
    
    Yields:
        Database session object (psycopg2 connection or SQLAlchemy session)
    """
    # TODO: Implement actual PostGIS test database setup For now, return a mock to allow tests to be written
    mock_db = MagicMock()
    mock_db.execute = MagicMock()
    mock_db.commit = MagicMock()
    mock_db.rollback = MagicMock()
    mock_db.close = MagicMock()
    
    yield mock_db
    
    # Cleanup
    mock_db.close()


@pytest.fixture
def mock_ingestion_service() -> MagicMock:
    """
    Provides a mock Ingestion Service for testing without actual service deployment.
    
    Returns:
        Mock object with ingestion service methods
    """
    mock_service = MagicMock()
    
    # Mock upload endpoint
    mock_service.upload = AsyncMock(return_value={
        "raster_id": "test-raster-123",
        "status": "cataloged",
        "message": "Upload successful",
        "bbox": {
            "min_lon": -180.0,
            "min_lat": -90.0,
            "max_lon": 180.0,
            "max_lat": 90.0
        }
    })
    
    # Mock status endpoint
    mock_service.get_status = AsyncMock(return_value={
        "raster_id": "test-raster-123",
        "status": "cataloged",
        "progress": 1.0,
        "error": None
    })
    
    # Mock health endpoint
    mock_service.health = AsyncMock(return_value={
        "status": "healthy",
        "database": True,
        "disk_space_gb": 100.0
    })
    
    return mock_service


@pytest.fixture
def mock_query_service() -> MagicMock:
    """
    Provides a mock Query Service for testing without actual service deployment.
    
    Returns:
        Mock object with query service methods
    """
    mock_service = MagicMock()
    
    # Mock point query endpoint
    mock_service.query_point = AsyncMock(return_value={
        "rasters": [
            {
                "raster_id": "test-raster-123",
                "file_path": "/data/test.tif",
                "crs": "EPSG:4326",
                "resolution": 0.02,
                "bbox": {
                    "min_lon": -180.0,
                    "min_lat": -90.0,
                    "max_lon": 180.0,
                    "max_lat": 90.0
                }
            }
        ],
        "count": 1
    })
    
    # Mock bbox query endpoint
    mock_service.query_bbox = AsyncMock(return_value={
        "rasters": [],
        "count": 0
    })
    
    # Mock health endpoint
    mock_service.health = AsyncMock(return_value={
        "status": "healthy",
        "database": True
    })
    
    return mock_service


# Test data fixtures
@pytest.fixture(scope="session")
def sample_tif_path() -> Path:
    """
    Provides path to a small sample GeoTIFF for testing.
    
    Returns:
        Path to sample.tif in tests/data/ directory
    """
    # Use the smallest available test file (dem.tif at 5.1MB)
    source_path = Path(__file__).parent.parent.parent / "data_test" / "dem.tif"
    target_path = Path(__file__).parent / "data" / "sample.tif"
    
    # Create symlink if it doesn't exist
    if not target_path.exists() and source_path.exists():
        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            target_path.symlink_to(source_path)
        except OSError:
            # If symlink fails (e.g., on Windows), copy the file
            import shutil
            shutil.copy2(source_path, target_path)
    
    return target_path


@pytest.fixture(scope="session")
def sample_j2k_path() -> Path:
    """
    Provides path to a small sample JPEG2000 for testing.
    
    Returns:
        Path to sample.j2k in tests/data/ directory
    """
    source_path = Path(__file__).parent.parent.parent / "data_test" / "T44SND_20250706T052241_AOT_10m.j2k"
    target_path = Path(__file__).parent / "data" / "sample.j2k"
    
    # Create symlink if it doesn't exist
    if not target_path.exists() and source_path.exists():
        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            target_path.symlink_to(source_path)
        except OSError:
            # If symlink fails (e.g., on Windows), copy the file
            import shutil
            shutil.copy2(source_path, target_path)
    
    return target_path


@pytest.fixture
def temp_data_dir() -> Generator[Path, None, None]:
    """
    Provides a temporary directory for test data that is cleaned up after the test.
    
    Yields:
        Path to temporary directory
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_raster_metadata() -> dict:
    """
    Provides sample raster metadata for testing.
    
    Returns:
        Dictionary with sample raster metadata
    """
    return {
        "raster_id": "test-raster-123",
        "file_path": "/data/test.tif",
        "crs": "EPSG:4326",
        "resolution": 0.02,
        "bbox": {
            "min_lon": -180.0,
            "min_lat": -90.0,
            "max_lon": 180.0,
            "max_lat": 90.0
        },
        "upload_date": "2024-01-01T00:00:00Z"
    }


@pytest.fixture
def sample_tile_request() -> dict:
    """
    Provides sample tile request parameters for testing.
    
    Returns:
        Dictionary with sample tile request parameters
    """
    return {
        "z": 0,
        "x": 0,
        "y": 0,
        "raster_id": "test-raster-123",
        "contrast": 1.0,
        "brightness": 0.0,
        "colormap": None
    }
