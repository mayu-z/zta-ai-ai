from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_scope, get_db
from app.db.models import ActionExecution, ComplianceCase, PersonaType, Tenant, User, UserStatus
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


def _create_completed_dsar_case(client: TestClient) -> tuple[str, str]:
    create_response = client.post(
        "/admin/compliance/cases",
        json={
            "case_type": "dsar",
            "subject_identifier": "subject-retention",
            "delivery_method": "secure_portal",
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()

    approve_response = client.post(
        f"/admin/compliance/cases/{created['case_id']}/approve",
        json={"comment": "Complete for retention tests"},
    )
    assert approve_response.status_code == 200

    return created["case_id"], created["action_execution_id"]


def _age_case_and_execution(
    db: Session,
    *,
    case_id: str,
    execution_id: str,
    age_days: int,
) -> None:
    timestamp = datetime.now(tz=UTC) - timedelta(days=age_days)
    case = db.scalar(
        select(ComplianceCase).where(
            ComplianceCase.id == case_id,
            ComplianceCase.tenant_id == TENANT_ID,
        )
    )
    assert case is not None
    case.updated_at = timestamp
    case.requested_at = timestamp

    execution = db.get(ActionExecution, execution_id)
    assert execution is not None
    execution.updated_at = timestamp
    execution.requested_at = timestamp

    db.add(case)
    db.add(execution)
    db.commit()


def test_retention_dry_run_reports_candidates_without_deleting(
    client: TestClient,
    db: Session,
) -> None:
    case_id, execution_id = _create_completed_dsar_case(client)
    _age_case_and_execution(db, case_id=case_id, execution_id=execution_id, age_days=120)

    response = client.post(
        "/admin/compliance/retention/run",
        json={
            "retention_days": 30,
            "dry_run": True,
            "max_items": 100,
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["dry_run"] is True
    assert payload["eligible_cases"] == 1
    assert payload["deleted_cases"] == 0
    assert payload["deleted_action_executions"] == 0

    case_response = client.get(f"/admin/compliance/cases/{case_id}")
    assert case_response.status_code == 200

    execution_response = client.get(f"/admin/actions/executions/{execution_id}")
    assert execution_response.status_code == 200


def test_retention_run_deletes_old_terminal_case_and_execution(
    client: TestClient,
    db: Session,
) -> None:
    case_id, execution_id = _create_completed_dsar_case(client)
    _age_case_and_execution(db, case_id=case_id, execution_id=execution_id, age_days=120)

    response = client.post(
        "/admin/compliance/retention/run",
        json={
            "retention_days": 30,
            "dry_run": False,
            "max_items": 100,
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["dry_run"] is False
    assert payload["deleted_cases"] == 1
    assert payload["deleted_action_executions"] >= 1

    case_response = client.get(f"/admin/compliance/cases/{case_id}")
    assert case_response.status_code == 422
    assert case_response.json()["code"] == "COMPLIANCE_CASE_NOT_FOUND"

    execution_response = client.get(f"/admin/actions/executions/{execution_id}")
    assert execution_response.status_code == 422
    assert execution_response.json()["code"] == "ACTION_EXECUTION_NOT_FOUND"


def test_retention_respects_legal_hold(
    client: TestClient,
    db: Session,
) -> None:
    case_id, execution_id = _create_completed_dsar_case(client)
    _age_case_and_execution(db, case_id=case_id, execution_id=execution_id, age_days=120)

    hold_response = client.post(
        f"/admin/compliance/cases/{case_id}/legal-hold",
        json={"active": True, "reason": "Open litigation"},
    )
    assert hold_response.status_code == 200
    assert hold_response.json()["legal_hold_active"] is True

    _age_case_and_execution(db, case_id=case_id, execution_id=execution_id, age_days=120)

    response = client.post(
        "/admin/compliance/retention/run",
        json={
            "retention_days": 30,
            "dry_run": False,
            "max_items": 100,
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["eligible_cases"] == 0
    assert payload["deleted_cases"] == 0
    assert payload["skipped_legal_hold"] >= 1

    case_response = client.get(f"/admin/compliance/cases/{case_id}")
    assert case_response.status_code == 200

    execution_response = client.get(f"/admin/actions/executions/{execution_id}")
    assert execution_response.status_code == 200
