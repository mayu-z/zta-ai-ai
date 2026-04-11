from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import DomainKeyword, IntentDefinition, RolePolicy, Tenant, User
from app.db.session import SessionLocal
from app.main import app


def test_mock_google_login_autoprovisions_unknown_domain_identity() -> None:
    email = "ithead@local.test"

    with TestClient(app) as client:
        response = client.post(
            "/auth/google",
            json={"google_token": f"mock:{email}"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["email"] == email
    assert payload["user"]["persona"] == "it_head"
    assert isinstance(payload["jwt"], str) and payload["jwt"]

    db = SessionLocal()
    try:
        tenant = db.scalar(select(Tenant).where(Tenant.domain == "local.test"))
        assert tenant is not None

        user = db.scalar(
            select(User).where(
                User.tenant_id == tenant.id,
                User.email == email,
            )
        )
        assert user is not None
        assert user.persona_type.value == "it_head"

        assert db.scalar(select(RolePolicy.id).where(RolePolicy.tenant_id == tenant.id)) is not None
        assert db.scalar(select(DomainKeyword.id).where(DomainKeyword.tenant_id == tenant.id)) is not None
        assert db.scalar(select(IntentDefinition.id).where(IntentDefinition.tenant_id == tenant.id)) is not None
    finally:
        db.close()
