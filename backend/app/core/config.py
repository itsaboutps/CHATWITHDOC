from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    gemini_api_key: str = ""
    embedding_model: str = "text-embedding-004"  # available embedding model
    generation_model: str = "gemini-2.5-flash"   # upgraded default from gemini-flash-latest
    embedding_rate_delay_ms: int = 150

    # Local fallback models (for offline / keyless operation)
    enable_local_embedding_fallback: bool = True
    local_embedding_model: str = "all-MiniLM-L6-v2"  # sentence-transformers model name
    enable_local_generation_fallback: bool = True
    local_generation_model: str = "gpt4all-falcon-q4_0"  # gpt4all model file name or alias
    local_generation_max_tokens: int = 512

    # Set use_in_memory=True to bypass any SQL database usage.
    use_in_memory: bool = True
    database_url: str = "sqlite+aiosqlite:///./app.db"  # ignored when in-memory

    # Embedded Qdrant in-memory (optional). If use_qdrant_embedded=True we build an in-memory collection.
    use_qdrant_embedded: bool = True
    qdrant_collection: str = "documents"

    minio_endpoint: str = ""
    minio_bucket: str = "documents"
    minio_root_user: str = ""
    minio_root_password: str = ""

    chunk_size: int = 800
    chunk_overlap: int = 120
    similarity_threshold: float = 0.55
    top_k: int = 5
    sync_ingest: bool = False
    use_qdrant_embedded: bool = True  # embedded in-memory Qdrant is canonical vector store
    api_key: Optional[str] = None
    admin_reset_token: Optional[str] = None

    log_level: str = "INFO"
    # Enable verbose pipeline stage logs (ingest + ask flow) when True
    pipeline_debug: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # ignore legacy environment variables (postgres_*, redis_url, etc.)

    def model_post_init(self, __context):  # type: ignore
        # Force in-memory mode dominance: if use_in_memory True, ignore any DATABASE_URL env
        if self.use_in_memory:
            self.database_url = "sqlite+aiosqlite:///./app.db"
        # Backward compatibility for legacy env variable names
        if not self.embedding_model and getattr(self, 'EMBEDDING_MODEL', None):  # type: ignore
            self.embedding_model = getattr(self, 'EMBEDDING_MODEL')  # type: ignore
        if not self.generation_model and getattr(self, 'GENERATION_MODEL', None):  # type: ignore
            self.generation_model = getattr(self, 'GENERATION_MODEL')  # type: ignore


@lru_cache
def get_settings() -> Settings:
    return Settings()
