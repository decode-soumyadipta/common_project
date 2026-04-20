from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables and .env."""
    database_url: str = "sqlite:///./offline_gis.db"
    data_root: Path = Path(".").resolve()
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    deployment_topology: Literal["same-machine", "split-lan", "hybrid"] = "same-machine"
    server_api_base_url: str = ""
    max_ingest_workers: int = 5
    ingest_checkpoint_interval: int = 1
    ingest_item_max_retries: int = 3
    titiler_base_url: str = "http://127.0.0.1:8081"
    titiler_tile_matrix_set_id: str = "WebMercatorQuad"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        case_sensitive=False,
    )


settings = Settings()
