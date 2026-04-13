from __future__ import annotations

from uuid import uuid4

import pytest

from app.agentic.connectors.base import MissingScopeFilter
from app.agentic.connectors.postgres import PostgresConnector
from app.agentic.models.execution_plan import ReadExecutionPlan, ScopeFilter


@pytest.mark.asyncio
async def test_missing_scope_filter_raises_before_real_query() -> None:
    tc = pytest.importorskip("testcontainers.postgres")
    PostgresContainer = tc.PostgresContainer

    with PostgresContainer("postgres:16") as container:
        connector = PostgresConnector(tenant_id=uuid4(), config={"connection_url": container.get_connection_url()})
        connector._connected = True

        plan = ReadExecutionPlan(
            plan_id="scope-1",
            entity="fees",
            fields=["tenant_id"],
            filters=[],
            scope=ScopeFilter(tenant_id="", user_alias="STU-1", department_id="CS"),
            limit=10,
        )

        with pytest.raises(MissingScopeFilter):
            await connector.execute(plan)
