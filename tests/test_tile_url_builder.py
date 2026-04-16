from offline_gis_app.services.tile_url_builder import build_xyz_url


def test_tile_url_uses_tile_matrix_set_path():
    url = build_xyz_url("/tmp/demo.tif")
    assert "/cog/tiles/WebMercatorQuad/{z}/{x}/{y}" in url
    assert "url=file:///tmp/demo.tif" in url

