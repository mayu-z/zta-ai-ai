from __future__ import annotations

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.agentic.db_models import AgenticActionConfigModel
from app.api.deps import get_current_scope, get_db
from app.core.redis_client import redis_client
from app.db.models import PersonaType, Tenant, User, UserStatus
from app.main import app
from app.schemas.pipeline import ScopeContext


TENANT_ID = "72345678-1234-1234-1234-123456789012"
USER_ID = "87654321-4321-4321-4321-210987654321"
ACTION_ID = "fee_reminder_v1"


@pytest.fixture
def tenant_and_user(db: Session):
    tenant = Tenant(
        id=TENANT_ID,
        name="Definition Test University",
        domain="definition-test.edu",
        subdomain="definition-test",
    )
    user = User(
        id=USER_ID,
        tenant_id=TENANT_ID,
        email="ithead@definition-test.edu",
        name="IT Head",
        persona_type=PersonaType.it_head,
        external_id="it-001",
        status=UserStatus.active,
    )
    db.add_all([tenant, user])
    db.commit()

    config = AgenticActionConfigModel(
        action_id=ACTION_ID,
        tenant_id=TENANT_ID,
        display_name="Fee Reminder",
        description="desc",
        trigger_type="scheduled",
        required_data_scope=["fees.own"],
        output_type="notification",
        requires_confirmation=False,
        human_approval_required=False,
        approval_level="self",
        allowed_personas=["student", "staff"],
        financial_transaction=False,
        has_sensitive_fields=False,
        cache_results=True,
        extra_config={},
        is_enabled=True,
        version=1,
    )
    db.add(config)
    db.commit()

    return tenant, user


@pytest.fixture
def client(db: Session, tenant_and_user):
    test_scope = ScopeContext(
        tenant_id=TENANT_ID,
        user_id=USER_ID,
        persona_type="it_head",
        email="ithead@definition-test.edu",
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


def test_list_agentic_definitions(client: TestClient) -> None:
    response = client.get("/admin/agentic/definitions")
    assert response.status_code == 200

    payload = response.json()
    assert payload["definitions"]
    assert any(item["agent_id"] == ACTION_ID for item in payload["definitions"])


def test_upsert_get_delete_agentic_definition_override(client: TestClient) -> None:
    upsert_response = client.put(
        f"/admin/agentic/definitions/{ACTION_ID}/override",
        json={
            "override": {
                "config": {
                    "rate_limit_max_per_day": 7,
                }
            }
        },
    )
    assert upsert_response.status_code == 200
    upsert_payload = upsert_response.json()
    assert upsert_payload["override"]["config"]["rate_limit_max_per_day"] == 7

    get_response = client.get(f"/admin/agentic/definitions/{ACTION_ID}")
    assert get_response.status_code == 200
    get_payload = get_response.json()
    assert get_payload["has_override"] is True
    assert get_payload["definition"]["config"]["rate_limit_max_per_day"] == 7

    delete_response = client.delete(f"/admin/agentic/definitions/{ACTION_ID}/override")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True


def test_upsert_agentic_definition_override_rejects_non_allowlisted_paths(client: TestClient) -> None:
    response = client.put(
        f"/admin/agentic/definitions/{ACTION_ID}/override",
        json={
            "override": {
                "description": "tampered",
            }
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "AGENT_DEFINITION_OVERRIDE_INVALID"


def test_invalidate_agentic_definition_cache(client: TestClient) -> None:
    definition_key = f"agentic:def:{TENANT_ID}:{ACTION_ID}"
    action_key = f"agentic:action:{TENANT_ID}:{ACTION_ID}"
    redis_client.client.set(definition_key, "1")
    redis_client.client.set(action_key, "1")

    response = client.post(
        "/admin/agentic/definitions/cache/invalidate",
        json={
            "agent_ids": [ACTION_ID],
            "include_action_cache": True,
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["requested_agent_ids"] == [ACTION_ID]
    assert payload["deleted_definition_keys"] >= 1
    assert payload["deleted_action_keys"] >= 1
