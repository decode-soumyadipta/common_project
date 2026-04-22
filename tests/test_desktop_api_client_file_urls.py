from offline_gis_app.client_backend.desktop.api_client import DesktopApiClient


def test_to_file_url_windows_drive_path():
    file_url = DesktopApiClient._to_file_url(r"C:\\tiles\\rgb raster.tif")
    assert file_url == "file:///C:/tiles/rgb raster.tif"


def test_to_file_url_posix_path():
    file_url = DesktopApiClient._to_file_url("/tmp/rgb.tif")
    assert file_url == "file:///tmp/rgb.tif"
