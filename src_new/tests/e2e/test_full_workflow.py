"""
End-to-end workflow test for the geospatial microservices system.

This test validates the complete data flow:
1. Upload sample.tif to Ingestion Service
2. Verify raster is cataloged in PostGIS
3. Request tile from Tile Service
4. Verify PNG tile is returned
5. Query by point from Query Service
6. Verify raster metadata is returned

Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 19.4
"""

import pytest
from pathlib import Path
from httpx import AsyncClient
import io
from PIL import Image

import socket

def _are_services_running() -> bool:
    for port in (8001, 8002, 8003):
        try:
            with socket.create_connection(("localhost", port), timeout=0.5):
                pass
        except OSError:
            return False
    return True

# Mark all tests in this module as async using anyio, and skip if services aren't running
pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(not _are_services_running(), reason="E2E test requires running services on ports 8001, 8002, and 8003")
]


class TestFullWorkflow:
    """End-to-end workflow tests for the complete system."""
    
    async def test_full_ingestion_to_query_workflow(
        self,
        sample_tif_path: Path,
        db_session,
    ):
        """
        Test the complete workflow from upload to query.
        
        Steps:
        1. Upload sample.tif to Ingestion Service
        2. Verify cataloged status
        3. Verify raster exists in PostGIS
        4. Request tile from Tile Service
        5. Verify PNG tile is valid
        6. Query by point from Query Service
        7. Verify raster is returned in query results
        
        This test requires all three services to be running:
        - Ingestion Service (port 8001)
        - Tile Service (port 8002)
        - Query Service (port 8003)
        """
        # TODO: This test requires actual service deployment
        # For now, we'll create a placeholder that can be implemented
        # once services are fully operational
        
        # Configuration
        ingestion_url = "http://localhost:8001"
        tile_url = "http://localhost:8002"
        query_url = "http://localhost:8003"
        
        # Step 1: Upload sample.tif
        async with AsyncClient(base_url=ingestion_url) as client:
            with open(sample_tif_path, "rb") as f:
                files = {"file": (sample_tif_path.name, f, "image/tiff")}
                response = await client.post("/upload", files=files)
                
            assert response.status_code == 200
            upload_data = response.json()
            assert "raster_id" in upload_data
            assert upload_data["status"] == "cataloged"
            assert upload_data["bbox"] is not None
            
            raster_id = upload_data["raster_id"]
            bbox = upload_data["bbox"]
        
        # Step 2: Verify cataloged status
        async with AsyncClient(base_url=ingestion_url) as client:
            response = await client.get(f"/status/{raster_id}")
            assert response.status_code == 200
            status_data = response.json()
            assert status_data["status"] == "cataloged"
            assert status_data["progress"] == 1.0
            assert status_data["error"] is None
        
        # Step 3: Verify raster exists in PostGIS/SQLite
        # If db_session is a MagicMock, let's query the actual database using the settings URL!
        from unittest.mock import MagicMock
        if hasattr(db_session, "execute") and not isinstance(db_session, MagicMock):
            actual_db = db_session
        else:
            from sqlalchemy import create_engine, text
            from src_new.shared.config import settings
            engine = create_engine(settings.database_url)
            actual_db = engine.connect()

        try:
            try:
                result = actual_db.execute(
                    text("SELECT raster_id, file_path, crs FROM raster_assets WHERE raster_id = :rid"),
                    {"rid": raster_id}
                )
                row = result.fetchone()
            except Exception:
                result = actual_db.execute(
                    text("SELECT id, file_path, crs FROM raster_assets WHERE id = :rid"),
                    {"rid": raster_id}
                )
                row = result.fetchone()
            
            assert row is not None
            assert row[0] == raster_id
        finally:
            if not hasattr(db_session, "execute") or isinstance(db_session, MagicMock):
                actual_db.close()
        
        # Step 4: Request tile from Tile Service
        # Request tile at zoom level 0, tile (0, 0)
        async with AsyncClient(base_url=tile_url) as client:
            response = await client.get(
                "/tiles/0/0/0.png",
                params={"raster_id": raster_id}
            )
            assert response.status_code == 200
            assert response.headers["content-type"] == "image/png"
            
            # Step 5: Verify PNG tile is valid
            tile_data = response.content
            assert len(tile_data) > 0
            
            # Verify it's a valid PNG by opening with PIL
            img = Image.open(io.BytesIO(tile_data))
            assert img.format == "PNG"
            assert img.size == (256, 256)  # Standard tile size
        
        # Step 6: Query by point from Query Service
        # Use the center point of the bounding box
        center_lon = (bbox["min_lon"] + bbox["max_lon"]) / 2
        center_lat = (bbox["min_lat"] + bbox["max_lat"]) / 2
        
        async with AsyncClient(base_url=query_url) as client:
            response = await client.post(
                "/query/point",
                json={
                    "lat": center_lat,
                    "lon": center_lon,
                    "crs": "EPSG:4326"
                }
            )
            assert response.status_code == 200
            query_data = response.json()
            
            # Step 7: Verify raster is returned in query results
            assert "rasters" in query_data
            assert query_data["count"] >= 1
            
            # Find our uploaded raster in the results
            found = False
            for raster in query_data["rasters"]:
                if raster["raster_id"] == raster_id:
                    found = True
                    assert raster["crs"] is not None
                    assert raster["bbox"] is not None
                    break
            
            assert found, f"Uploaded raster {raster_id} not found in query results"
    
    async def test_tile_preview_endpoint(self, sample_tif_path: Path):
        """
        Test the tile preview endpoint.
        
        Steps:
        1. Upload sample.tif
        2. Request preview thumbnail
        3. Verify 512x512 PNG is returned
        
        Requirements: 14.5
        """
        ingestion_url = "http://localhost:8001"
        tile_url = "http://localhost:8002"
        
        # Upload raster
        async with AsyncClient(base_url=ingestion_url) as client:
            with open(sample_tif_path, "rb") as f:
                files = {"file": (sample_tif_path.name, f, "image/tiff")}
                response = await client.post("/upload", files=files)
            
            assert response.status_code == 200
            raster_id = response.json()["raster_id"]
        
        # Request preview
        async with AsyncClient(base_url=tile_url) as client:
            response = await client.get(f"/preview/{raster_id}")
            assert response.status_code == 200
            assert response.headers["content-type"] == "image/png"
            
            # Verify it's a 512x512 PNG
            img = Image.open(io.BytesIO(response.content))
            assert img.format == "PNG"
            assert img.size == (512, 512)
    
    async def test_tile_metadata_endpoint(self, sample_tif_path: Path):
        """
        Test the tile metadata endpoint.
        
        Steps:
        1. Upload sample.tif
        2. Request tile metadata
        3. Verify bounds and zoom levels are returned
        
        Requirements: 14.5
        """
        ingestion_url = "http://localhost:8001"
        tile_url = "http://localhost:8002"
        
        # Upload raster
        async with AsyncClient(base_url=ingestion_url) as client:
            with open(sample_tif_path, "rb") as f:
                files = {"file": (sample_tif_path.name, f, "image/tiff")}
                response = await client.post("/upload", files=files)
            
            assert response.status_code == 200
            raster_id = response.json()["raster_id"]
        
        # Request metadata
        async with AsyncClient(base_url=tile_url) as client:
            response = await client.get(f"/metadata/{raster_id}")
            assert response.status_code == 200
            
            metadata = response.json()
            assert "bounds" in metadata
            assert "minzoom" in metadata
            assert "maxzoom" in metadata
            assert "center" in metadata
            
            # Verify bounds structure
            bounds = metadata["bounds"]
            assert "min_lon" in bounds
            assert "min_lat" in bounds
            assert "max_lon" in bounds
            assert "max_lat" in bounds
    
    async def test_bbox_query_workflow(self, sample_tif_path: Path):
        """
        Test bounding box query workflow.
        
        Steps:
        1. Upload sample.tif
        2. Query by bounding box
        3. Verify raster is returned
        
        Requirements: 14.2
        """
        ingestion_url = "http://localhost:8001"
        query_url = "http://localhost:8003"
        
        # Upload raster
        async with AsyncClient(base_url=ingestion_url) as client:
            with open(sample_tif_path, "rb") as f:
                files = {"file": (sample_tif_path.name, f, "image/tiff")}
                response = await client.post("/upload", files=files)
            
            assert response.status_code == 200
            upload_data = response.json()
            raster_id = upload_data["raster_id"]
            bbox = upload_data["bbox"]
        
        # Query by bounding box (use the raster's own bbox)
        async with AsyncClient(base_url=query_url) as client:
            response = await client.post(
                "/query/bbox",
                json={
                    "min_lon": bbox["min_lon"],
                    "min_lat": bbox["min_lat"],
                    "max_lon": bbox["max_lon"],
                    "max_lat": bbox["max_lat"],
                    "crs": "EPSG:4326"
                }
            )
            assert response.status_code == 200
            query_data = response.json()
            
            assert "rasters" in query_data
            assert query_data["count"] >= 1
            
            # Verify our raster is in the results
            raster_ids = [r["raster_id"] for r in query_data["rasters"]]
            assert raster_id in raster_ids
    
    async def test_health_endpoints(self):
        """
        Test health check endpoints for all services.
        
        Verifies that all three services report healthy status.
        
        Requirements: 18.5
        """
        services = [
            ("Ingestion Service", "http://localhost:8001"),
            ("Tile Service", "http://localhost:8002"),
            ("Query Service", "http://localhost:8003"),
        ]
        
        for service_name, base_url in services:
            async with AsyncClient(base_url=base_url) as client:
                response = await client.get("/health")
                assert response.status_code == 200, f"{service_name} health check failed"
                
                health_data = response.json()
                assert "status" in health_data
                assert health_data["status"] in ["healthy", "degraded"]
                
                # Ingestion service should report disk space
                if "Ingestion" in service_name:
                    assert "disk_space_gb" in health_data
                    assert health_data["disk_space_gb"] > 0
