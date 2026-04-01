from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="ZTA-AI")
    environment: str = Field(default="development")
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)

    database_url: str = Field(
        default="postgresql+psycopg2://zta:zta@localhost:5432/zta_ai"
    )
    redis_url: str = Field(default="redis://localhost:6379/0")

    jwt_secret_key: str = Field(default="change-me")
    jwt_algorithm: str = Field(default="HS256")
    jwt_exp_minutes: int = Field(default=30)
    jwt_refresh_window_minutes: int = Field(default=5)

    use_mock_google_oauth: bool = Field(default=True)
    mock_google_token_prefix: str = Field(default="mock:")

    intent_cache_ttl_seconds: int = Field(default=24 * 60 * 60)
    daily_query_limit: int = Field(default=50)

    celery_broker_url: str = Field(default="redis://localhost:6379/1")
    celery_result_backend: str = Field(default="redis://localhost:6379/2")

    slm_provider: str = Field(default="simulator")
    slm_base_url: str = Field(default="https://integrate.api.nvidia.com/v1")
    slm_api_key: str = Field(default="")
    slm_model: str = Field(default="microsoft/phi-3-mini-128k-instruct")
    slm_temperature: float = Field(default=0.2)
    slm_top_p: float = Field(default=0.7)
    slm_max_tokens: int = Field(default=256)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
