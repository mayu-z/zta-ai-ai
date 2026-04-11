from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.exceptions import AuthenticationError
from app.identity.service import IdentityService


def _build_hs256_id_token(
    *,
    secret: str,
    issuer: str,
    audience: str,
    email: str,
    name: str,
) -> str:
    now = datetime.now(tz=UTC)
    payload = {
        "iss": issuer,
        "aud": audience,
        "email": email,
        "name": name,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=10)).timestamp()),
    }
    return jwt.encode(payload, key=secret, algorithm="HS256")


def _configure_oidc(
    service: IdentityService,
    monkeypatch: pytest.MonkeyPatch,
    *,
    issuer: str = "https://idp.example.com",
    audience: str = "zta-backend",
    secret: str = "oidc-test-secret-that-is-at-least-thirty-two-chars",
) -> None:
    monkeypatch.setattr(service.settings, "auth_provider", "oidc")
    monkeypatch.setattr(service.settings, "oidc_issuer", issuer)
    monkeypatch.setattr(service.settings, "oidc_audience", audience)
    monkeypatch.setattr(service.settings, "oidc_jwks_url", "")
    monkeypatch.setattr(service.settings, "oidc_shared_secret", secret)
    monkeypatch.setattr(service.settings, "oidc_allowed_algorithms", "HS256")


def test_verify_oidc_token_success(monkeypatch: pytest.MonkeyPatch) -> None:
    service = IdentityService()
    _configure_oidc(service, monkeypatch)

    token = _build_hs256_id_token(
        secret="oidc-test-secret-that-is-at-least-thirty-two-chars",
        issuer="https://idp.example.com",
        audience="zta-backend",
        email="executive@ipeds.local",
        name="Executive",
    )

    identity = service.verify_oidc_token(token)

    assert identity.email == "executive@ipeds.local"
    assert identity.name == "Executive"


def test_verify_oidc_token_rejected_when_provider_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = IdentityService()
    monkeypatch.setattr(service.settings, "auth_provider", "mock_google")

    token = _build_hs256_id_token(
        secret="oidc-test-secret-that-is-at-least-thirty-two-chars",
        issuer="https://idp.example.com",
        audience="zta-backend",
        email="executive@ipeds.local",
        name="Executive",
    )

    with pytest.raises(AuthenticationError) as exc_info:
        service.verify_oidc_token(token)

    assert exc_info.value.code == "AUTH_PROVIDER_DISABLED"


def test_authenticate_oidc_returns_scoped_jwt(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = IdentityService()
    _configure_oidc(service, monkeypatch)

    id_token = _build_hs256_id_token(
        secret="oidc-test-secret-that-is-at-least-thirty-two-chars",
        issuer="https://idp.example.com",
        audience="zta-backend",
        email="executive@ipeds.local",
        name="Executive",
    )

    jwt_token, user, scope = service.authenticate_oidc(db=db_session, id_token=id_token)

    assert jwt_token
    assert user.email == "executive@ipeds.local"
    assert scope.tenant_id
    assert scope.user_id == user.id
