from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_scope, get_db
from app.db.models import (
    DataSource,
    DataSourceStatus,
    DataSourceType,
    FieldVisibility,
    PersonaType,
    RolePolicy,
    SchemaField,
    Tenant,
    User,
    UserStatus,
)
from app.main import app
from app.schemas.pipeline import ScopeContext


TENANT_ID = "42345678-1234-1234-1234-123456789012"
USER_ID = "57654321-4321-4321-4321-210987654321"


@pytest.fixture
def tenant_user_and_role_policies(db: Session):
    tenant = Tenant(
        id=TENANT_ID,
        name="Policy Test University",
        domain="policy-test.edu",
        subdomain="policy-test",
    )
    user = User(
        id=USER_ID,
        tenant_id=TENANT_ID,
        email="ithead@policy-test.edu",
        name="IT Head",
        persona_type=PersonaType.it_head,
        external_id="it-001",
        status=UserStatus.active,
    )
    db.add_all([tenant, user])

    db.add_all(
        [
            RolePolicy(
                tenant_id=TENANT_ID,
                role_key="student",
                display_name="Student",
                allowed_domains=["academic"],
                masked_fields=[],
            ),
            RolePolicy(
                tenant_id=TENANT_ID,
                role_key="admin_staff",
                display_name="Admin Staff",
                allowed_domains=["admin"],
                masked_fields=[],
            ),
            RolePolicy(
                tenant_id=TENANT_ID,
                role_key="admin_staff:finance",
                display_name="Finance Admin",
                allowed_domains=["finance"],
                masked_fields=[],
            ),
        ]
    )

    db.commit()
    return tenant, user


@pytest.fixture
def client(db: Session, tenant_user_and_role_policies):
    test_scope = ScopeContext(
        tenant_id=TENANT_ID,
        user_id=USER_ID,
        persona_type="it_head",
        email="ithead@policy-test.edu",
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


def _seed_schema_field(db: Session, alias_token: str = "student_ssn") -> tuple[str, str]:
    source = DataSource(
        tenant_id=TENANT_ID,
        name="Policy Source",
        source_type=DataSourceType.google_sheets,
        config_encrypted="{}",
        department_scope=[],
        status=DataSourceStatus.connected,
    )
    db.add(source)
    db.flush()

    field = SchemaField(
        tenant_id=TENANT_ID,
        data_source_id=source.id,
        real_table="student_records",
        real_column="ssn",
        alias_token=alias_token,
        display_name="Student SSN",
        data_type="text",
        visibility=FieldVisibility.visible,
        pii_flag=False,
        masked_for_personas=[],
    )
    db.add(field)
    db.commit()
    return source.id, field.id


def test_list_field_level_masking_rules_returns_schema_data(
    client: TestClient,
    db: Session,
) -> None:
    source_id, field_id = _seed_schema_field(db)

    response = client.get(f"/admin/policies/field-level-masking?data_source_id={source_id}")
    assert response.status_code == 200

    payload = response.json()
    assert payload["summary"]["total_fields"] == 1
    assert payload["summary"]["masked_fields"] == 0

    item = payload["items"][0]
    assert item["schema_field_id"] == field_id
    assert item["alias_token"] == "student_ssn"
    assert item["visibility"] == "visible"
    assert item["role_keys_masked"] == []


def test_update_field_level_masking_rule_syncs_role_policies(
    client: TestClient,
    db: Session,
) -> None:
    _source_id, field_id = _seed_schema_field(db, alias_token="ssn_token")

    update_response = client.put(
        "/admin/policies/field-level-masking",
        json={
            "schema_field_id": field_id,
            "visibility": "masked",
            "pii_flag": True,
            "masked_for_personas": ["student", "admin_staff"],
            "display_name": "Student Identifier",
        },
    )
    assert update_response.status_code == 200

    payload = update_response.json()
    assert payload["item"]["visibility"] == "masked"
    assert payload["item"]["pii_flag"] is True
    assert sorted(payload["item"]["masked_for_personas"]) == ["admin_staff", "student"]

    added_roles = set(payload["sync"]["added_to_role_policies"])
    assert "student" in added_roles
    assert "admin_staff" in added_roles
    assert "admin_staff:finance" in added_roles

    role_rows = db.scalars(
        select(RolePolicy).where(RolePolicy.tenant_id == TENANT_ID)
    ).all()
    for row in role_rows:
        if row.role_key in {"student", "admin_staff", "admin_staff:finance"}:
            assert "ssn_token" in row.masked_fields

    remove_response = client.put(
        "/admin/policies/field-level-masking",
        json={
            "schema_field_id": field_id,
            "masked_for_personas": [],
        },
    )
    assert remove_response.status_code == 200

    removed_roles = set(remove_response.json()["sync"]["removed_from_role_policies"])
    assert "student" in removed_roles
    assert "admin_staff" in removed_roles
    assert "admin_staff:finance" in removed_roles

    role_rows_after = db.scalars(
        select(RolePolicy).where(RolePolicy.tenant_id == TENANT_ID)
    ).all()
    for row in role_rows_after:
        if row.role_key in {"student", "admin_staff", "admin_staff:finance"}:
            assert "ssn_token" not in row.masked_fields


def test_update_field_level_masking_rule_rejects_unknown_persona(
    client: TestClient,
    db: Session,
) -> None:
    _source_id, field_id = _seed_schema_field(db, alias_token="pii_field")

    response = client.put(
        "/admin/policies/field-level-masking",
        json={
            "schema_field_id": field_id,
            "masked_for_personas": ["unknown_persona"],
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_PERSONA_TYPE"


def test_update_row_level_policy_rule_endpoint_updates_role_policy(
    client: TestClient,
) -> None:
    response = client.put(
        "/admin/policies/row-level/student",
        json={
            "row_scope_mode": "owner_id",
            "sensitive_domains": ["finance", "academic"],
            "require_business_hours_for_sensitive": False,
            "business_hours_start": 6,
            "business_hours_end": 21,
            "require_trusted_device_for_sensitive": False,
            "require_mfa_for_sensitive": False,
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["role_key"] == "student"
    assert payload["row_scope_mode"] == "owner_id"
    assert payload["require_business_hours_for_sensitive"] is False
    assert payload["business_hours_start"] == 6
    assert payload["business_hours_end"] == 21
    assert payload["require_trusted_device_for_sensitive"] is False
    assert payload["require_mfa_for_sensitive"] is False

    list_response = client.get("/admin/policies/row-level")
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    student_item = next(item for item in items if item["role_key"] == "student")
    assert student_item["row_scope_mode"] == "owner_id"


def test_update_row_level_policy_rule_not_found(client: TestClient) -> None:
    response = client.put(
        "/admin/policies/row-level/non-existent-role",
        json={"row_scope_mode": "owner_id"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "ROLE_POLICY_NOT_FOUND"
