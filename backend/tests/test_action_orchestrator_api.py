from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_scope, get_db
from app.db.models import PersonaType, Tenant, User, UserStatus
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


def test_action_templates_endpoint_returns_registry_health(client: TestClient) -> None:
    response = client.get("/admin/actions/templates")
    assert response.status_code == 200

    payload = response.json()
    assert len(payload["templates"]) == 12
    assert payload["health"]["healthy"] is True
    assert payload["health"]["template_count"] == 12


def test_action_execution_requires_approval_then_completes(client: TestClient) -> None:
    execute_response = client.post(
        "/admin/actions/execute",
        json={
            "action_id": "DSAR_EXECUTE",
            "input_payload": {
                "subject_identifier": "subject-123",
                "delivery_method": "secure_portal",
            },
        },
    )
    assert execute_response.status_code == 200

    execution = execute_response.json()
    assert execution["status"] == "awaiting_approval"
    assert execution["approval_required"] is True
    assert execution["steps"] == []

    approve_response = client.post(
        f"/admin/actions/executions/{execution['execution_id']}/approve",
        json={"comment": "Approved for compliance processing"},
    )
    assert approve_response.status_code == 200

    completed = approve_response.json()
    assert completed["status"] == "completed"
    assert completed["approved_by"] == USER_ID
    assert len(completed["steps"]) > 0
    assert completed["output"]["status"] == "completed"
    assert completed["output"]["request_id"].startswith("DSAR_")
    assert completed["output"]["proof_id"].startswith("proof_")
    assert completed["output"]["delivery_method"] == "secure_portal"
    assert completed["output"]["completion_summary"]["records_delivered"] >= 0
    assert completed["output"]["forensic_evidence"]["regulatory_ready"] is True


def test_dry_run_skips_approval_and_simulates_steps(client: TestClient) -> None:
    response = client.post(
        "/admin/actions/execute",
        json={
            "action_id": "ERASURE_EXECUTE",
            "dry_run": True,
            "input_payload": {"subject_identifier": "subject-456"},
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["approval_required"] is False
    assert len(payload["steps"]) > 0
    assert all(step["status"] == "simulated" for step in payload["steps"])
    assert payload["output"]["status"] == "dry_run_preview"


def test_action_execution_persists_across_service_reset(client: TestClient) -> None:
    execute_response = client.post(
        "/admin/actions/execute",
        json={
            "action_id": "DSAR_EXECUTE",
            "input_payload": {
                "subject_identifier": "subject-persist-action",
                "delivery_method": "secure_portal",
            },
        },
    )
    assert execute_response.status_code == 200
    execution_id = execute_response.json()["execution_id"]

    action_orchestrator_service.reset()

    get_response = client.get(f"/admin/actions/executions/{execution_id}")
    assert get_response.status_code == 200
    assert get_response.json()["execution_id"] == execution_id
    assert get_response.json()["status"] == "awaiting_approval"

    approve_response = client.post(
        f"/admin/actions/executions/{execution_id}/approve",
        json={"comment": "Approve after reset"},
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "completed"


def test_reversible_action_can_be_rolled_back(client: TestClient) -> None:
    execute_response = client.post(
        "/admin/actions/execute",
        json={
            "action_id": "POLICY_UPDATE",
            "input_payload": {"policy_id": "pol-123", "changes": {"k": "v"}},
        },
    )
    assert execute_response.status_code == 200
    execution_id = execute_response.json()["execution_id"]

    approve_response = client.post(
        f"/admin/actions/executions/{execution_id}/approve",
        json={"comment": "Approved policy rollout"},
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "completed"

    rollback_response = client.post(
        f"/admin/actions/executions/{execution_id}/rollback",
        json={"reason": "Validation mismatch in downstream service"},
    )
    assert rollback_response.status_code == 200

    rolled_back = rollback_response.json()
    assert rolled_back["status"] == "rolled_back"
    assert rolled_back["output"]["rollback"]["reason"] == "Validation mismatch in downstream service"


def test_bulk_soft_delete_generates_job_summary(client: TestClient) -> None:
    execute_response = client.post(
        "/admin/actions/execute",
        json={
            "action_id": "BULK_SOFT_DELETE",
            "input_payload": {
                "entity": "claims",
                "record_ids": ["claim-1", "claim-2", "claim-3"],
            },
        },
    )
    assert execute_response.status_code == 200

    execution = execute_response.json()
    assert execution["status"] == "awaiting_approval"

    approve_response = client.post(
        f"/admin/actions/executions/{execution['execution_id']}/approve",
        json={"comment": "Approved soft delete"},
    )
    assert approve_response.status_code == 200

    payload = approve_response.json()["output"]
    assert payload["job_id"].startswith("softdel_")
    assert payload["deleted_count"] == 3
    assert payload["entity"] == "claims"


def test_consent_withdrawal_runs_without_approval(client: TestClient) -> None:
    response = client.post(
        "/admin/actions/execute",
        json={
            "action_id": "CONSENT_WITHDRAWAL",
            "input_payload": {
                "subject_identifier": "subject-2026",
                "consent_type": "analytics",
            },
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["approval_required"] is False
    assert payload["output"]["status"] == "completed"
    assert payload["output"]["effective_at"]
    assert payload["output"]["downstream_processing"]["blocked"] is True


def test_incident_response_rejects_invalid_severity(client: TestClient) -> None:
    response = client.post(
        "/admin/actions/execute",
        json={
            "action_id": "INCIDENT_RESPONSE",
            "input_payload": {
                "incident_id": "inc-778",
                "severity": "urgent",
            },
        },
    )
    assert response.status_code == 422

    payload = response.json()
    assert payload["code"] == "ACTION_INPUT_VALIDATION_FAILED"
    assert "severity" in payload["error"]


def test_non_reversible_action_rejects_rollback(client: TestClient) -> None:
    execute_response = client.post(
        "/admin/actions/execute",
        json={
            "action_id": "DSAR_EXECUTE",
            "input_payload": {"subject_identifier": "subject-789"},
        },
    )
    assert execute_response.status_code == 200
    execution_id = execute_response.json()["execution_id"]

    approve_response = client.post(
        f"/admin/actions/executions/{execution_id}/approve",
        json={"comment": "Approved"},
    )
    assert approve_response.status_code == 200

    rollback_response = client.post(
        f"/admin/actions/executions/{execution_id}/rollback",
        json={"reason": "Should fail"},
    )
    assert rollback_response.status_code == 422
    assert rollback_response.json()["code"] == "ACTION_NOT_REVERSIBLE"


def test_policy_update_requires_policy_id(client: TestClient) -> None:
    response = client.post(
        "/admin/actions/execute",
        json={
            "action_id": "POLICY_UPDATE",
            "input_payload": {
                "changes": {"scope": "tighten_access"},
            },
        },
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "ACTION_INPUT_VALIDATION_FAILED"
    assert "policy_id" in payload["error"]


def test_dsar_rejects_invalid_delivery_method(client: TestClient) -> None:
    response = client.post(
        "/admin/actions/execute",
        json={
            "action_id": "DSAR_EXECUTE",
            "input_payload": {
                "subject_identifier": "subject-123",
                "delivery_method": "public_link",
            },
        },
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "ACTION_INPUT_VALIDATION_FAILED"
    assert "delivery_method" in payload["error"]


def test_segment_activation_requires_approval_and_generates_output(client: TestClient) -> None:
    execute_response = client.post(
        "/admin/actions/execute",
        json={
            "action_id": "SEGMENT_ACTIVATION",
            "input_payload": {
                "segment_id": "segment-a1",
                "destination": "crm",
            },
        },
    )
    assert execute_response.status_code == 200

    execution = execute_response.json()
    assert execution["status"] == "awaiting_approval"

    approve_response = client.post(
        f"/admin/actions/executions/{execution['execution_id']}/approve",
        json={"comment": "Approved segment activation"},
    )
    assert approve_response.status_code == 200

    payload = approve_response.json()["output"]
    assert payload["activation_id"].startswith("activation_")
    assert payload["status"] == "completed"
    assert payload["destination"] == "crm"


def test_connector_refresh_coerces_force_boolean_from_string(client: TestClient) -> None:
    response = client.post(
        "/admin/actions/execute",
        json={
            "action_id": "CONNECTOR_REFRESH",
            "input_payload": {
                "connector_id": "salesforce-prod",
                "force": "yes",
            },
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["input_payload"]["force"] is True
    assert payload["output"]["connector_id"] == "salesforce-prod"


def test_evaluate_escalations_marks_pending_approvals(client: TestClient) -> None:
    execute_response = client.post(
        "/admin/actions/execute",
        json={
            "action_id": "AUDIT_EXPORT",
            "input_payload": {
                "from": "2026-01-01T00:00:00Z",
                "to": "2026-01-31T23:59:59Z",
                "format": "csv",
            },
        },
    )
    assert execute_response.status_code == 200

    execution = execute_response.json()
    approval_due_at = datetime.fromisoformat(execution["approval_due_at"])
    as_of = (approval_due_at + timedelta(minutes=1)).astimezone(UTC)
    as_of_query_value = as_of.isoformat().replace("+00:00", "Z")

    escalate_response = client.post(
        f"/admin/actions/escalations/evaluate?as_of={as_of_query_value}"
    )
    assert escalate_response.status_code == 200

    payload = escalate_response.json()
    assert payload["escalated_count"] == 1
    assert payload["items"][0]["execution_id"] == execution["execution_id"]
    assert payload["items"][0]["escalated"] is True


def test_audit_export_generates_signature_and_window(client: TestClient) -> None:
    execute_response = client.post(
        "/admin/actions/execute",
        json={
            "action_id": "AUDIT_EXPORT",
            "input_payload": {
                "from": "2026-02-01T00:00:00Z",
                "to": "2026-02-28T23:59:59Z",
                "format": "json",
            },
        },
    )
    assert execute_response.status_code == 200
    execution_id = execute_response.json()["execution_id"]

    approve_response = client.post(
        f"/admin/actions/executions/{execution_id}/approve",
        json={"comment": "Approved export"},
    )
    assert approve_response.status_code == 200

    payload = approve_response.json()["output"]
    assert payload["export_id"].startswith("AUDIT_")
    assert payload["signature"]
    assert payload["export_window"]["format"] == "json"
    assert payload["delivery"]["tamper_proof"] is True
