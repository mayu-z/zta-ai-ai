from __future__ import annotations

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_scope, get_db
from app.db.models import DataSource, PersonaType, Tenant, User, UserStatus
from app.main import app
from app.schemas.pipeline import ScopeContext


TENANT_ID = "32345678-1234-1234-1234-123456789012"
USER_ID = "67654321-4321-4321-4321-210987654321"


@pytest.fixture
def tenant_and_user(db: Session):
    tenant = Tenant(
        id=TENANT_ID,
        name="Connector Test University",
        domain="connector-test.edu",
        subdomain="connector-test",
    )
    user = User(
        id=USER_ID,
        tenant_id=TENANT_ID,
        email="ithead@connector-test.edu",
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
        email="ithead@connector-test.edu",
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


def _create_google_source(client: TestClient, *, include_sheet_rows: bool = True) -> str:
    config: dict[str, object] = {
        "service_account_json": {"project_id": "demo-project"},
        "spreadsheet_id": "sheet-123",
    }
    if include_sheet_rows:
        config["sheet_rows"] = [
            {
                "tenant_id": TENANT_ID,
                "domain": "admin",
                "entity_type": "records",
                "claim_key": "record_count",
                "value_number": 5,
            }
        ]

    response = client.post(
        "/admin/data-sources",
        json={
            "name": "Research Sheet",
            "source_type": "google_sheets",
            "config": config,
            "department_scope": ["finance", " admin "],
        },
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_data_source_test_connection_success_updates_status(
    client: TestClient,
) -> None:
    source_id = _create_google_source(client)

    response = client.post(
        f"/admin/data-sources/{source_id}/test-connection?timeout_seconds=10"
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["test_result"]["status"] == "healthy"
    assert payload["data_source"]["status"] == "connected"
    assert payload["data_source"]["last_sync_at"] is not None
    assert payload["data_source"]["sync_error_msg"] is None


def test_data_source_test_connection_invalid_config_sets_error(
    client: TestClient,
) -> None:
    response = client.post(
        "/admin/data-sources",
        json={
            "name": "Broken Sheet",
            "source_type": "google_sheets",
            "config": {
                "service_account_json": {"project_id": "demo-project"},
            },
            "department_scope": [],
        },
    )
    assert response.status_code == 200
    source_id = response.json()["id"]

    test_response = client.post(
        f"/admin/data-sources/{source_id}/test-connection?timeout_seconds=10"
    )
    assert test_response.status_code == 200

    payload = test_response.json()
    assert payload["test_result"]["status"] == "error"
    assert payload["test_result"]["error_code"] == "SOURCE_CONFIG_INVALID"
    assert payload["data_source"]["status"] == "error"
    assert "spreadsheet_id" in (payload["data_source"]["sync_error_msg"] or "")


def test_data_source_health_endpoint_returns_health_details(
    client: TestClient,
) -> None:
    source_id = _create_google_source(client, include_sheet_rows=False)

    response = client.get(f"/admin/data-sources/{source_id}/health")
    assert response.status_code == 200

    payload = response.json()
    assert payload["health"]["status"] == "degraded"
    assert payload["connection_info"]["source_type"] == "google_sheets"


def test_data_source_update_disable_enable_flow(
    client: TestClient,
    db: Session,
) -> None:
    source_id = _create_google_source(client)

    update_response = client.put(
        f"/admin/data-sources/{source_id}",
        json={
            "name": "Research Sheet v2",
            "department_scope": ["finance", "compliance"],
            "status": "paused",
            "config": {
                "service_account_json": {"project_id": "demo-project-v2"},
                "spreadsheet_id": "sheet-456",
                "sheet_rows": [],
            },
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["name"] == "Research Sheet v2"
    assert updated["status"] == "paused"
    assert updated["department_scope"] == ["finance", "compliance"]

    enable_response = client.post(f"/admin/data-sources/{source_id}/enable")
    assert enable_response.status_code == 200
    assert enable_response.json()["status"] == "connected"

    disable_response = client.post(f"/admin/data-sources/{source_id}/disable")
    assert disable_response.status_code == 200
    assert disable_response.json()["status"] == "paused"

    row = db.scalar(
        select(DataSource).where(
            DataSource.id == source_id,
            DataSource.tenant_id == TENANT_ID,
        )
    )
    assert row is not None
    assert row.status.value == "paused"


def test_data_source_update_rejects_invalid_status(client: TestClient) -> None:
    source_id = _create_google_source(client)

    response = client.put(
        f"/admin/data-sources/{source_id}",
        json={"status": "error"},
    )
    assert response.status_code == 422


def test_data_source_sync_populates_schema_and_history(
    client: TestClient,
) -> None:
    source_id = _create_google_source(client)

    sync_response = client.post(
        f"/admin/data-sources/{source_id}/sync?force_schema_refresh=true"
    )
    assert sync_response.status_code == 200

    sync_payload = sync_response.json()
    assert sync_payload["sync_result"]["status"] == "complete"
    assert sync_payload["schema_refresh"]["added"] >= 1
    assert sync_payload["schema_refresh"]["total_fields"] >= 1
    assert sync_payload["data_source"]["status"] == "connected"

    schema_response = client.get(f"/admin/data-sources/{source_id}/schema")
    assert schema_response.status_code == 200
    schema_items = schema_response.json()
    assert any(item["real_column"] == "claim_key" for item in schema_items)

    history_response = client.get(f"/admin/data-sources/{source_id}/sync-history")
    assert history_response.status_code == 200
    history_payload = history_response.json()
    assert history_payload["history_mode"] == "derived"
    assert history_payload["schema_snapshot"]["total_fields"] >= 1
    assert any(event["event"] == "sync_completed" for event in history_payload["events"])


def test_data_source_resync_schema_prunes_removed_fields(
    client: TestClient,
) -> None:
    source_id = _create_google_source(client)

    initial_sync = client.post(
        f"/admin/data-sources/{source_id}/sync?force_schema_refresh=true"
    )
    assert initial_sync.status_code == 200
    assert initial_sync.json()["schema_refresh"]["total_fields"] >= 5

    update_response = client.put(
        f"/admin/data-sources/{source_id}",
        json={
            "config": {
                "service_account_json": {"project_id": "demo-project"},
                "spreadsheet_id": "sheet-123",
                "sheet_rows": [
                    {
                        "tenant_id": TENANT_ID,
                        "domain": "admin",
                        "entity_type": "records",
                        "claim_key": "record_count",
                    }
                ],
            }
        },
    )
    assert update_response.status_code == 200

    resync_response = client.post(
        f"/admin/data-sources/{source_id}/resync-schema?force_refresh=true&prune_removed_fields=true"
    )
    assert resync_response.status_code == 200

    resync_payload = resync_response.json()
    assert resync_payload["schema_refresh"]["removed"] >= 1
    assert resync_payload["schema_refresh"]["total_fields"] == 4

    schema_response = client.get(f"/admin/data-sources/{source_id}/schema")
    assert schema_response.status_code == 200
    schema_columns = {item["real_column"] for item in schema_response.json()}
    assert "value_number" not in schema_columns


def test_data_source_sync_handles_invalid_connector_config(
    client: TestClient,
) -> None:
    response = client.post(
        "/admin/data-sources",
        json={
            "name": "Broken Sync Sheet",
            "source_type": "google_sheets",
            "config": {
                "service_account_json": {"project_id": "demo-project"},
            },
            "department_scope": [],
        },
    )
    assert response.status_code == 200
    source_id = response.json()["id"]

    sync_response = client.post(f"/admin/data-sources/{source_id}/sync")
    assert sync_response.status_code == 200

    payload = sync_response.json()
    assert payload["sync_result"]["status"] == "failed"
    assert payload["error_code"] == "SOURCE_CONFIG_INVALID"
    assert payload["data_source"]["status"] == "error"
