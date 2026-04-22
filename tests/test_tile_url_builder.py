from offline_gis_app.server_ingestion.services.tile_url_builder import build_xyz_url


def test_tile_url_uses_tile_matrix_set_path():
    url = build_xyz_url("/tmp/demo.tif")
    assert "/cog/tiles/WebMercatorQuad/{z}/{x}/{y}" in url
    assert "url=file:///tmp/demo.tif" in url


def test_tile_url_normalizes_windows_drive_path():
    url = build_xyz_url(r"C:\data\demo raster.tif")
    assert "url=file:///C:/data/demo%20raster.tif" in url

