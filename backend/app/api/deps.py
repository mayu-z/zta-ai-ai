from __future__ import annotations

from datetime import UTC, datetime

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.redis_client import redis_client
from app.core.security import decode_access_token
from app.db.models import Tenant, TenantStatus, User, UserStatus
from app.db.session import get_db
from app.identity.service import identity_service
from app.schemas.pipeline import ScopeContext

bearer_scheme = HTTPBearer(auto_error=False)


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
