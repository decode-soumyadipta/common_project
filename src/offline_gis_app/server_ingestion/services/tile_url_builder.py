from urllib.parse import quote

from offline_gis_app.config.settings import settings


def build_xyz_url(file_path: str) -> str:
    encoded_path = quote(file_path, safe="/:")
    return (
        f"{settings.titiler_base_url}/cog/tiles/{settings.titiler_tile_matrix_set_id}/{{z}}/{{x}}/{{y}}.png"
        f"?url=file://{encoded_path}"
    )
