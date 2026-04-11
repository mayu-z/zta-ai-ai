from __future__ import annotations

import base64
import json

import pytest

from app.connectors.external_connectors import ERPNextConnector, GoogleSheetsConnector
from app.connectors.registry import connector_registry
from app.core.exceptions import ValidationError
from app.db.models import DataSource, DataSourceStatus, DataSourceType
from app.schemas.pipeline import CompiledQueryPlan


def _encode_config(payload: dict[str, object]) -> str:
    return base64.b64encode(
        json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    ).decode("utf-8")


def _sample_plan(source_type: str = "google_sheets") -> CompiledQueryPlan:
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
        requires_aggregate=True,
        parameterized_signature="sig:sheets",
    )


def test_registry_returns_google_sheets_connector_with_live_query_support() -> None:
    source = DataSource(
        tenant_id="tenant-1",
        name="Research Sheet",
        source_type=DataSourceType.google_sheets,
        config_encrypted=_encode_config(
            {
                "service_account_json": {"project_id": "demo-project"},
                "spreadsheet_id": "sheet-123",
                "sheet_rows": [
                    {
                        "tenant_id": "tenant-1",
                        "domain": "ops",
                        "entity_type": "records",
                        "claim_key": "record_count",
                        "value_number": 3,
                    },
                    {
                        "tenant_id": "tenant-1",
                        "domain": "ops",
                        "entity_type": "records",
                        "claim_key": "record_count",
                        "value_number": 2,
                    },
                    {
                        "tenant_id": "tenant-2",
                        "domain": "ops",
                        "entity_type": "records",
                        "claim_key": "record_count",
                        "value_number": 99,
                    },
                ],
            }
        ),
        department_scope=[],
        status=DataSourceStatus.connected,
    )

    connector = connector_registry.get(_sample_plan(), source)

    assert isinstance(connector, GoogleSheetsConnector)
    values = connector.execute_query(None, _sample_plan())
    assert values["record_count"] == 5


def test_registry_returns_erpnext_connector_with_live_query_support() -> None:
    source = DataSource(
        tenant_id="tenant-1",
        name="ERP Claims",
        source_type=DataSourceType.erpnext,
        config_encrypted=_encode_config(
            {
                "base_url": "https://erp.example.com",
                "api_key": "key",
                "api_secret": "secret",
                "doctype": "ZTA Claim",
                "seeded_rows": [
                    {
                        "tenant_id": "tenant-1",
                        "domain": "ops",
                        "entity_type": "records",
                        "claim_key": "record_count",
                        "value_number": 2,
                    },
                    {
                        "tenant_id": "tenant-1",
                        "domain": "ops",
                        "entity_type": "records",
                        "claim_key": "record_count",
                        "value_number": 8,
                    },
                    {
                        "tenant_id": "tenant-2",
                        "domain": "ops",
                        "entity_type": "records",
                        "claim_key": "record_count",
                        "value_number": 77,
                    },
                ],
            }
        ),
        department_scope=[],
        status=DataSourceStatus.connected,
    )
    plan = _sample_plan("erpnext").model_copy(update={"requires_aggregate": True})

    connector = connector_registry.get(plan, source)

    assert isinstance(connector, ERPNextConnector)
    values = connector.execute_query(None, plan)
    assert values["record_count"] == 10


def test_registry_rejects_google_sheets_without_spreadsheet_id() -> None:
    source = DataSource(
        tenant_id="tenant-1",
        name="Broken Research Sheet",
        source_type=DataSourceType.google_sheets,
        config_encrypted=_encode_config(
            {
                "service_account_json": {"project_id": "demo-project"},
                "sheet_rows": [],
            }
        ),
        department_scope=[],
        status=DataSourceStatus.connected,
    )

    with pytest.raises(ValidationError) as exc:
        connector_registry.get(_sample_plan(), source)

    assert exc.value.code == "SOURCE_CONFIG_INVALID"


def test_registry_rejects_erpnext_missing_required_config() -> None:
    source = DataSource(
        tenant_id="tenant-1",
        name="Broken ERP",
        source_type=DataSourceType.erpnext,
        config_encrypted=_encode_config(
            {
                "base_url": "https://erp.example.com",
                "api_key": "",
                "seeded_rows": [],
            }
        ),
        department_scope=[],
        status=DataSourceStatus.connected,
    )

    with pytest.raises(ValidationError) as exc:
        connector_registry.get(_sample_plan("erpnext"), source)

    assert exc.value.code == "SOURCE_CONFIG_INVALID"
