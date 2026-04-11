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
    api_host: str = Field(default="127.0.0.1")
    api_port: int = Field(default=8000)
    allowed_origins: list[str] = Field(
        default=["http://localhost:8080", "http://localhost:3000"]
    )

    database_url: str = Field(
        default="postgresql+psycopg2://zta:zta@localhost:5432/zta_ai"
    )
    redis_url: str = Field(default="redis://localhost:6379/0")

    secrets_backend: str = Field(default="env")
    secrets_cache_ttl_seconds: int = Field(default=300)
    secrets_file_path: str = Field(default="")
    aws_secrets_manager_region: str = Field(default="")
    aws_secrets_manager_prefix: str = Field(default="")
    vault_addr: str = Field(default="")
    vault_token: str = Field(default="")
    vault_token_env_var: str = Field(default="VAULT_TOKEN")
    vault_kv_mount: str = Field(default="secret")
    vault_secret_path_prefix: str = Field(default="zta-ai/")

    jwt_secret_key: str = Field(default="change-me")  # keep default for dev
    jwt_algorithm: str = Field(default="HS256")
    jwt_exp_minutes: int = Field(default=30)
    jwt_refresh_window_minutes: int = Field(default=5)

    auth_provider: str = Field(default="mock_google")
    use_mock_google_oauth: bool = Field(default=False)
    mock_google_token_prefix: str = Field(default="mock:")
    oidc_issuer: str = Field(default="")
    oidc_audience: str = Field(default="")
    oidc_jwks_url: str = Field(default="")
    oidc_shared_secret: str = Field(default="")
    oidc_allowed_algorithms: str = Field(default="RS256,HS256")
    saml_idp_metadata_url: str = Field(default="")
    saml_sp_entity_id: str = Field(default="")
    egress_allowed_hosts: str = Field(default="")
    service_mtls_enabled: bool = Field(default=False)
    service_mtls_client_cert_path: str = Field(default="")
    service_mtls_client_key_path: str = Field(default="")
    service_mtls_ca_bundle_path: str = Field(default="")
    mfa_totp_issuer: str = Field(default="ZTA-AI")
    mfa_totp_period_seconds: int = Field(default=30)
    mfa_totp_window_steps: int = Field(default=1)

    intent_cache_ttl_seconds: int = Field(default=24 * 60 * 60)
    daily_query_limit: int = Field(default=50)
    ipeds_tenant_id: str = Field(
        default="ipeds-tenant-00000000-0000-0000-0000-000000000001"
    )
    default_local_source_type: str = Field(default="ipeds_claims")

    celery_broker_url: str = Field(default="redis://localhost:6379/1")
    celery_result_backend: str = Field(default="redis://localhost:6379/2")

    slm_provider: str = Field(default="simulator")
    slm_base_url: str = Field(default="https://integrate.api.nvidia.com/v1")
    slm_api_key: str = Field(default="")  # Deprecated: use SLM_API_KEYS for multiple keys
    slm_api_keys: str = Field(default="")  # Comma-separated list of API keys for round-robin
    slm_requests_per_minute: int = Field(default=50)  # Rate limit per key per minute
    slm_model: str = Field(default="microsoft/phi-3-mini-128k-instruct")
    slm_temperature: float = Field(default=0.7)
    slm_top_p: float = Field(default=0.95)
    slm_max_tokens: int = Field(default=512)
    slm_zero_learning_enforced: bool = Field(default=True)
    slm_zero_learning_header_name: str = Field(default="X-ZTA-Zero-Learning")
    slm_zero_learning_header_value: str = Field(default="true")
    slm_zero_learning_audit_log_enabled: bool = Field(default=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
