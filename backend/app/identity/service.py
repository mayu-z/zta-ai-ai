from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from datetime import UTC, datetime
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode

import jwt
from jwt import InvalidTokenError, PyJWKClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError
from app.core.security import create_access_token
from app.core.secret_manager import secret_manager
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

    def _auth_provider(self) -> str:
        return self.settings.auth_provider.strip().lower()

    def _oidc_algorithms(self) -> list[str]:
        raw = self.settings.oidc_allowed_algorithms
        algorithms = [item.strip() for item in raw.split(",") if item.strip()]
        return algorithms or ["RS256"]

    def _oidc_shared_secret(self) -> str:
        return secret_manager.get_secret(
            "OIDC_SHARED_SECRET",
            fallback=self.settings.oidc_shared_secret,
        ).strip()

    def _decode_base32_secret(self, secret: str) -> bytes:
        normalized = secret.strip().replace(" ", "").upper()
        padding = "=" * (-len(normalized) % 8)
        return base64.b32decode(normalized + padding, casefold=True)

    def _totp_from_counter(self, secret: str, counter: int) -> str:
        secret_bytes = self._decode_base32_secret(secret)
        payload = counter.to_bytes(8, "big")
        digest = hmac.new(secret_bytes, payload, hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        code_int = (
            ((digest[offset] & 0x7F) << 24)
            | ((digest[offset + 1] & 0xFF) << 16)
            | ((digest[offset + 2] & 0xFF) << 8)
            | (digest[offset + 3] & 0xFF)
        )
        return f"{code_int % 1_000_000:06d}"

    def _totp_counter(self) -> int:
        return int(time.time() // self.settings.mfa_totp_period_seconds)

    def _build_totp_uri(self, email: str, secret: str) -> str:
        issuer = self.settings.mfa_totp_issuer.strip() or "ZTA-AI"
        label = quote(f"{issuer}:{email}")
        query = urlencode(
            {
                "secret": secret,
                "issuer": issuer,
                "algorithm": "SHA1",
                "digits": 6,
                "period": self.settings.mfa_totp_period_seconds,
            }
        )
        return f"otpauth://totp/{label}?{query}"

    def _effective_mfa_verified(
        self,
        user: User,
        requested_mfa_verified: bool | None,
    ) -> bool:
        # Users with TOTP configured must complete MFA verification for each session.
        if user.mfa_method == "totp":
            return bool(requested_mfa_verified)
        if requested_mfa_verified is None:
            return True
        return bool(requested_mfa_verified)

    def _get_active_user_by_id(self, db: Session, user_id: str) -> User:
        user = db.scalar(
            select(User).where(
                User.id == user_id,
                User.status == UserStatus.active,
            )
        )
        if not user:
            raise AuthenticationError(
                message="User account is invalid or inactive",
                code="USER_INVALID",
            )
        return user

    def enroll_totp(self, db: Session, user_id: str) -> dict[str, str]:
        user = self._get_active_user_by_id(db, user_id)
        secret = base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")

        user.mfa_method = "totp"
        user.mfa_totp_secret = secret
        user.mfa_enabled = False
        user.mfa_enrolled_at = None

        db.add(user)
        db.commit()

        return {
            "method": "totp",
            "secret": secret,
            "otpauth_uri": self._build_totp_uri(user.email, secret),
        }

    def verify_totp_code(self, db: Session, user_id: str, code: str) -> None:
        normalized_code = code.strip().replace(" ", "")
        if not normalized_code.isdigit() or len(normalized_code) != 6:
            raise AuthenticationError(
                message="Invalid MFA code",
                code="MFA_CODE_INVALID",
            )

        user = self._get_active_user_by_id(db, user_id)
        if user.mfa_method != "totp" or not user.mfa_totp_secret:
            raise AuthenticationError(
                message="TOTP is not enrolled for this user",
                code="MFA_NOT_ENROLLED",
            )

        counter = self._totp_counter()
        window = max(0, int(self.settings.mfa_totp_window_steps))
        valid = False
        for offset in range(-window, window + 1):
            expected = self._totp_from_counter(user.mfa_totp_secret, counter + offset)
            if hmac.compare_digest(expected, normalized_code):
                valid = True
                break

        if not valid:
            raise AuthenticationError(
                message="Invalid MFA code",
                code="MFA_CODE_INVALID",
            )

        user.mfa_enabled = True
        user.mfa_enrolled_at = user.mfa_enrolled_at or datetime.now(tz=UTC)

        db.add(user)
        db.commit()

    def verify_google_token(self, google_token: str) -> GoogleIdentity:
        provider = self._auth_provider()
        if provider != "mock_google":
            raise AuthenticationError(
                message=(
                    f"Google auth endpoint is disabled because AUTH_PROVIDER={provider}"
                ),
                code="AUTH_PROVIDER_DISABLED",
            )

        if not self.settings.use_mock_google_oauth:
            raise AuthenticationError(
                message="Mock Google OAuth is disabled by configuration",
                code="MOCK_AUTH_DISABLED",
            )

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

    def verify_oidc_token(self, id_token: str) -> GoogleIdentity:
        provider = self._auth_provider()
        if provider != "oidc":
            raise AuthenticationError(
                message=f"OIDC auth endpoint is disabled because AUTH_PROVIDER={provider}",
                code="AUTH_PROVIDER_DISABLED",
            )

        issuer = self.settings.oidc_issuer.strip()
        audience = self.settings.oidc_audience.strip()
        if not issuer or not audience:
            raise AuthenticationError(
                message="OIDC provider is not configured",
                code="OIDC_CONFIG_INVALID",
            )

        try:
            if self.settings.oidc_jwks_url:
                jwk_client = PyJWKClient(self.settings.oidc_jwks_url)
                signing_key = jwk_client.get_signing_key_from_jwt(id_token)
                claims = jwt.decode(
                    id_token,
                    key=signing_key.key,
                    algorithms=self._oidc_algorithms(),
                    audience=audience,
                    issuer=issuer,
                    options={"require": ["exp", "iat", "iss", "aud"]},
                )
            elif self._oidc_shared_secret():
                claims = jwt.decode(
                    id_token,
                    key=self._oidc_shared_secret(),
                    algorithms=self._oidc_algorithms(),
                    audience=audience,
                    issuer=issuer,
                    options={"require": ["exp", "iat", "iss", "aud"]},
                )
            else:
                raise AuthenticationError(
                    message="OIDC key source is missing",
                    code="OIDC_CONFIG_INVALID",
                )
        except InvalidTokenError as exc:
            raise AuthenticationError(
                message="OIDC token validation failed",
                code="OIDC_TOKEN_INVALID",
            ) from exc

        email = str(
            claims.get("email")
            or claims.get("upn")
            or claims.get("preferred_username")
            or ""
        ).strip().lower()
        if not email or "@" not in email:
            raise AuthenticationError(
                message="OIDC token is missing a valid email claim",
                code="OIDC_EMAIL_MISSING",
            )

        name = str(
            claims.get("name")
            or claims.get("given_name")
            or email.split("@")[0].replace(".", " ").title()
        )
        return GoogleIdentity(email=email, name=name)

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

    def _authenticate_identity(
        self,
        db: Session,
        identity: GoogleIdentity,
        session_ip: str | None,
        device_trusted: bool,
        mfa_verified: bool | None,
    ) -> tuple[str, User, ScopeContext]:
        tenant = self.resolve_tenant(db, identity.email)
        user = self.resolve_user(db, tenant.id, identity.email)
        effective_mfa_verified = self._effective_mfa_verified(user, mfa_verified)

        session_id = str(uuid.uuid4())
        scope = self.build_scope_context(
            user=user,
            tenant=tenant,
            session_id=session_id,
            session_ip=session_ip,
            device_trusted=device_trusted,
            mfa_verified=effective_mfa_verified,
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

    def authenticate_google(
        self,
        db: Session,
        google_token: str,
        session_ip: str | None = None,
        device_trusted: bool = True,
        mfa_verified: bool | None = None,
    ) -> tuple[str, User, ScopeContext]:
        identity = self.verify_google_token(google_token)
        return self._authenticate_identity(
            db=db,
            identity=identity,
            session_ip=session_ip,
            device_trusted=device_trusted,
            mfa_verified=mfa_verified,
        )

    def authenticate_oidc(
        self,
        db: Session,
        id_token: str,
        session_ip: str | None = None,
        device_trusted: bool = True,
        mfa_verified: bool | None = None,
    ) -> tuple[str, User, ScopeContext]:
        identity = self.verify_oidc_token(id_token)
        return self._authenticate_identity(
            db=db,
            identity=identity,
            session_ip=session_ip,
            device_trusted=device_trusted,
            mfa_verified=mfa_verified,
        )


identity_service = IdentityService()
