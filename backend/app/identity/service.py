from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError
from app.core.security import create_access_token
from app.db.models import (
    PersonaType,
    RolePolicy,
    Tenant,
    TenantStatus,
    User,
    UserStatus,
)
from app.schemas.pipeline import ScopeContext


@dataclass
class GoogleIdentity:
    email: str
    name: str


ALL_DOMAINS = [
    "academic",
    "finance",
    "hr",
    "admissions",
    "exam",
    "department",
    "campus",
    "admin",
    "notices",
]


class IdentityService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def verify_google_token(self, google_token: str) -> GoogleIdentity:
        if self.settings.use_mock_google_oauth:
            prefix = self.settings.mock_google_token_prefix
            if google_token.startswith(prefix):
                email = google_token[len(prefix) :].strip().lower()
                return GoogleIdentity(
                    email=email, name=email.split("@")[0].replace(".", " ").title()
                )

            try:
                decoded = base64.b64decode(google_token).decode("utf-8")
                data = json.loads(decoded)
                email = str(data["email"]).lower()
                name = str(data.get("name", email.split("@")[0]))
                return GoogleIdentity(email=email, name=name)
            except Exception as exc:  # noqa: BLE001
                raise AuthenticationError(
                    message="Mock Google token format is invalid",
                    code="GOOGLE_TOKEN_INVALID",
                ) from exc

        raise AuthenticationError(
            message="Real Google OAuth validation is not enabled in this build",
            code="GOOGLE_OAUTH_UNAVAILABLE",
        )

    def resolve_tenant(self, db: Session, email: str) -> Tenant:
        if "@" not in email:
            raise AuthenticationError(
                message="Invalid identity email", code="IDENTITY_EMAIL_INVALID"
            )

        domain = email.split("@", 1)[1].lower()
        tenant = db.scalar(
            select(Tenant).where(
                Tenant.domain == domain, Tenant.status == TenantStatus.active
            )
        )
        if not tenant:
            raise AuthenticationError(
                message="Email domain is not onboarded", code="UNKNOWN_TENANT"
            )
        return tenant

    def resolve_user(self, db: Session, tenant_id: str, email: str) -> User:
        user = db.scalar(
            select(User).where(
                User.tenant_id == tenant_id,
                User.email == email,
                User.status == UserStatus.active,
            )
        )
        if not user:
            raise AuthenticationError(
                message="User is not provisioned for this tenant", code="USER_NOT_FOUND"
            )
        return user

    def _persona_row_scope_mode(self, persona: PersonaType) -> str | None:
        if persona == PersonaType.student:
            return "owner_id"
        if persona == PersonaType.faculty:
            return "course_ids"
        if persona == PersonaType.dept_head:
            return "department_id"
        if persona == PersonaType.admin_staff:
            return "admin_function"
        return None

    def _role_key_candidates(
        self, persona: PersonaType, admin_function: str | None
    ) -> list[str]:
        candidates: list[str] = []
        persona_key = persona.value
        admin_key = (admin_function or "").strip().lower()

        if persona == PersonaType.admin_staff and admin_key:
            candidates.append(f"admin_staff:{admin_key}")
            if admin_key == "finance":
                candidates.append("finance_dept")
            elif admin_key == "exam":
                candidates.append("examination_head")

        candidates.append(persona_key)

        if persona == PersonaType.dept_head:
            candidates.append("hod")
        if persona == PersonaType.it_head:
            candidates.append("it_admin")

        unique_candidates: list[str] = []
        for item in candidates:
            if item and item not in unique_candidates:
                unique_candidates.append(item)
        return unique_candidates

    def _serialize_role_policy(self, policy: RolePolicy) -> dict[str, Any]:
        start = policy.business_hours_start
        end = policy.business_hours_end
        if start < 0 or start > 23:
            start = 9
        if end < 0 or end > 23:
            end = 19
        if end < start:
            end = start

        return {
            "allowed_domains": list(policy.allowed_domains or []),
            "masked_fields": list(policy.masked_fields or []),
            "aggregate_only": bool(policy.aggregate_only),
            "chat_enabled": bool(policy.chat_enabled),
            "row_scope_mode": policy.row_scope_mode,
            "sensitive_domains": list(policy.sensitive_domains or ["finance", "hr"]),
            "require_business_hours_for_sensitive": bool(
                policy.require_business_hours_for_sensitive
            ),
            "business_hours_start": start,
            "business_hours_end": end,
            "require_trusted_device_for_sensitive": bool(
                policy.require_trusted_device_for_sensitive
            ),
            "require_mfa_for_sensitive": bool(policy.require_mfa_for_sensitive),
        }

    def _resolve_role_policy(
        self,
        db: Session,
        tenant_id: str,
        persona: PersonaType,
        admin_function: str | None,
    ) -> tuple[str, dict[str, Any]]:
        candidates = self._role_key_candidates(persona, admin_function)

        if not candidates:
            raise AuthenticationError(
                message="Role policy is not configured for this user role",
                code="ROLE_POLICY_NOT_CONFIGURED",
            )

        rows = db.scalars(
            select(RolePolicy).where(
                RolePolicy.tenant_id == tenant_id,
                RolePolicy.role_key.in_(candidates),
                RolePolicy.is_active.is_(True),
            )
        ).all()
        by_role = {row.role_key: row for row in rows}
        for role_key in candidates:
            policy = by_role.get(role_key)
            if policy is not None:
                return role_key, self._serialize_role_policy(policy)

        raise AuthenticationError(
            message="Role policy is not configured for this user role",
            code="ROLE_POLICY_NOT_CONFIGURED",
        )

    def _row_scope_filters(self, user: User, row_scope_mode: str | None) -> dict[str, Any]:
        if row_scope_mode == "owner_id":
            return {"owner_id": user.external_id}
        if row_scope_mode == "course_ids":
            return {"course_ids": list(user.course_ids or [])}
        if row_scope_mode == "department_id":
            return {"department_id": user.department}
        if row_scope_mode == "admin_function":
            return {"admin_function": user.admin_function}
        return {}

    def build_scope_context(
        self,
        user: User,
        tenant: Tenant,
        session_id: str,
        session_ip: str | None,
        device_trusted: bool,
        mfa_verified: bool,
        db: Session,
    ) -> ScopeContext:
        role_key, role_policy = self._resolve_role_policy(
            db=db,
            tenant_id=tenant.id,
            persona=user.persona_type,
            admin_function=user.admin_function,
        )
        allowed_domains = role_policy["allowed_domains"]
        denied_domains = [
            domain
            for domain in ALL_DOMAINS
            if all(domain not in allowed for allowed in allowed_domains)
        ]
        row_scope_mode = role_policy.get("row_scope_mode") or self._persona_row_scope_mode(
            user.persona_type
        )
        masked_fields = sorted(
            set(
                list(user.masked_fields or []) + list(role_policy["masked_fields"])
            )
        )

        return ScopeContext(
            tenant_id=tenant.id,
            user_id=user.id,
            email=user.email,
            name=user.name,
            persona_type=user.persona_type.value,
            department=user.department,
            external_id=user.external_id,
            admin_function=user.admin_function,
            role_key=role_key,
            course_ids=user.course_ids or [],
            row_scope_mode=row_scope_mode,
            row_scope_filters=self._row_scope_filters(user, row_scope_mode),
            allowed_domains=allowed_domains,
            denied_domains=denied_domains,
            masked_fields=masked_fields,
            aggregate_only=bool(role_policy["aggregate_only"]),
            own_id=user.external_id,
            chat_enabled=bool(role_policy["chat_enabled"]),
            sensitive_domains=list(role_policy["sensitive_domains"]),
            require_business_hours_for_sensitive=bool(
                role_policy["require_business_hours_for_sensitive"]
            ),
            business_hours_start=int(role_policy["business_hours_start"]),
            business_hours_end=int(role_policy["business_hours_end"]),
            require_trusted_device_for_sensitive=bool(
                role_policy["require_trusted_device_for_sensitive"]
            ),
            require_mfa_for_sensitive=bool(role_policy["require_mfa_for_sensitive"]),
            session_id=session_id,
            session_ip=session_ip,
            device_trusted=device_trusted,
            mfa_verified=mfa_verified,
        )

    def authenticate_google(
        self,
        db: Session,
        google_token: str,
        session_ip: str | None = None,
        device_trusted: bool = True,
        mfa_verified: bool = True,
    ) -> tuple[str, User, ScopeContext]:
        identity = self.verify_google_token(google_token)
        tenant = self.resolve_tenant(db, identity.email)
        user = self.resolve_user(db, tenant.id, identity.email)

        session_id = str(uuid.uuid4())
        scope = self.build_scope_context(
            user=user,
            tenant=tenant,
            session_id=session_id,
            session_ip=session_ip,
            device_trusted=device_trusted,
            mfa_verified=mfa_verified,
            db=db,
        )

        payload = {
            "sub": user.id,
            "tenant_id": tenant.id,
            "email": user.email,
            "name": user.name,
            "persona_type": user.persona_type.value,
            "department": user.department,
            "external_id": user.external_id,
            "admin_function": user.admin_function,
            "role_key": scope.role_key,
            "course_ids": user.course_ids or [],
            "row_scope_mode": scope.row_scope_mode,
            "row_scope_filters": scope.row_scope_filters,
            "allowed_domains": scope.allowed_domains,
            "denied_domains": scope.denied_domains,
            "masked_fields": scope.masked_fields,
            "aggregate_only": scope.aggregate_only,
            "chat_enabled": scope.chat_enabled,
            "sensitive_domains": scope.sensitive_domains,
            "require_business_hours_for_sensitive": scope.require_business_hours_for_sensitive,
            "business_hours_start": scope.business_hours_start,
            "business_hours_end": scope.business_hours_end,
            "require_trusted_device_for_sensitive": scope.require_trusted_device_for_sensitive,
            "require_mfa_for_sensitive": scope.require_mfa_for_sensitive,
            "session_id": session_id,
            "session_ip": scope.session_ip,
            "device_trusted": scope.device_trusted,
            "mfa_verified": scope.mfa_verified,
            "jti": str(uuid.uuid4()),
        }
        token = create_access_token(payload)
        return token, user, scope


identity_service = IdentityService()
