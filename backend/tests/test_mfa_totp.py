from __future__ import annotations

import base64
import hashlib
import hmac
import time

from app.identity.service import identity_service


def _totp_code(secret: str, counter: int) -> str:
    normalized = secret.strip().replace(" ", "").upper()
    padding = "=" * (-len(normalized) % 8)
    secret_bytes = base64.b32decode(normalized + padding, casefold=True)

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


def test_totp_enrollment_persists_user_secret(db_session) -> None:
    tenant = identity_service.resolve_tenant(db_session, "executive@ipeds.local")
    user = identity_service.resolve_user(
        db_session,
        tenant_id=tenant.id,
        email="executive@ipeds.local",
    )

    enrolled = identity_service.enroll_totp(db=db_session, user_id=user.id)

    db_session.refresh(user)
    assert enrolled["method"] == "totp"
    assert enrolled["secret"]
    assert enrolled["otpauth_uri"].startswith("otpauth://totp/")
    assert user.mfa_method == "totp"
    assert user.mfa_totp_secret == enrolled["secret"]
    assert user.mfa_enabled is False


def test_totp_verify_enables_mfa(db_session) -> None:
    tenant = identity_service.resolve_tenant(db_session, "executive@ipeds.local")
    user = identity_service.resolve_user(
        db_session,
        tenant_id=tenant.id,
        email="executive@ipeds.local",
    )
    enrolled = identity_service.enroll_totp(db=db_session, user_id=user.id)

    counter = int(time.time() // identity_service.settings.mfa_totp_period_seconds)
    code = _totp_code(enrolled["secret"], counter)

    identity_service.verify_totp_code(db=db_session, user_id=user.id, code=code)

    db_session.refresh(user)
    assert user.mfa_enabled is True
    assert user.mfa_enrolled_at is not None


def test_login_defaults_to_mfa_unverified_when_totp_is_configured(db_session) -> None:
    tenant = identity_service.resolve_tenant(db_session, "executive@ipeds.local")
    user = identity_service.resolve_user(
        db_session,
        tenant_id=tenant.id,
        email="executive@ipeds.local",
    )
    enrolled = identity_service.enroll_totp(db=db_session, user_id=user.id)

    counter = int(time.time() // identity_service.settings.mfa_totp_period_seconds)
    code = _totp_code(enrolled["secret"], counter)
    identity_service.verify_totp_code(db=db_session, user_id=user.id, code=code)

    _token, _resolved_user, scope = identity_service.authenticate_google(
        db=db_session,
        google_token="mock:executive@ipeds.local",
    )
    assert scope.mfa_verified is False

    _token2, _resolved_user2, scope2 = identity_service.authenticate_google(
        db=db_session,
        google_token="mock:executive@ipeds.local",
        mfa_verified=True,
    )
    assert scope2.mfa_verified is True
