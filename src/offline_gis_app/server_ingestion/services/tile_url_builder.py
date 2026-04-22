from offline_gis_app.server_ingestion.services.tiler_service import TiTilerUrlPolicy


_URL_POLICY = TiTilerUrlPolicy()


def build_xyz_url(file_path: str) -> str:
    return _URL_POLICY.build_url(file_path)
