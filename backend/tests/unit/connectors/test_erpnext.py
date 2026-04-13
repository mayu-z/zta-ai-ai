from __future__ import annotations

import json
from uuid import uuid4

import httpx
import pytest

from app.agentic.connectors.erpnext import ERPNextConnector
from app.agentic.models.execution_plan import FilterOperator, QueryFilter, ReadExecutionPlan, ScopeFilter


def test_erpnext_filter_translation() -> None:
    connector = ERPNextConnector(
        tenant_id=uuid4(),
        config={"erp_base_url": "https://erp.example.edu", "api_key": "k", "api_secret": "s"},
    )
    translated = connector._translate_filters(
        [
            QueryFilter(field="amount_due", operator=FilterOperator.GT, value=0),
            QueryFilter(field="student_id", operator=FilterOperator.EQ, value="STU-001"),
        ]
    )

    assert translated[0] == ["amount_due", ">", 0]
    assert translated[1] == ["student_id", "=", "STU-001"]


@pytest.mark.asyncio
async def test_erpnext_execute_includes_scope_filters(monkeypatch) -> None:
    captured = {"filters": None}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/resource/Fees"):
            captured["filters"] = request.url.params.get("filters")
            return httpx.Response(200, json={"data": [{"amount_due": 1200}]})
        return httpx.Response(200, json={"message": "pong"})

    transport = httpx.MockTransport(handler)
    connector = ERPNextConnector(
        tenant_id=uuid4(),
        config={
            "erp_base_url": "https://erp.example.edu",
            "api_key": "k",
            "api_secret": "s",
            "entity_mappings": {"fees": "Fees"},
            "tenant_company_name": "UniversityCo",
        },
    )
    connector._client = httpx.AsyncClient(transport=transport, base_url="https://erp.example.edu")
    connector._connected = True

    plan = ReadExecutionPlan(
        plan_id="p-1",
        entity="fees",
        fields=["amount_due"],
        filters=[QueryFilter(field="student_id", operator=FilterOperator.EQ, value="STU-001")],
        scope=ScopeFilter(tenant_id=str(uuid4()), user_alias="STU-001", department_id="CS"),
    )
    connector._tenant_id = uuid4()
    plan = ReadExecutionPlan(
        plan_id=plan.plan_id,
        entity=plan.entity,
        fields=plan.fields,
        filters=plan.filters,
        scope=ScopeFilter(tenant_id=str(connector.tenant_id), user_alias="STU-001", department_id="CS"),
    )

    result = await connector.execute(plan)

    assert result.row_count == 1
    parsed = json.loads(captured["filters"])
    assert ["student_id", "=", "STU-001"] in parsed
    assert ["tenant_id", "=", str(connector.tenant_id)] in parsed
