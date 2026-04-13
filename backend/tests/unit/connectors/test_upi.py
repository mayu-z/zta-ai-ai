from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.agentic.connectors.base import MissingScopeFilter
from app.agentic.connectors.upi import UPIGatewayConnector
from app.agentic.models.execution_plan import ScopeFilter, WriteExecutionPlan


@pytest.mark.asyncio
async def test_upi_scope_double_enforcement_blocks_mismatch() -> None:
    call_count = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        call_count["count"] += 1
        return httpx.Response(200, json={"id": "ord_1"})

    connector = UPIGatewayConnector(
        tenant_id=uuid4(),
        config={"payment_gateway_type": "razorpay", "gateway_credentials": {"api_key": "k", "api_secret": "s"}},
    )
    connector._connected = True
    connector._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    plan = WriteExecutionPlan(
        plan_id="upi-1",
        entity="payment_order",
        operation="create_link",
        payload={
            "amount_paise": 300000,
            "order_id": "ZTA-1",
            "description": "Fee",
            "customer_alias": "STU-002",
            "expiry_seconds": 1800,
        },
        scope=ScopeFilter(tenant_id=str(connector.tenant_id), user_alias="STU-001", department_id="CS"),
    )

    with pytest.raises(MissingScopeFilter):
        await connector.write(plan)

    assert call_count["count"] == 0
