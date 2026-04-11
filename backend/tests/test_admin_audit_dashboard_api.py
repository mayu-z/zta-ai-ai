from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_scope, get_db
from app.db.models import AuditLog, PersonaType, Tenant, User, UserStatus
from app.main import app
from app.schemas.pipeline import ScopeContext


TENANT_ID = "22345678-1234-1234-1234-123456789012"
PRIMARY_USER_ID = "77654321-4321-4321-4321-210987654321"
SECONDARY_USER_ID = "11111111-2222-3333-4444-555555555555"


@pytest.fixture
def tenant_and_users(db: Session):
    tenant = Tenant(
        id=TENANT_ID,
        name="Audit Test University",
        domain="audit-test.edu",
        subdomain="audit-test",
    )
    user_primary = User(
        id=PRIMARY_USER_ID,
        tenant_id=TENANT_ID,
        email="ithead@audit-test.edu",
        name="IT Head",
        persona_type=PersonaType.it_head,
        external_id="it-001",
        status=UserStatus.active,
    )
    user_secondary = User(
        id=SECONDARY_USER_ID,
        tenant_id=TENANT_ID,
        email="analyst@audit-test.edu",
        name="Analyst",
        persona_type=PersonaType.admin_staff,
        external_id="analyst-001",
        status=UserStatus.active,
    )
    db.add_all([tenant, user_primary, user_secondary])
    db.commit()
    return tenant, user_primary, user_secondary


@pytest.fixture
def client(db: Session, tenant_and_users):
    test_scope = ScopeContext(
        tenant_id=TENANT_ID,
        user_id=PRIMARY_USER_ID,
        persona_type="it_head",
        email="ithead@audit-test.edu",
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


def _insert_audit_event(
    db: Session,
    *,
    user_id: str,
    blocked: bool,
    block_reason: str | None,
    domain: str,
    latency_ms: int,
    latency_flag: str | None,
    created_at: datetime,
) -> None:
    db.add(
        AuditLog(
            tenant_id=TENANT_ID,
            user_id=user_id,
            session_id=f"session-{user_id[:8]}",
            query_text=f"show {domain} report",
            intent_hash=f"hash-{domain}-{created_at.timestamp()}-{user_id[:4]}",
            domains_accessed=[domain],
            was_blocked=blocked,
            block_reason=block_reason,
            response_summary="ok",
            latency_ms=latency_ms,
            latency_flag=latency_flag,
            created_at=created_at,
        )
    )


def test_audit_dashboard_returns_summary_and_policy_decisions(
    client: TestClient,
    db: Session,
) -> None:
    now = datetime.now(tz=UTC)

    for idx in range(30):
        _insert_audit_event(
            db,
            user_id=PRIMARY_USER_ID if idx % 2 == 0 else SECONDARY_USER_ID,
            blocked=(idx % 5 == 0),
            block_reason="policy_denied" if idx % 5 == 0 else None,
            domain="finance" if idx < 20 else "academic",
            latency_ms=120 + idx,
            latency_flag="error" if idx == 0 else None,
            created_at=now - timedelta(hours=2, minutes=idx),
        )

    db.commit()

    response = client.get("/admin/audit-dashboard?window_hours=24&anomaly_limit=10")
    assert response.status_code == 200

    payload = response.json()
    assert payload["summary"]["total_events"] == 30
    assert payload["summary"]["blocked_events"] == 6
    assert payload["summary"]["allowed_events"] == 24
    assert payload["summary"]["unique_users"] == 2

    policy_decisions = payload["policy_decisions"]
    assert policy_decisions["allowed"] == 24
    assert policy_decisions["blocked"] == 6
    assert policy_decisions["top_block_reasons"]
    assert policy_decisions["top_block_reasons"][0]["reason"] == "policy_denied"

    top_domains = payload["usage"]["top_domains"]
    assert top_domains
    assert top_domains[0]["domain"] == "finance"


def test_audit_dashboard_detects_anomaly_patterns(
    client: TestClient,
    db: Session,
) -> None:
    now = datetime.now(tz=UTC)
    out_of_hours_base = datetime(now.year, now.month, now.day, 2, 15, tzinfo=UTC)
    if out_of_hours_base > now:
        out_of_hours_base -= timedelta(days=1)

    for idx in range(20):
        _insert_audit_event(
            db,
            user_id=PRIMARY_USER_ID,
            blocked=True,
            block_reason="policy_denied",
            domain="admin",
            latency_ms=1450,
            latency_flag="error" if idx == 0 else None,
            created_at=now - timedelta(hours=1, minutes=idx),
        )

    for idx in range(7):
        _insert_audit_event(
            db,
            user_id=SECONDARY_USER_ID,
            blocked=False,
            block_reason=None,
            domain="finance",
            latency_ms=200,
            latency_flag=None,
            created_at=out_of_hours_base + timedelta(minutes=idx),
        )

    db.commit()

    response = client.get("/admin/audit-dashboard?window_hours=48&anomaly_limit=20")
    assert response.status_code == 200

    payload = response.json()
    anomaly_codes = {item["code"] for item in payload["anomalies"]}

    assert "HIGH_BLOCKED_QUERY_RATIO" in anomaly_codes
    assert "ERROR_FLAG_BUDGET_EXCEEDED" in anomaly_codes
    assert "P95_LATENCY_TARGET_BREACH" in anomaly_codes
    assert "ELEVATED_OUT_OF_HOURS_ACTIVITY" in anomaly_codes
    assert "REPEATED_POLICY_DENIALS_BY_USER" in anomaly_codes
