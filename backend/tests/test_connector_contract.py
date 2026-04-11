from __future__ import annotations

import pytest

from app.connectors.base import CONNECTOR_ERROR_CODES
from app.connectors.external_connectors import ERPNextConnector, GoogleSheetsConnector
from app.connectors.mock_claims import mock_claims_connector
from app.connectors.sql_connector import SQLConnector
from app.core.exceptions import ValidationError
from app.schemas.pipeline import CompiledQueryPlan


def _sample_plan(source_type: str) -> CompiledQueryPlan:
    return CompiledQueryPlan(
        tenant_id="tenant-1",
        source_type=source_type,
        domain="ops",
        entity_type="records",
        select_keys=["record_count"],
        filters={
            "tenant_id": "tenant-1",
            "domain": "ops",
            "entity_type": "records",
        },
        slot_map={"SLOT_1": "record_count"},
        parameterized_signature="sig:v1",
    )


def test_connector_error_codes_contract_is_complete() -> None:
    expected = {
        "SUCCESS",
        "CLIENT_ERROR",
        "AUTHENTICATION_ERROR",
        "AUTHORIZATION_ERROR",
        "NOT_FOUND",
        "RATE_LIMITED",
        "SERVER_ERROR",
        "TIMEOUT",
    }

    assert expected.issubset(set(CONNECTOR_ERROR_CODES.keys()))


def test_mock_connector_supports_health_and_connection_contract() -> None:
    connection = mock_claims_connector.connect()
    test_result = mock_claims_connector.test_connection()
    health = mock_claims_connector.health_check()
    info = mock_claims_connector.get_connection_info()

    assert connection.status == "connected"
    assert test_result.status == "healthy"
    assert health.status == "healthy"
    assert info.connector_id == "mock_claims"


def test_sql_connector_supports_connection_contract() -> None:
    connector = SQLConnector(connection_url="sqlite+pysqlite:///:memory:")

    connection = connector.connect()
    test_result = connector.test_connection()
    info = connector.get_connection_info()

    assert connection.status == "connected"
    assert test_result.status == "healthy"
    assert info.source_type == "sqlite"


def test_erp_connector_executes_scoped_query() -> None:
    erp_connector = ERPNextConnector(
        base_url="https://erp.example.com",
        api_key="key",
        api_secret="secret",
        seeded_rows=[
            {
                "tenant_id": "tenant-1",
                "domain": "ops",
                "entity_type": "records",
                "claim_key": "record_count",
                "value_number": 4,
            },
            {
                "tenant_id": "tenant-1",
                "domain": "ops",
                "entity_type": "records",
                "claim_key": "record_count",
                "value_number": 6,
            },
            {
                "tenant_id": "tenant-2",
                "domain": "ops",
                "entity_type": "records",
                "claim_key": "record_count",
                "value_number": 999,
            },
        ],
    )
    plan = _sample_plan("erpnext").model_copy(update={"requires_aggregate": True})

    values = erp_connector.execute_query(None, plan)

    assert values["record_count"] == 10


def test_google_sheets_connector_executes_scoped_query() -> None:
    sheets_connector = GoogleSheetsConnector(
        service_account_json={"project_id": "demo"},
        spreadsheet_id="sheet-123",
        sheet_rows=[
            {
                "tenant_id": "tenant-1",
                "domain": "ops",
                "entity_type": "records",
                "claim_key": "record_count",
                "owner_id": "owner-1",
                "value_number": 5,
            },
            {
                "tenant_id": "tenant-1",
                "domain": "ops",
                "entity_type": "records",
                "claim_key": "record_count",
                "owner_id": "owner-1",
                "value_number": 7,
            },
            {
                "tenant_id": "tenant-1",
                "domain": "ops",
                "entity_type": "records",
                "claim_key": "record_count",
                "owner_id": "owner-2",
                "value_number": 999,
            },
        ],
    )
    plan = CompiledQueryPlan(
        tenant_id="tenant-1",
        source_type="google_sheets",
        domain="ops",
        entity_type="records",
        select_keys=["record_count"],
        filters={
            "tenant_id": "tenant-1",
            "domain": "ops",
            "entity_type": "records",
            "owner_id": "owner-1",
        },
        requires_aggregate=True,
        parameterized_signature="sig:sheets",
    )

    values = sheets_connector.execute_query(None, plan)

    assert values["record_count"] == 12


def test_google_sheets_connector_requires_spreadsheet_id() -> None:
    with pytest.raises(ValidationError) as exc:
        GoogleSheetsConnector(
            service_account_json={"project_id": "demo"},
            spreadsheet_id="",
        )

    assert exc.value.code == "SOURCE_CONFIG_INVALID"


def test_connector_contract_validates_timeout_arguments() -> None:
    with pytest.raises(ValidationError):
        mock_claims_connector.connect(timeout_seconds=0)

    with pytest.raises(ValidationError):
        SQLConnector(connection_url="sqlite+pysqlite:///:memory:").connect(
            timeout_seconds=0
        )
