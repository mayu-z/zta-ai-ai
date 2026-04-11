from __future__ import annotations

from datetime import UTC, datetime

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.redis_client import redis_client
from app.core.security import decode_access_token
from app.db.models import Tenant, TenantStatus, User, UserStatus
from app.db.session import get_db
from app.identity.service import identity_service
from app.schemas.pipeline import ScopeContext

bearer_scheme = HTTPBearer(auto_error=False)


class SystemAdminContext(BaseModel):
    email: str
    session_id: str
    jti: str | None = None


def _allowed_system_admin_emails() -> set[str]:
    raw = get_settings().system_admin_allowed_emails
    return {
        item.strip().lower()
        for item in str(raw).split(",")
        if item.strip()
    }


def _ensure_not_killed(scope: ScopeContext) -> None:
    tenant_key = f"kill:tenant:{scope.tenant_id}"
    dept_key = f"kill:tenant:{scope.tenant_id}:department:{scope.department}"
    user_key = f"kill:user:{scope.user_id}"

    if redis_client.client.exists(tenant_key):
        raise AuthorizationError(
            message="Tenant sessions are currently revoked by IT head",
            code="TENANT_KILL_SWITCH",
        )
    if scope.department and redis_client.client.exists(dept_key):
        raise AuthorizationError(
            message="Department sessions are currently revoked",
            code="DEPARTMENT_KILL_SWITCH",
        )
    if redis_client.client.exists(user_key):
        raise AuthorizationError(
            message="User session is currently revoked", code="USER_KILL_SWITCH"
        )


def get_scope_from_token(db: Session, token: str) -> ScopeContext:
    payload = decode_access_token(token)

    jti = payload.get("jti")
    if jti and redis_client.client.exists(f"deny:{jti}"):
        raise AuthenticationError(
            message="Session has been logged out", code="TOKEN_REVOKED"
        )

    user_id = str(payload.get("sub"))
    tenant_id = str(payload.get("tenant_id"))

    tenant = db.scalar(
        select(Tenant).where(
            Tenant.id == tenant_id, Tenant.status == TenantStatus.active
        )
    )
    if not tenant:
        raise AuthenticationError(
            message="Tenant is invalid or inactive", code="TENANT_INVALID"
        )

    user = db.scalar(
        select(User).where(
            User.id == user_id,
            User.tenant_id == tenant_id,
            User.status == UserStatus.active,
        )
    )
    if not user:
        raise AuthenticationError(
            message="User account is invalid or inactive", code="USER_INVALID"
        )

    _session_id = str(payload.get("session_id") or f"sid-{user_id[:8]}")

    scope = identity_service.build_scope_context(
        user=user,
        tenant=tenant,
        session_id=_session_id,
        session_ip=payload.get("session_ip"),
        device_trusted=bool(payload.get("device_trusted", True)),
        mfa_verified=bool(payload.get("mfa_verified", True)),
        db=db,
    )

    _ensure_not_killed(scope)
    return scope


def get_current_scope(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> ScopeContext:
    if credentials is None:
        raise AuthenticationError(message="Missing bearer token", code="TOKEN_REQUIRED")
    return get_scope_from_token(db=db, token=credentials.credentials)


def get_current_system_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> SystemAdminContext:
    if credentials is None:
        raise AuthenticationError(message="Missing bearer token", code="TOKEN_REQUIRED")

    payload = decode_access_token(credentials.credentials)
    if not bool(payload.get("is_system_admin")):
        raise AuthorizationError(
            message="System admin privileges required",
            code="SYSTEM_ADMIN_ONLY",
        )

    email = str(payload.get("email") or payload.get("system_admin_email") or "").strip().lower()
    if not email:
        raise AuthenticationError(
            message="System admin token is missing email claim",
            code="TOKEN_INVALID_CLAIMS",
        )

    allowed_emails = _allowed_system_admin_emails()
    if allowed_emails and email not in allowed_emails:
        raise AuthorizationError(
            message="System admin account is not allow-listed",
            code="SYSTEM_ADMIN_NOT_ALLOWED",
        )

    jti = str(payload.get("jti") or "").strip() or None
    if jti and redis_client.client.exists(f"deny:{jti}"):
        raise AuthenticationError(
            message="Session has been logged out",
            code="TOKEN_REVOKED",
        )

    session_id = str(payload.get("session_id") or f"sysadmin-{email}")
    return SystemAdminContext(email=email, session_id=session_id, jti=jti)
