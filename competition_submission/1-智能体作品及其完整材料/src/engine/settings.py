from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class EngineSettings(BaseSettings):
    engine_database_url: str = "postgresql://lex_engine@localhost:5432/lexcyber"
    redis_url: str = "redis://localhost:6379/0"
    service_token: str = ""
    app_callback_base_url: str = "http://java:8080"
    workflow_profile: str = "stub"
    app_env: str = "development"
    model_provider: str = "stub"
    model_name: str = "stub-general-v1"
    model_api_key: str = ""
    model_api_base_url: str = "https://api.openai.com/v1"
    model_timeout_seconds: float = 45.0
    model_max_retries: int = 2
    model_max_calls_per_task: int = 3
    allow_stub_model: bool = False
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "lexcyber"
    object_storage_provider: str = "filesystem"
    object_storage_root: str = "/data/objects"
    document_parse_timeout_seconds: int = 60
    knowledge_base_url: str = ""
    legal_source_search_enabled: bool = False
    sentencing_enabled: bool = False
    embedding_provider: str = ""
    embedding_model: str = ""
    embedding_api_key: str = ""
    knowledge_root: str = "/opt/lexcyber/knowledge"
    prompt_root: str = "/opt/lexcyber/prompts"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)


@lru_cache
def get_settings() -> EngineSettings:
    return EngineSettings()


settings = get_settings()
