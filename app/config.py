from functools import lru_cache

from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):

    # --- API keys ---
    cohere_api_key: str = ""
    openai_api_key: str = ""

     # --- Databases ---
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/customer_support"     # async (FastAPI)
    sync_database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/customer_support"  # sync (agent tools)
    redis_url: str = "redis://localhost:6379/0"


     # --- Auth (JWT) ---
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24



@lru_cache()
def get_settings() -> Settings:
    s = Settings()

    if s.openai_api_key:
        os.environ.setdefault("OPENAI_API_KEY", s.openai_api_key)

    if s.cohere_api_key:
        os.environ.setdefault("COHERE_API_KEY", s.cohere_api_key)

    return s