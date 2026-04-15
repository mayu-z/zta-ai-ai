from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="zta-agentic-service")
    environment: str = Field(default="local")

    database_url: str = Field(default="postgresql+psycopg://zta:zta@localhost:5432/zta_agentic")
    redis_url: str = Field(default="redis://localhost:6379/0")
    broker_url: str = Field(default="redis://localhost:6379/1")

    llm_provider: str = Field(default="stub")
    llm_model: str = Field(default="intent-stub")

    intent_auto_select_threshold: float = Field(default=0.82)
    intent_clarification_threshold: float = Field(default=0.65)
    intent_margin_threshold: float = Field(default=0.08)

    max_chain_depth: int = Field(default=3)
    tokenization_secret_key: str = Field(default="change-me")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
