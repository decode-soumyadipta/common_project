from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./offline_gis.db"
    data_root: Path = Path(".").resolve()
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    titiler_base_url: str = "http://127.0.0.1:8081"
    titiler_tile_matrix_set_id: str = "WebMercatorQuad"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        case_sensitive=False,
    )


settings = Settings()
