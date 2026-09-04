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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)


@lru_cache
def get_settings() -> EngineSettings:
    return EngineSettings()


settings = get_settings()
