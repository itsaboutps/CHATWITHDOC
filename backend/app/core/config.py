from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    gemini_api_key: str = ""
    # Defaults adjusted to models confirmed available via user's key list.
    # embedding-001 kept as fallback but prefer newer text-embedding-004.
    embedding_model: str = "text-embedding-004"
    # gemini-1.5-flash not available for this key; switch to gemini-flash-latest.
    generation_model: str = "gemini-flash-latest"
    # Optional small delay (ms) between embedding API calls to reduce 429 rate-limit bursts.
    embedding_rate_delay_ms: int = 150

    database_url: str = "sqlite+aiosqlite:///./app.db"
    qdrant_url: str
    qdrant_collection: str = "documents"

    minio_endpoint: str
    minio_bucket: str = "documents"
    minio_root_user: str
    minio_root_password: str


    chunk_size: int = 800
    chunk_overlap: int = 120
    similarity_threshold: float = 0.55
    top_k: int = 5
    sync_ingest: bool = False
    api_key: str | None = None
    admin_reset_token: str | None = None  # protects /admin/reset endpoint

    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
