from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_scope, get_db
from app.db.models import PersonaType, Tenant, User, UserStatus
from app.main import app
from app.schemas.pipeline import ScopeContext
from app.services.action_orchestrator import action_orchestrator_service


TENANT_ID = "52345678-1234-1234-1234-123456789012"
USER_ID = "47654321-4321-4321-4321-210987654321"


@pytest.fixture(autouse=True)
def reset_action_orchestrator() -> None:
    action_orchestrator_service.reset()
    yield
    action_orchestrator_service.reset()


@pytest.fixture
def tenant_and_user(db: Session):
    tenant = Tenant(
        id=TENANT_ID,
        name="Workflow Test University",
        domain="workflow-test.edu",
        subdomain="workflow-test",
    )
    user = User(
        id=USER_ID,
        tenant_id=TENANT_ID,
        email="ithead@workflow-test.edu",
        name="IT Head",
        persona_type=PersonaType.it_head,
        external_id="it-001",
        status=UserStatus.active,
    )
    db.add_all([tenant, user])
    db.commit()
    return tenant, user


@pytest.fixture
def client(db: Session, tenant_and_user):
    test_scope = ScopeContext(
        tenant_id=TENANT_ID,
        user_id=USER_ID,
        persona_type="it_head",
        email="ithead@workflow-test.edu",
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


def test_workflow_builder_updates_effective_template_and_execution_flow(
    client: TestClient,
) -> None:
    upsert_response = client.put(
        "/admin/actions/templates/CONSENT_WITHDRAWAL",
        json={
            "trigger": "consent_manual_review_required",
            "approval_required": True,
            "approver_role": "it_head",
            "sla_hours": 2,
            "execution_steps": ["record_withdrawal", "compliance_review", "confirm"],
        },
    )
    assert upsert_response.status_code == 200

    updated = upsert_response.json()
    assert updated["enabled"] is True
    assert updated["effective_template"]["trigger"] == "consent_manual_review_required"
    assert updated["effective_template"]["approval_requirements"]["required"] is True
    assert updated["effective_template"]["approval_requirements"]["approver_role"] == "it_head"
    assert updated["effective_template"]["approval_requirements"]["sla_hours"] == 2
    assert updated["effective_template"]["execution_steps"] == [
        "record_withdrawal",
        "compliance_review",
        "confirm",
    ]

    execute_response = client.post(
        "/admin/actions/execute",
        json={
            "action_id": "CONSENT_WITHDRAWAL",
            "input_payload": {
                "subject_identifier": "subject-workflow-1",
                "consent_type": "analytics",
            },
        },
    )
    assert execute_response.status_code == 200

    execution = execute_response.json()
    assert execution["status"] == "awaiting_approval"
    assert execution["approval_required"] is True
    assert execution["approver_role"] == "it_head"

    approve_response = client.post(
        f"/admin/actions/executions/{execution['execution_id']}/approve",
        json={"comment": "Approved custom consent workflow"},
    )
    assert approve_response.status_code == 200

    approved = approve_response.json()
    assert approved["status"] == "completed"
    assert [step["step_name"] for step in approved["steps"]] == [
        "record_withdrawal",
        "compliance_review",
        "confirm",
    ]


def test_workflow_builder_can_disable_action_template(client: TestClient) -> None:
    disable_response = client.put(
        "/admin/actions/templates/CONNECTOR_REFRESH",
        json={"is_enabled": False},
    )
    assert disable_response.status_code == 200
    assert disable_response.json()["enabled"] is False

    execute_response = client.post(
        "/admin/actions/execute",
        json={
            "action_id": "CONNECTOR_REFRESH",
            "input_payload": {
                "connector_id": "connector-1",
                "force": False,
            },
        },
    )
    assert execute_response.status_code == 422
    assert execute_response.json()["code"] == "ACTION_TEMPLATE_DISABLED"


def test_workflow_builder_delete_override_restores_default_execution(
    client: TestClient,
) -> None:
    upsert_response = client.put(
        "/admin/actions/templates/CONSENT_WITHDRAWAL",
        json={
            "approval_required": True,
            "approver_role": "it_head",
        },
    )
    assert upsert_response.status_code == 200

    first_execute = client.post(
        "/admin/actions/execute",
        json={
            "action_id": "CONSENT_WITHDRAWAL",
            "input_payload": {
                "subject_identifier": "subject-workflow-2",
                "consent_type": "marketing",
            },
        },
    )
    assert first_execute.status_code == 200
    assert first_execute.json()["status"] == "awaiting_approval"

    delete_response = client.delete("/admin/actions/templates/CONSENT_WITHDRAWAL")
    assert delete_response.status_code == 200
    assert delete_response.json()["override"] is None

    second_execute = client.post(
        "/admin/actions/execute",
        json={
            "action_id": "CONSENT_WITHDRAWAL",
            "input_payload": {
                "subject_identifier": "subject-workflow-3",
                "consent_type": "marketing",
            },
        },
    )
    assert second_execute.status_code == 200
    assert second_execute.json()["status"] == "completed"
    assert second_execute.json()["approval_required"] is False


def test_workflow_builder_templates_list_includes_override_metadata(
    client: TestClient,
) -> None:
    upsert_response = client.put(
        "/admin/actions/templates/CONNECTOR_REFRESH",
        json={
            "trigger": "manual_refresh_trigger",
            "sla_hours": 4,
        },
    )
    assert upsert_response.status_code == 200

    response = client.get("/admin/actions/templates")
    assert response.status_code == 200

    payload = response.json()
    assert len(payload["templates"]) == 12

    connector_refresh = next(
        item for item in payload["templates"] if item["action_id"] == "CONNECTOR_REFRESH"
    )
    assert connector_refresh["trigger"] == "manual_refresh_trigger"
    assert connector_refresh["override"] is not None
    assert connector_refresh["override"]["sla_hours"] == 4
