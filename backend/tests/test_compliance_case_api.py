from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_scope, get_db
from app.db.models import PersonaType, Tenant, User, UserStatus
from app.main import app
from app.schemas.pipeline import ScopeContext
from app.services.action_orchestrator import action_orchestrator_service
from app.services.compliance_case_service import compliance_case_service


TENANT_ID = "12345678-1234-1234-1234-123456789012"
USER_ID = "87654321-4321-4321-4321-210987654321"


@pytest.fixture(autouse=True)
def reset_services() -> None:
    action_orchestrator_service.reset()
    compliance_case_service.reset()
    yield
    action_orchestrator_service.reset()
    compliance_case_service.reset()


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


def test_create_and_approve_dsar_case(client: TestClient) -> None:
    create_response = client.post(
        "/admin/compliance/cases",
        json={
            "case_type": "dsar",
            "subject_identifier": "subject-abc",
            "delivery_method": "encrypted_email",
        },
    )
    assert create_response.status_code == 200

    created = create_response.json()
    assert created["case_type"] == "dsar"
    assert created["status"] == "pending_approval"
    assert created["delivery_method"] == "encrypted_email"
    assert created["action_execution_id"]

    approve_response = client.post(
        f"/admin/compliance/cases/{created['case_id']}/approve",
        json={"comment": "Approved by compliance"},
    )
    assert approve_response.status_code == 200

    approved = approve_response.json()
    assert approved["status"] == "completed"
    assert approved["last_action_status"] == "completed"
    assert approved["output"]["request_id"].startswith("DSAR_")


def test_erasure_case_approval_blocked_by_legal_hold(client: TestClient) -> None:
    create_response = client.post(
        "/admin/compliance/cases",
        json={
            "case_type": "erasure",
            "subject_identifier": "subject-erasure",
            "legal_basis": "gdpr_article_17",
        },
    )
    assert create_response.status_code == 200

    created = create_response.json()

    hold_response = client.post(
        f"/admin/compliance/cases/{created['case_id']}/legal-hold",
        json={"active": True, "reason": "Pending litigation"},
    )
    assert hold_response.status_code == 200
    assert hold_response.json()["legal_hold_active"] is True

    blocked_approve = client.post(
        f"/admin/actions/executions/{created['action_execution_id']}/approve",
        json={"comment": "Should be blocked"},
    )
    assert blocked_approve.status_code == 422
    assert blocked_approve.json()["code"] == "LEGAL_HOLD_ACTIVE"

    release_response = client.post(
        f"/admin/compliance/cases/{created['case_id']}/legal-hold",
        json={"active": False, "reason": "Litigation closed"},
    )
    assert release_response.status_code == 200
    assert release_response.json()["legal_hold_active"] is False

    approve_response = client.post(
        f"/admin/actions/executions/{created['action_execution_id']}/approve",
        json={"comment": "Now allowed"},
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "completed"


def test_case_state_persists_across_service_reset(client: TestClient) -> None:
    create_response = client.post(
        "/admin/compliance/cases",
        json={
            "case_type": "erasure",
            "subject_identifier": "subject-persist",
            "legal_basis": "gdpr_article_17",
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()

    hold_response = client.post(
        f"/admin/compliance/cases/{created['case_id']}/legal-hold",
        json={"active": True, "reason": "Regulatory inquiry"},
    )
    assert hold_response.status_code == 200
    assert hold_response.json()["legal_hold_active"] is True

    compliance_case_service.reset()

    get_response = client.get(f"/admin/compliance/cases/{created['case_id']}")
    assert get_response.status_code == 200
    persisted = get_response.json()
    assert persisted["legal_hold_active"] is True
    assert persisted["legal_hold_reason"] == "Regulatory inquiry"

    blocked_approve = client.post(
        f"/admin/actions/executions/{created['action_execution_id']}/approve",
        json={"comment": "Should still be blocked"},
    )
    assert blocked_approve.status_code == 422
    assert blocked_approve.json()["code"] == "LEGAL_HOLD_ACTIVE"


def test_list_cases_filters_by_type_and_status(client: TestClient) -> None:
    dsar_create = client.post(
        "/admin/compliance/cases",
        json={
            "case_type": "dsar",
            "subject_identifier": "subject-list-1",
        },
    )
    assert dsar_create.status_code == 200

    erasure_create = client.post(
        "/admin/compliance/cases",
        json={
            "case_type": "erasure",
            "subject_identifier": "subject-list-2",
            "legal_basis": "gdpr_article_17",
        },
    )
    assert erasure_create.status_code == 200

    approve_dsar = client.post(
        f"/admin/compliance/cases/{dsar_create.json()['case_id']}/approve",
        json={"comment": "Complete case"},
    )
    assert approve_dsar.status_code == 200

    dsar_only = client.get("/admin/compliance/cases?case_type=dsar")
    assert dsar_only.status_code == 200
    dsar_items = dsar_only.json()
    assert dsar_items
    assert all(item["case_type"] == "dsar" for item in dsar_items)

    completed = client.get("/admin/compliance/cases?status=completed")
    assert completed.status_code == 200
    completed_items = completed.json()
    assert any(item["status"] == "completed" for item in completed_items)


def test_create_case_rejects_invalid_case_type(client: TestClient) -> None:
    response = client.post(
        "/admin/compliance/cases",
        json={
            "case_type": "breach",
            "subject_identifier": "subject-x",
        },
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "COMPLIANCE_CASE_TYPE_INVALID"
