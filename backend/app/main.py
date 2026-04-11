from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import admin, auth, chat, pipeline_monitor
from app.core.config import get_settings
from app.core.egress import enforce_egress_url_allowed
from app.core.exceptions import ZTAError
from app.core.mtls import validate_service_mtls_configuration
from app.core.secret_manager import secret_manager, validate_secret_store_configuration
from app.core.zero_learning import validate_zero_learning_configuration
from app.core.redis_client import redis_client
from app.db.init_db import create_all_tables

settings = get_settings()
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name, version="1.0.0")

cors_allowed_origins = [
    "http://172.31.42.23:8080",
    "http://localhost:8080",
    "http://localhost:3000",
    "http://3.25.168.174:8080",
    "http://3.25.168.174",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def enforce_startup_security() -> None:
    auth_provider = settings.auth_provider.strip().lower()
    allowed_providers = {"mock_google", "oidc", "saml"}

    if auth_provider not in allowed_providers:
        raise RuntimeError(
            "AUTH_PROVIDER must be one of: mock_google, oidc, saml"
        )

    if settings.environment != "production":
        return

    validate_secret_store_configuration(settings)

    jwt_secret = secret_manager.get_secret(
        "JWT_SECRET_KEY",
        fallback=settings.jwt_secret_key,
    ).strip()

    if settings.use_mock_google_oauth:
        raise RuntimeError("USE_MOCK_GOOGLE_OAUTH must be false in production")

    if auth_provider == "mock_google":
        raise RuntimeError(
            "AUTH_PROVIDER=mock_google is not allowed in production. Use oidc or saml."
        )

    if jwt_secret == "change-me" or len(jwt_secret) < 32:
        raise RuntimeError(
            "JWT_SECRET_KEY must be at least 32 characters and not use default placeholder in production. "
            'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
        )

    if auth_provider == "oidc":
        oidc_shared_secret = secret_manager.get_secret(
            "OIDC_SHARED_SECRET",
            fallback=settings.oidc_shared_secret,
        ).strip()
        if not settings.oidc_issuer or not settings.oidc_audience:
            raise RuntimeError(
                "OIDC_ISSUER and OIDC_AUDIENCE are required when AUTH_PROVIDER=oidc in production"
            )
        if not settings.oidc_jwks_url and not oidc_shared_secret:
            raise RuntimeError(
                "Provide OIDC_JWKS_URL or OIDC_SHARED_SECRET when AUTH_PROVIDER=oidc in production"
            )

    if auth_provider == "saml":
        if not settings.saml_idp_metadata_url or not settings.saml_sp_entity_id:
            raise RuntimeError(
                "SAML_IDP_METADATA_URL and SAML_SP_ENTITY_ID are required when AUTH_PROVIDER=saml in production"
            )

    if not settings.mfa_totp_issuer.strip():
        raise RuntimeError(
            "MFA_TOTP_ISSUER must be configured in production"
        )

    if settings.mfa_totp_period_seconds < 15:
        raise RuntimeError(
            "MFA_TOTP_PERIOD_SECONDS must be >= 15 in production"
        )

    if settings.mfa_totp_window_steps < 0 or settings.mfa_totp_window_steps > 5:
        raise RuntimeError(
            "MFA_TOTP_WINDOW_STEPS must be between 0 and 5 in production"
        )

    if not settings.slm_base_url.strip().lower().startswith("https://"):
        raise RuntimeError("SLM_BASE_URL must use https in production")

    validate_service_mtls_configuration(
        enabled=settings.service_mtls_enabled,
        client_cert_path=settings.service_mtls_client_cert_path,
        client_key_path=settings.service_mtls_client_key_path,
        ca_bundle_path=settings.service_mtls_ca_bundle_path,
    )

    validate_zero_learning_configuration(settings)

    if not settings.egress_allowed_hosts.strip():
        raise RuntimeError(
            "EGRESS_ALLOWED_HOSTS must be configured in production"
        )

    enforce_egress_url_allowed(
        target_url=settings.slm_base_url,
        raw_allowlist=settings.egress_allowed_hosts,
    )


@app.on_event("startup")
def on_startup() -> None:
    enforce_startup_security()
    create_all_tables()

    try:
        redis_client.client.ping()
        if redis_client.using_in_memory_fallback:
            logger.warning(
                "Redis fallback mode is active. Intent cache and pipeline monitor pub/sub will be degraded."
            )
        else:
            logger.info("Redis connection established")
    except Exception:
        logger.exception("Redis health check failed during startup")


@app.exception_handler(ZTAError)
async def zta_error_handler(_request: Request, exc: ZTAError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.message,
            "code": exc.code,
            "timestamp": datetime.now(tz=UTC).isoformat(),
        },
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(_request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "code": "INTERNAL_ERROR",
            "details": str(exc),
            "timestamp": datetime.now(tz=UTC).isoformat(),
        },
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(admin.router)
app.include_router(pipeline_monitor.router)
