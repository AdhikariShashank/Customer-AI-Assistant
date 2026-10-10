from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API keys
    cohere_api_key: str = ""
    openai_api_key: str = ""

    # Databases
    database_url: str
    sync_database_url: str
    redis_url: str = "redis://localhost:6379/0"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "customer-support"
    embed_dim: int = 1536

    # Auth
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    # Storage
    temp_documents_path: str = "storage/documents"



@lru_cache()
def get_settings() -> Settings:
    s = Settings()

    if s.openai_api_key:
        os.environ.setdefault("OPENAI_API_KEY", s.openai_api_key)

    if s.cohere_api_key:
        os.environ.setdefault("COHERE_API_KEY", s.cohere_api_key)

    return s