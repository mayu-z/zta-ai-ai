from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.deps import get_current_scope
from app.core.config import get_settings
from app.core.exceptions import AuthenticationError
from app.core.redis_client import redis_client
from app.core.security import create_access_token, decode_access_token
from app.db.session import get_db
from app.identity.service import identity_service
from app.schemas.auth import (
    AuthResponse,
    AuthUser,
    GoogleAuthRequest,
    LogoutResponse,
    RefreshRequest,
    RefreshResponse,
)
from app.schemas.pipeline import ScopeContext

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)
settings = get_settings()


@router.post("/google", response_model=AuthResponse)
def auth_google(
    payload: GoogleAuthRequest, db: Session = Depends(get_db)
) -> AuthResponse:
    token, user, _scope = identity_service.authenticate_google(
        db=db, google_token=payload.google_token
    )
    return AuthResponse(
        jwt=token,
        user=AuthUser(
            id=user.id,
            email=user.email,
            name=user.name,
            persona=user.persona_type.value,
            department=user.department,
        ),
    )


@router.post("/refresh", response_model=RefreshResponse)
def refresh_token(payload: RefreshRequest) -> RefreshResponse:
    decoded = decode_access_token(payload.jwt)

    exp = int(decoded.get("exp", 0))
    now = int(datetime.now(tz=UTC).timestamp())
    seconds_left = exp - now
    refresh_window = settings.jwt_refresh_window_minutes * 60

    if seconds_left <= 0:
        raise AuthenticationError(
            message="Token is already expired", code="TOKEN_EXPIRED"
        )
    if seconds_left > refresh_window:
        raise AuthenticationError(
            message="Token is not eligible for refresh yet",
            code="TOKEN_REFRESH_TOO_EARLY",
        )

    stripped = {k: v for k, v in decoded.items() if k not in {"exp", "iat"}}
    refreshed = create_access_token(stripped)
    return RefreshResponse(jwt=refreshed)


@router.post("/logout", response_model=LogoutResponse)
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    _scope: ScopeContext = Depends(get_current_scope),
) -> LogoutResponse:
    if credentials is None:
        raise AuthenticationError(message="Missing bearer token", code="TOKEN_REQUIRED")

    payload = decode_access_token(credentials.credentials)
    jti = payload.get("jti")
    exp = int(payload.get("exp", 0))

    if jti:
        ttl = max(exp - int(datetime.now(tz=UTC).timestamp()), 30 * 60)
        redis_client.client.setex(f"deny:{jti}", ttl, "1")

    return LogoutResponse(message="Logged out successfully")
