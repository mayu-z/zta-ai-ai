from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_scope, get_db
from app.core.config import get_settings
from app.db.models import ComplianceAttestation, PersonaType, Tenant, User, UserStatus
from app.main import app
from app.schemas.pipeline import ScopeContext
from app.services.action_orchestrator import action_orchestrator_service


TENANT_ID = "12345678-1234-1234-1234-123456789012"
USER_ID = "87654321-4321-4321-4321-210987654321"


@pytest.fixture(autouse=True)
def reset_action_orchestrator() -> None:
    action_orchestrator_service.reset()
    yield
    action_orchestrator_service.reset()


@pytest.fixture
def tenant_and_user(db: Session):
    tenant = Tenant(
        id=TENANT_ID,
        name="Test University",
        domain="test.edu",
        subdomain="test",
    )
    user = User(
        id=USER_ID,
        tenant_id=TENANT_ID,
        email="ithead@test.edu",
        name="IT Head",
        persona_type=PersonaType.it_head,
        external_id="it-001",
        status=UserStatus.active,
    )
    db.add(tenant)
    db.add(user)
    db.commit()
    return tenant, user


@pytest.fixture
def client(db: Session, tenant_and_user):
    test_scope = ScopeContext(
        tenant_id=TENANT_ID,
        user_id=USER_ID,
        persona_type="it_head",
        email="ithead@test.edu",
        external_id="it-001",
        allowed_domains=["academic", "finance", "admin"],
        aggregate_only=False,
        masked_fields=[],
    )

    def override_get_db():
        yield db

    def override_get_scope():
        return test_scope

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_scope] = override_get_scope

    test_client = TestClient(app)
    yield test_client

    app.dependency_overrides.clear()


def _create_completed_dsar_execution(client: TestClient) -> None:
    execute_response = client.post(
        "/admin/actions/execute",
        json={
            "action_id": "DSAR_EXECUTE",
            "input_payload": {
                "subject_identifier": "subject-attest",
                "delivery_method": "secure_portal",
            },
        },
    )
    assert execute_response.status_code == 200

    execution_id = execute_response.json()["execution_id"]
    approve_response = client.post(
        f"/admin/actions/executions/{execution_id}/approve",
        json={"comment": "Approved for attestation"},
    )
    assert approve_response.status_code == 200


def test_create_attestation_generates_signature_and_persists(
    client: TestClient,
    db: Session,
) -> None:
    _create_completed_dsar_execution(client)

    now = datetime.now(tz=UTC)
    response = client.post(
        "/admin/compliance/attestations",
        json={
            "framework": "gdpr",
            "from_at": (now - timedelta(days=7)).isoformat().replace("+00:00", "Z"),
            "to_at": now.isoformat().replace("+00:00", "Z"),
            "max_items": 100,
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["framework"] == "GDPR"
    assert payload["signature_algorithm"] == "HMAC-SHA256"
    assert len(payload["signature"]) == 64
    assert len(payload["payload_digest"]) == 64

    signed_payload = payload["signed_payload"]
    canonical = json.dumps(
        signed_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    expected_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    expected_signature = hmac.new(
        get_settings().jwt_secret_key.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    assert payload["payload_digest"] == expected_digest
    assert payload["signature"] == expected_signature

    row = db.get(ComplianceAttestation, payload["attestation_id"])
    assert row is not None
    assert row.framework == "GDPR"
    assert row.tenant_id == TENANT_ID


def test_attestation_window_is_normalized_when_from_after_to(
    client: TestClient,
) -> None:
    now = datetime.now(tz=UTC)
    response = client.post(
        "/admin/compliance/attestations",
        json={
            "framework": "HIPAA",
            "from_at": now.isoformat().replace("+00:00", "Z"),
            "to_at": (now - timedelta(days=3)).isoformat().replace("+00:00", "Z"),
            "max_items": 100,
        },
    )
    assert response.status_code == 200

    payload = response.json()
    period_from = datetime.fromisoformat(payload["period"]["from"])
    period_to = datetime.fromisoformat(payload["period"]["to"])
    assert period_from <= period_to


def test_list_attestations_filters_by_framework(
    client: TestClient,
) -> None:
    now = datetime.now(tz=UTC)

    gdpr_response = client.post(
        "/admin/compliance/attestations",
        json={
            "framework": "GDPR",
            "from_at": (now - timedelta(days=2)).isoformat().replace("+00:00", "Z"),
            "to_at": now.isoformat().replace("+00:00", "Z"),
            "max_items": 100,
        },
    )
    assert gdpr_response.status_code == 200

    hipaa_response = client.post(
        "/admin/compliance/attestations",
        json={
            "framework": "HIPAA",
            "from_at": (now - timedelta(days=2)).isoformat().replace("+00:00", "Z"),
            "to_at": now.isoformat().replace("+00:00", "Z"),
            "max_items": 100,
        },
    )
    assert hipaa_response.status_code == 200

    list_response = client.get("/admin/compliance/attestations?framework=gdpr&limit=10")
    assert list_response.status_code == 200

    payload = list_response.json()
    assert payload["count"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["framework"] == "GDPR"
    assert "signed_payload" not in payload["items"][0]


def test_create_attestation_rejects_unsupported_framework(
    client: TestClient,
) -> None:
    response = client.post(
        "/admin/compliance/attestations",
        json={
            "framework": "NIST80053",
            "max_items": 100,
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "COMPLIANCE_FRAMEWORK_NOT_SUPPORTED"
