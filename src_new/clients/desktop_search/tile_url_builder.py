"""Tile URL builder compatibility shim for desktop client.

In the new microservices architecture, tile URLs are built by the Tile Service.
This module provides a compatibility layer for the old desktop client code.
"""

from urllib.parse import quote


def build_xyz_url(file_path: str, tile_service_url: str = "http://127.0.0.1:8002") -> str:
    """Build a TiTiler XYZ tile URL for a local file.
    
    Args:
        file_path: Absolute path to the raster file
        tile_service_url: Base URL of the Tile Service
        
    Returns:
        XYZ tile URL template with {z}/{x}/{y} placeholders
    """
    # Convert file path to file:// URL
    if not file_path.startswith("file://"):
        file_path = f"file://{file_path}"
    
    encoded_path = quote(file_path, safe="/:")
    return f"{tile_service_url}/cog/WebMercatorQuad/tiles/{{z}}/{{x}}/{{y}}.png?url={encoded_path}"
