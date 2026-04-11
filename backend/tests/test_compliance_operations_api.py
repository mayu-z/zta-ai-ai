from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_scope, get_db
from app.db.models import AuditLog, PersonaType, Tenant, User, UserStatus
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


def _insert_audit_log(db: Session, *, blocked: bool, created_at: datetime) -> None:
    db.add(
        AuditLog(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            session_id="session-1",
            query_text="show me audit evidence",
            intent_hash="abc123",
            domains_accessed=["compliance"],
            was_blocked=blocked,
            block_reason="policy_denied" if blocked else None,
            response_summary="ok",
            latency_ms=120,
            latency_flag=None,
            created_at=created_at,
        )
    )
    db.commit()


def test_compliance_summary_aggregates_action_and_audit_metrics(
    client: TestClient,
    db: Session,
) -> None:
    now = datetime.now(tz=UTC)

    dsar_execute = client.post(
        "/admin/actions/execute",
        json={
            "action_id": "DSAR_EXECUTE",
            "input_payload": {
                "subject_identifier": "subject-123",
                "delivery_method": "secure_portal",
            },
        },
    )
    assert dsar_execute.status_code == 200

    dsar_execution_id = dsar_execute.json()["execution_id"]
    dsar_approve = client.post(
        f"/admin/actions/executions/{dsar_execution_id}/approve",
        json={"comment": "Approved DSAR"},
    )
    assert dsar_approve.status_code == 200

    erasure_execute = client.post(
        "/admin/actions/execute",
        json={
            "action_id": "ERASURE_EXECUTE",
            "input_payload": {
                "subject_identifier": "subject-456",
                "legal_basis": "gdpr_article_17",
            },
        },
    )
    assert erasure_execute.status_code == 200

    _insert_audit_log(db, blocked=False, created_at=now)
    _insert_audit_log(db, blocked=True, created_at=now)

    from_at = (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    to_at = (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    summary_response = client.get(
        f"/admin/compliance/summary?from_at={from_at}&to_at={to_at}"
    )

    assert summary_response.status_code == 200
    payload = summary_response.json()

    assert payload["dsar"]["total_requests"] == 1
    assert payload["dsar"]["completed"] == 1
    assert payload["erasure"]["total_requests"] == 1
    assert payload["erasure"]["pending"] == 1
    assert payload["audit"]["total_query_events"] == 2
    assert payload["audit"]["blocked_query_events"] == 1


def test_forensic_export_filters_actions_and_blocked_audit_events(
    client: TestClient,
    db: Session,
) -> None:
    now = datetime.now(tz=UTC)

    incident_execute = client.post(
        "/admin/actions/execute",
        json={
            "action_id": "INCIDENT_RESPONSE",
            "input_payload": {
                "incident_id": "inc-100",
                "severity": "critical",
            },
        },
    )
    assert incident_execute.status_code == 200

    incident_execution_id = incident_execute.json()["execution_id"]
    incident_approve = client.post(
        f"/admin/actions/executions/{incident_execution_id}/approve",
        json={"comment": "Approved incident response"},
    )
    assert incident_approve.status_code == 200

    _insert_audit_log(db, blocked=False, created_at=now)
    _insert_audit_log(db, blocked=True, created_at=now)

    response = client.post(
        "/admin/compliance/forensic-export",
        json={
            "from_at": (now - timedelta(hours=1)).isoformat().replace(
                "+00:00", "Z"
            ),
            "to_at": (now + timedelta(hours=1)).isoformat().replace(
                "+00:00", "Z"
            ),
            "include_action_ids": ["INCIDENT_RESPONSE"],
            "include_blocked_queries_only": True,
            "max_items": 100,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["export_id"].startswith("forensic_")
    assert len(payload["signature"]) == 64
    assert payload["summary"]["action_count"] >= 1
    assert all(item["action_id"] == "INCIDENT_RESPONSE" for item in payload["actions"])
    assert payload["audit_events"]
    assert all(item["was_blocked"] is True for item in payload["audit_events"])
