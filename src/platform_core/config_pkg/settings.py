from pathlib import Path
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Distributed system configuration loaded from environment variables."""

    # 1. Topology & Database
    deployment_topology: Literal["same-machine", "split-lan", "hybrid", "distributed"] = "same-machine"
    database_url: str = "sqlite:///./offline_gis.db"
    data_root: Path = Path(".").resolve()
    
    # 2. Server A: Gateway & Rendering
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    gateway_url: str = "http://127.0.0.1:8000"
    server_api_base_url: str = "" # Alias for gateway_url
    
    # 3. Server B: Processor Node
    processor_host: str = "0.0.0.0"
    processor_port: int = 8002
    processor_url: str = "http://127.0.0.1:8002"
    
    # 4. Rendering (TiTiler)
    titiler_base_url: str = "http://127.0.0.1:8081"
    titiler_tile_matrix_set_id: str = "WebMercatorQuad"
    
    # 5. Ingestion Performance
    max_ingest_workers: int = 5
    ingest_checkpoint_interval: int = 1
    ingest_item_max_retries: int = 3
    ingest_memory_budget_mb: int = 512
    ingest_window_chunk_size: int = 1024
    ingest_enable_cog_conversion: bool = True
    ingest_cog_overwrite: bool = False
    
    # 6. GDAL / COG Optimization
    cog_blocksize: int = 512
    cog_compression: str = "LZW"
    cog_overview_resampling: str = "average"

    # 7. Output Organization
    ingest_organize_outputs: bool = True
    ingest_output_base_dir: str = "processed_outputs"
    
    # 8. System & Logging
    log_level: str = "INFO"
    debug: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        case_sensitive=False,
        extra="ignore", # Allow extra fields in .env without crashing
    )

settings = Settings()
