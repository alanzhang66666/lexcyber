from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql://lex:lex@localhost:5432/lex"
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "lexcyber"
    knowledge_base_url: str = ""
    retrieval_gateway_url: str = "http://localhost:8002"
    model_gateway_url: str = "http://localhost:8001"
    model_provider: str = "stub"
    model_name: str = "stub-general-v1"
    model_api_key: str = ""
    model_api_base_url: str = "https://api.openai.com/v1"
    model_timeout_seconds: float = 45.0
    model_max_retries: int = 2
    model_max_calls_per_task: int = 3
    model_max_concurrency: int = 2
    allow_stub_model: bool = False
    prompt_root: str = "/opt/lexcyber/prompts"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
