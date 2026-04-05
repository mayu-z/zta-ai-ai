from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError
from app.core.security import create_access_token
from app.db.models import PersonaType, Tenant, TenantStatus, User, UserStatus
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

    def _persona_allowed_domains(
        self, persona: PersonaType, admin_function: str | None
    ) -> list[str]:
        if persona == PersonaType.student:
            return ["academic", "finance_self", "notices"]
        if persona == PersonaType.faculty:
            return ["academic", "hr_self", "notices"]
        if persona == PersonaType.dept_head:
            return ["academic", "department", "notices"]
        if persona == PersonaType.admin_staff:
            mapping = {
                "finance": ["finance"],
                "hr": ["hr"],
                "admissions": ["admissions"],
                "exam": ["exam", "academic"],
            }
            return mapping.get((admin_function or "").lower(), ["department"])
        if persona == PersonaType.executive:
            return [
                "campus_aggregate",
                "academic_aggregate",
                "finance_aggregate",
                "hr_aggregate",
            ]
        if persona == PersonaType.it_head:
            return ["admin"]
        return []

    def _persona_masked_fields(self, persona: PersonaType) -> list[str]:
        defaults = {
            PersonaType.student: ["salary", "bank_account", "ssn", "tax_id"],
            PersonaType.faculty: ["bank_account", "ssn", "tax_id"],
            PersonaType.dept_head: ["salary", "bank_account", "ssn", "tax_id"],
            PersonaType.admin_staff: ["bank_account", "ssn", "tax_id"],
            PersonaType.executive: ["student_pii", "salary_row", "ssn", "bank_account"],
            PersonaType.it_head: [],
        }
        return defaults.get(persona, []).copy()

    def build_scope_context(
        self,
        user: User,
        tenant: Tenant,
        session_id: str,
        session_ip: str | None,
        device_trusted: bool,
        mfa_verified: bool,
    ) -> ScopeContext:
        allowed_domains = self._persona_allowed_domains(
            user.persona_type, user.admin_function
        )
        denied_domains = [
            domain
            for domain in ALL_DOMAINS
            if all(domain not in allowed for allowed in allowed_domains)
        ]
        masked_fields = sorted(
            set(
                (user.masked_fields or [])
                + self._persona_masked_fields(user.persona_type)
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
            course_ids=user.course_ids or [],
            allowed_domains=allowed_domains,
            denied_domains=denied_domains,
            masked_fields=masked_fields,
            aggregate_only=user.persona_type == PersonaType.executive,
            own_id=user.external_id,
            chat_enabled=user.persona_type != PersonaType.it_head,
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
            "course_ids": user.course_ids or [],
            "allowed_domains": scope.allowed_domains,
            "denied_domains": scope.denied_domains,
            "masked_fields": scope.masked_fields,
            "aggregate_only": scope.aggregate_only,
            "chat_enabled": scope.chat_enabled,
            "session_id": session_id,
            "session_ip": scope.session_ip,
            "device_trusted": scope.device_trusted,
            "mfa_verified": scope.mfa_verified,
            "jti": str(uuid.uuid4()),
        }
        token = create_access_token(payload)
        return token, user, scope


identity_service = IdentityService()
