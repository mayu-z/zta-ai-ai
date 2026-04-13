from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table

from app.agentic.connectors.base import HealthStatus, MissingScopeFilter, QueryInjectionAttempt
from app.agentic.connectors.postgres import PostgresConnector
from app.agentic.models.execution_plan import FilterOperator, QueryFilter, ReadExecutionPlan, ScopeFilter


@pytest.mark.asyncio
async def test_scope_filter_enforcement_before_query(monkeypatch) -> None:
    connector = PostgresConnector(tenant_id=uuid4(), config={"connection_url": "postgresql://x:y@localhost/db"})
    connector._connected = True

    called = {"table": False}

    async def _fail_get_table(entity):
        del entity
        called["table"] = True
        raise AssertionError("_get_table must not be called when scope is invalid")

    monkeypatch.setattr(connector, "_get_table", _fail_get_table)

    plan = ReadExecutionPlan(
        plan_id="p1",
        entity="fees",
        fields=[],
        filters=[],
        scope=ScopeFilter(tenant_id="", user_alias="STU-1", department_id="CS"),
    )

    with pytest.raises(MissingScopeFilter):
        await connector.execute(plan)
    assert called["table"] is False


@pytest.mark.asyncio
async def test_query_injection_prevention_before_query(monkeypatch) -> None:
    tenant_id = uuid4()
    connector = PostgresConnector(tenant_id=tenant_id, config={"connection_url": "postgresql://x:y@localhost/db"})
    connector._connected = True

    called = {"table": False}

    async def _fail_get_table(entity):
        del entity
        called["table"] = True
        raise AssertionError("_get_table must not be called for injection attempts")

    monkeypatch.setattr(connector, "_get_table", _fail_get_table)

    plan = ReadExecutionPlan(
        plan_id="p2",
        entity="fees",
        fields=[],
        filters=[
            QueryFilter(
                field="student_id",
                operator=FilterOperator.EQ,
                value="'; DROP TABLE fees; --",
            )
        ],
        scope=ScopeFilter(tenant_id=str(tenant_id), user_alias="STU-1", department_id="CS"),
    )

    with pytest.raises(QueryInjectionAttempt):
        await connector.execute(plan)
    assert called["table"] is False


def test_build_select_always_contains_tenant_filter() -> None:
    tenant_id = uuid4()
    connector = PostgresConnector(tenant_id=tenant_id, config={"connection_url": "postgresql://x:y@localhost/db"})

    metadata = MetaData()
    table = Table(
        "fees",
        metadata,
        Column("tenant_id", String),
        Column("student_id", String),
        Column("amount_due", Integer),
    )
    plan = ReadExecutionPlan(
        plan_id="p3",
        entity="fees",
        fields=["amount_due"],
        filters=[QueryFilter(field="student_id", operator=FilterOperator.EQ, value="STU-1")],
        scope=ScopeFilter(tenant_id=str(tenant_id), user_alias="STU-1", department_id="CS"),
    )

    stmt, params = connector._build_select(plan=plan, table=table)
    sql = str(stmt)

    assert "tenant_id" in sql
    assert params["tenant_id"] == str(tenant_id)


@pytest.mark.asyncio
async def test_health_check_down_on_ping_failure(monkeypatch) -> None:
    connector = PostgresConnector(tenant_id=uuid4(), config={"connection_url": "postgresql://x:y@localhost/db"})

    async def _fail_ping():
        raise RuntimeError("db down")

    monkeypatch.setattr(connector, "_ping", _fail_ping)
    health = await connector.health_check()

    assert health.status == HealthStatus.DOWN
    assert health.error is not None
