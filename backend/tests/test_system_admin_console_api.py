from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_scope, get_db
from app.db.models import (
    ActionExecution,
    AuditLog,
    ComplianceCase,
    DataSource,
    DataSourceStatus,
    DataSourceType,
    PersonaType,
    Tenant,
    User,
    UserStatus,
)
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


def _insert_audit_log(
    db: Session,
    *,
    user_id: str,
    blocked: bool,
    domain: str,
    created_at: datetime,
    latency_ms: int = 120,
    latency_flag: str | None = None,
    block_reason: str | None = None,
) -> None:
    db.add(
        AuditLog(
            tenant_id=TENANT_ID,
            user_id=user_id,
            session_id=f"session-{user_id[:8]}",
            query_text=f"show me {domain}",
            intent_hash=f"hash-{domain}-{created_at.timestamp()}",
            domains_accessed=[domain],
            was_blocked=blocked,
            block_reason=block_reason
            if block_reason is not None
            else ("policy_denied" if blocked else None),
            response_summary="ok",
            latency_ms=latency_ms,
            latency_flag=latency_flag,
            created_at=created_at,
        )
    )



def test_system_fleet_health_reports_alerts_and_usage_metrics(
    client: TestClient,
    db: Session,
) -> None:
    now = datetime.now(tz=UTC)

    for idx in range(30):
        _insert_audit_log(
            db,
            user_id=USER_ID,
            blocked=(idx % 3 == 0),
            domain="finance" if idx % 2 == 0 else "academic",
            created_at=now - timedelta(hours=2),
        )

    db.add_all(
        [
            DataSource(
                tenant_id=TENANT_ID,
                name="Finance SQL",
                source_type=DataSourceType.postgresql,
                config_encrypted="{}",
                department_scope=[],
                status=DataSourceStatus.connected,
            ),
            DataSource(
                tenant_id=TENANT_ID,
                name="Admissions ERP",
                source_type=DataSourceType.erpnext,
                config_encrypted="{}",
                department_scope=[],
                status=DataSourceStatus.error,
            ),
            DataSource(
                tenant_id=TENANT_ID,
                name="Ops Sheet",
                source_type=DataSourceType.google_sheets,
                config_encrypted="{}",
                department_scope=[],
                status=DataSourceStatus.disconnected,
            ),
        ]
    )
    db.commit()

    action_response = client.post(
        "/admin/actions/execute",
        json={
            "action_id": "CONSENT_WITHDRAWAL",
            "input_payload": {
                "subject_identifier": "subject-system-health",
                "consent_type": "analytics",
            },
        },
    )
    assert action_response.status_code == 200

    response = client.get("/admin/system/fleet-health?lookback_hours=24")
    assert response.status_code == 200

    payload = response.json()
    assert payload["overall_status"] == "critical"
    assert payload["activity"]["queries"] == 30
    assert payload["activity"]["blocked_queries"] == 10
    assert payload["activity"]["actions_executed"] >= 1
    assert payload["connectors"]["total"] == 3
    assert payload["connectors"]["error"] == 1

    alert_codes = {item["code"] for item in payload["alerts"]}
    assert "CONNECTOR_ERRORS_DETECTED" in alert_codes
    assert "HIGH_BLOCKED_QUERY_RATIO" in alert_codes



def test_system_churn_risk_detects_usage_decline_and_connector_instability(
    client: TestClient,
    db: Session,
) -> None:
    now = datetime.now(tz=UTC)

    prior_user_ids = [
        USER_ID,
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
    ]
    for idx, user_id in enumerate(prior_user_ids, start=1):
        if user_id != USER_ID:
            db.add(
                User(
                    id=user_id,
                    tenant_id=TENANT_ID,
                    email=f"analyst{idx}@test.edu",
                    name=f"Analyst {idx}",
                    persona_type=PersonaType.admin_staff,
                    external_id=f"analyst-{idx}",
                    status=UserStatus.active,
                )
            )
    db.commit()

    prior_start = now - timedelta(days=14)
    for idx in range(90):
        user_id = prior_user_ids[idx % len(prior_user_ids)]
        _insert_audit_log(
            db,
            user_id=user_id,
            blocked=False,
            domain="finance",
            created_at=prior_start + timedelta(days=2, minutes=idx),
        )

    recent_start = now - timedelta(days=7)
    for idx in range(20):
        _insert_audit_log(
            db,
            user_id=USER_ID,
            blocked=False,
            domain="finance",
            created_at=recent_start + timedelta(days=1, minutes=idx),
        )

    db.add(
        DataSource(
            tenant_id=TENANT_ID,
            name="Risk Warehouse",
            source_type=DataSourceType.postgresql,
            config_encrypted="{}",
            department_scope=[],
            status=DataSourceStatus.error,
        )
    )
    db.commit()

    response = client.get("/admin/system/churn-risk?window_days=14")
    assert response.status_code == 200

    payload = response.json()
    assert payload["risk_level"] == "high"
    assert payload["risk_score"] >= 7.0

    signal_codes = {item["code"] for item in payload["signals"]}
    assert "QUERY_VOLUME_DECLINE" in signal_codes
    assert "ACTIVE_USER_DECLINE" in signal_codes
    assert "CONNECTOR_INSTABILITY" in signal_codes



def test_system_llm_cost_analytics_estimates_spend(
    client: TestClient,
    db: Session,
) -> None:
    now = datetime.now(tz=UTC)

    for idx in range(100):
        _insert_audit_log(
            db,
            user_id=USER_ID,
            blocked=False,
            domain="finance" if idx < 70 else "admin",
            created_at=now - timedelta(days=2, minutes=idx),
        )
    db.commit()

    response = client.get(
        "/admin/system/llm-costs?window_days=30&estimated_cost_per_query=0.01"
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["summary"]["total_queries"] == 100
    assert payload["summary"]["estimated_total_spend"] == 1.0
    assert payload["cost_model"]["estimated_cost_per_query"] == 0.01

    top_domains = payload["breakdown"]["top_domains"]
    assert top_domains
    assert top_domains[0]["domain"] == "finance"



def test_system_tenant_deep_dive_includes_compliance_counts(
    client: TestClient,
) -> None:
    case_response = client.post(
        "/admin/compliance/cases",
        json={
            "case_type": "dsar",
            "subject_identifier": "subject-deep-dive",
            "delivery_method": "secure_portal",
        },
    )
    assert case_response.status_code == 200

    attestation_response = client.post(
        "/admin/compliance/attestations",
        json={
            "framework": "GDPR",
            "max_items": 100,
        },
    )
    assert attestation_response.status_code == 200

    response = client.get("/admin/system/tenant-deep-dive?window_days=30")
    assert response.status_code == 200

    payload = response.json()
    assert payload["compliance"]["cases_total"] >= 1
    assert payload["compliance"]["attestations_total"] >= 1


def test_system_slo_compliance_reports_breached_checks(
    client: TestClient,
    db: Session,
) -> None:
    now = datetime.now(tz=UTC)

    for idx in range(100):
        _insert_audit_log(
            db,
            user_id=USER_ID,
            blocked=False,
            domain="finance",
            created_at=now - timedelta(days=1, minutes=idx),
            latency_ms=1400,
            latency_flag="error" if idx == 0 else None,
        )
    db.commit()

    response = client.get(
        "/admin/system/slo-compliance?window_days=30&latency_target_ms=1000&error_budget_percent=0.1"
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["overall_status"] == "breached"
    assert payload["observed"]["latency_p95_ms"] >= 1400
    assert payload["observed"]["error_rate_percent"] == 1.0

    checks = {entry["code"]: entry for entry in payload["checks"]}
    assert checks["LATENCY_P95"]["met"] is False
    assert checks["ERROR_RATE"]["met"] is False


def test_system_alerts_surfaces_operational_risks(
    client: TestClient,
    db: Session,
) -> None:
    now = datetime.now(tz=UTC)

    for idx in range(30):
        _insert_audit_log(
            db,
            user_id=USER_ID,
            blocked=(idx % 3 == 0),
            domain="admin" if idx % 2 == 0 else "finance",
            created_at=now - timedelta(hours=2, minutes=idx),
            latency_ms=150,
            latency_flag="error" if idx == 0 else None,
        )

    db.add(
        DataSource(
            tenant_id=TENANT_ID,
            name="Ops API",
            source_type=DataSourceType.erpnext,
            config_encrypted="{}",
            department_scope=[],
            status=DataSourceStatus.error,
        )
    )
    db.commit()

    execute_response = client.post(
        "/admin/actions/execute",
        json={
            "action_id": "DSAR_EXECUTE",
            "input_payload": {
                "subject_identifier": "subject-overdue-approval",
                "delivery_method": "secure_portal",
            },
        },
    )
    assert execute_response.status_code == 200
    execution_id = execute_response.json()["execution_id"]

    execution = db.get(ActionExecution, execution_id)
    assert execution is not None
    execution.approval_due_at = now - timedelta(hours=1)
    execution.status = "awaiting_approval"
    db.add(execution)

    case_response = client.post(
        "/admin/compliance/cases",
        json={
            "case_type": "dsar",
            "subject_identifier": "subject-sla-breach",
            "delivery_method": "secure_portal",
        },
    )
    assert case_response.status_code == 200
    case_id = case_response.json()["case_id"]

    case = db.get(ComplianceCase, case_id)
    assert case is not None
    case.sla_due_at = now - timedelta(hours=2)
    case.status = "executing"
    db.add(case)
    db.commit()

    response = client.get("/admin/system/alerts?lookback_hours=24")
    assert response.status_code == 200

    payload = response.json()
    alert_codes = {item["code"] for item in payload["alerts"]}
    assert "CONNECTOR_ERRORS_DETECTED" in alert_codes
    assert "QUERY_ERROR_BUDGET_EXCEEDED" in alert_codes
    assert "HIGH_POLICY_DENY_RATIO" in alert_codes
    assert "OVERDUE_APPROVAL_QUEUE" in alert_codes
    assert "COMPLIANCE_SLA_BREACHES" in alert_codes


def test_system_capacity_model_reports_headroom_and_status(
    client: TestClient,
    db: Session,
) -> None:
    now = datetime.now(tz=UTC)

    user_ids = [
        USER_ID,
        "33333333-3333-3333-3333-333333333333",
        "44444444-4444-4444-4444-444444444444",
    ]
    for idx, user_id in enumerate(user_ids, start=1):
        if user_id != USER_ID:
            db.add(
                User(
                    id=user_id,
                    tenant_id=TENANT_ID,
                    email=f"ops{idx}@test.edu",
                    name=f"Ops {idx}",
                    persona_type=PersonaType.admin_staff,
                    external_id=f"ops-{idx}",
                    status=UserStatus.active,
                )
            )
    db.commit()

    for idx in range(120):
        _insert_audit_log(
            db,
            user_id=user_ids[idx % len(user_ids)],
            blocked=False,
            domain="finance",
            created_at=now - timedelta(minutes=idx // 3),
            latency_ms=900,
        )
    db.commit()

    response = client.get("/admin/system/capacity-model?window_days=30&target_p95_ms=1000")
    assert response.status_code == 200

    payload = response.json()
    assert payload["targets"]["p95_latency_ms"] == 1000
    assert payload["observed"]["total_queries"] == 120
    assert payload["observed"]["peak_active_users_per_minute"] >= 1
    assert payload["model"]["estimated_max_concurrent_users"] >= 10
    assert payload["model"]["capacity_status"] in {
        "healthy",
        "near_capacity",
        "over_capacity",
    }


def test_system_degradation_policy_reports_critical_mode_when_signals_breach(
    client: TestClient,
    db: Session,
) -> None:
    now = datetime.now(tz=UTC)

    for idx in range(60):
        _insert_audit_log(
            db,
            user_id=USER_ID,
            blocked=False,
            domain="admin",
            created_at=now - timedelta(minutes=idx),
            latency_ms=1700,
            latency_flag="error" if idx % 10 == 0 else None,
        )

    for idx in range(55):
        db.add(
            ActionExecution(
                tenant_id=TENANT_ID,
                action_id="DSAR_EXECUTE",
                status="awaiting_approval",
                dry_run=False,
                input_payload={"subject_identifier": f"subject-{idx}"},
                requested_by=USER_ID,
            )
        )

    db.commit()

    response = client.get(
        "/admin/system/degradation-policy?lookback_hours=24"
        "&warning_p95_ms=1000&critical_p95_ms=1500"
        "&warning_error_rate_percent=0.1&critical_error_rate_percent=1.0"
        "&warning_pending_actions=20&critical_pending_actions=50"
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["degradation_mode"] == "critical"
    assert payload["signals"]["p95_latency_ms"] >= 1500
    assert payload["signals"]["pending_actions"] >= 50
    assert payload["controls"]


def test_system_performance_regression_flags_regressed_release_profile(
    client: TestClient,
    db: Session,
) -> None:
    now = datetime.now(tz=UTC)

    for idx in range(80):
        _insert_audit_log(
            db,
            user_id=USER_ID,
            blocked=False,
            domain="finance",
            created_at=now - timedelta(hours=30, minutes=idx),
            latency_ms=450,
        )

    for idx in range(80):
        _insert_audit_log(
            db,
            user_id=USER_ID,
            blocked=False,
            domain="finance",
            created_at=now - timedelta(hours=2, minutes=idx),
            latency_ms=1400,
            latency_flag="error" if idx % 16 == 0 else None,
        )

    db.commit()

    response = client.get(
        "/admin/system/performance-regression?window_hours=24"
        "&max_p95_regression_percent=10"
        "&max_p99_regression_percent=10"
        "&max_error_rate_percent=1.0"
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["overall_status"] == "regressed"
    assert payload["metrics"]["recent"]["total_queries"] == 80
    assert payload["metrics"]["baseline"]["total_queries"] == 80
    assert payload["metrics"]["delta"]["p95_regression_percent"] > 10

    checks = {item["code"]: item for item in payload["checks"]}
    assert checks["P95_REGRESSION"]["met"] is False
    assert checks["ERROR_RATE_BUDGET"]["met"] is False


def test_system_performance_regression_reports_stable_when_within_thresholds(
    client: TestClient,
    db: Session,
) -> None:
    now = datetime.now(tz=UTC)

    for idx in range(60):
        _insert_audit_log(
            db,
            user_id=USER_ID,
            blocked=False,
            domain="admin",
            created_at=now - timedelta(hours=30, minutes=idx),
            latency_ms=700,
        )

    for idx in range(60):
        _insert_audit_log(
            db,
            user_id=USER_ID,
            blocked=False,
            domain="admin",
            created_at=now - timedelta(hours=1, minutes=idx),
            latency_ms=720,
        )

    db.commit()

    response = client.get(
        "/admin/system/performance-regression?window_hours=24"
        "&max_p95_regression_percent=10"
        "&max_p99_regression_percent=15"
        "&max_error_rate_percent=0.5"
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["overall_status"] == "stable"
    checks = {item["code"]: item for item in payload["checks"]}
    assert checks["P95_REGRESSION"]["met"] is True
    assert checks["P99_REGRESSION"]["met"] is True
    assert checks["ERROR_RATE_BUDGET"]["met"] is True
