from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import admin, auth, chat, pipeline_monitor
from app.core.config import get_settings
from app.core.exceptions import ZTAError
from app.core.redis_client import redis_client
from app.db.init_db import create_all_tables

settings = get_settings()
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    if settings.environment == "production" and settings.jwt_secret_key == "change-me":
        raise RuntimeError(
            "JWT_SECRET_KEY must be set to a secure random value in production. "
            'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
        )
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
