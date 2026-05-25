from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "l2l3-protocol"
    environment: str = "local"
    log_level: str = "INFO"
    log_dir: Path = Path("logs")

    database_url: str = "postgresql+asyncpg://l2l3:l2l3@localhost:5432/l2l3_protocol"

    agentmemory_base_url: str = "http://localhost:3111"
    agentmemory_secret: str | None = None
    agentmemory_enabled: bool = True

    mem0_enabled: bool = True
    mem0_vector_provider: str = "qdrant"
    mem0_qdrant_host: str = "localhost"
    mem0_qdrant_port: int = 6333
    mem0_collection_name: str = "l2l3_semantic_memory"
    mem0_llm_provider: str = "gemini"
    mem0_llm_model: str = "gemini-2.5-flash"
    mem0_embedder_provider: str = "gemini"
    mem0_embedder_model: str = "models/gemini-embedding-001"
    mem0_embedding_dims: int = 768
    gemini_api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")

    hermes_enabled: bool = True
    hermes_model: str = "deepseek-v4-pro"
    hermes_max_iterations: int = 20
    deepseek_api_key: str | None = Field(default=None, validation_alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = "https://api.deepseek.com"

    procedural_registry_path: Path = Path("registries")


@lru_cache
def get_settings() -> Settings:
    return Settings()
