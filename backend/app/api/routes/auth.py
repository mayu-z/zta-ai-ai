from __future__ import annotations

import uuid
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
    MFATOTPEnrollResponse,
    MFATOTPVerifyRequest,
    MFATOTPVerifyResponse,
    OIDCAuthRequest,
    RefreshRequest,
    RefreshResponse,
    SystemAdminMockLoginRequest,
)
from app.schemas.pipeline import ScopeContext

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)
settings = get_settings()


def _allowed_system_admin_emails() -> set[str]:
    return {
        item.strip().lower()
        for item in str(settings.system_admin_allowed_emails).split(",")
        if item.strip()
    }


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


@router.post("/system-admin/mock-login", response_model=AuthResponse)
def auth_system_admin_mock(payload: SystemAdminMockLoginRequest) -> AuthResponse:
    if settings.environment.strip().lower() == "production":
        raise AuthenticationError(
            message="System admin mock login is disabled in production",
            code="SYSTEM_ADMIN_MOCK_DISABLED",
        )

    if not bool(settings.enable_system_admin_mock_login):
        raise AuthenticationError(
            message="System admin mock login is disabled by configuration",
            code="SYSTEM_ADMIN_MOCK_DISABLED",
        )

    prefix = settings.system_admin_mock_token_prefix
    token = payload.admin_token.strip()
    if not token.startswith(prefix):
        raise AuthenticationError(
            message="System admin token prefix is invalid",
            code="SYSTEM_ADMIN_TOKEN_INVALID",
        )

    email = token[len(prefix) :].strip().lower()
    if "@" not in email:
        raise AuthenticationError(
            message="System admin email is invalid",
            code="SYSTEM_ADMIN_TOKEN_INVALID",
        )

    allowed = _allowed_system_admin_emails()
    if allowed and email not in allowed:
        raise AuthenticationError(
            message="System admin account is not allow-listed",
            code="SYSTEM_ADMIN_NOT_ALLOWED",
        )

    local_part = email.split("@", 1)[0]
    name = local_part.replace(".", " ").replace("_", " ").title() or "System Admin"
    session_id = str(uuid.uuid4())
    token_payload = {
        "sub": f"sysadmin:{email}",
        "email": email,
        "name": name,
        "persona_type": "system_admin",
        "is_system_admin": True,
        "session_id": session_id,
        "jti": str(uuid.uuid4()),
    }
    jwt_token = create_access_token(token_payload)

    return AuthResponse(
        jwt=jwt_token,
        user=AuthUser(
            id=f"sysadmin:{email}",
            email=email,
            name=name,
            persona="system_admin",
            department="global",
        ),
    )


@router.post("/oidc", response_model=AuthResponse)
def auth_oidc(
    payload: OIDCAuthRequest, db: Session = Depends(get_db)
) -> AuthResponse:
    token, user, _scope = identity_service.authenticate_oidc(
        db=db,
        id_token=payload.id_token,
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


@router.post("/mfa/totp/enroll", response_model=MFATOTPEnrollResponse)
def enroll_totp(
    scope: ScopeContext = Depends(get_current_scope),
    db: Session = Depends(get_db),
) -> MFATOTPEnrollResponse:
    enrolled = identity_service.enroll_totp(db=db, user_id=scope.user_id)
    return MFATOTPEnrollResponse(
        method=enrolled["method"],
        secret=enrolled["secret"],
        otpauth_uri=enrolled["otpauth_uri"],
    )


@router.post("/mfa/totp/verify", response_model=MFATOTPVerifyResponse)
def verify_totp(
    payload: MFATOTPVerifyRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    scope: ScopeContext = Depends(get_current_scope),
    db: Session = Depends(get_db),
) -> MFATOTPVerifyResponse:
    if credentials is None:
        raise AuthenticationError(message="Missing bearer token", code="TOKEN_REQUIRED")

    identity_service.verify_totp_code(db=db, user_id=scope.user_id, code=payload.code)

    decoded = decode_access_token(credentials.credentials)
    stripped = {k: v for k, v in decoded.items() if k not in {"exp", "iat"}}
    stripped["mfa_verified"] = True
    stripped["jti"] = str(uuid.uuid4())

    refreshed = create_access_token(stripped)
    return MFATOTPVerifyResponse(jwt=refreshed, mfa_verified=True)


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
