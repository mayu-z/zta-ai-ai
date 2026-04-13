from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from app.agentic.connectors.postgres import PostgresConnector
from app.agentic.models.execution_plan import FilterOperator, QueryFilter, ReadExecutionPlan, ScopeFilter


def _setup_fees_table(sync_url: str, tenant_a: str, tenant_b: str) -> None:
    engine = create_engine(sync_url)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS fees"))
        conn.execute(
            text(
                """
                CREATE TABLE fees (
                    id SERIAL PRIMARY KEY,
                    tenant_id VARCHAR(64) NOT NULL,
                    student_id VARCHAR(64) NOT NULL,
                    amount_due INTEGER NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO fees (tenant_id, student_id, amount_due)
                VALUES
                  (:tenant_a, 'STU-001', 1200),
                  (:tenant_b, 'STU-001', 2200)
                """
            ),
            {"tenant_a": tenant_a, "tenant_b": tenant_b},
        )


@pytest.mark.asyncio
async def test_tenant_isolation_real_postgres() -> None:
    tc = pytest.importorskip("testcontainers.postgres")
    PostgresContainer = tc.PostgresContainer

    tenant_a = str(uuid4())
    tenant_b = str(uuid4())

    with PostgresContainer("postgres:16") as container:
        sync_url = container.get_connection_url()
        _setup_fees_table(sync_url, tenant_a=tenant_a, tenant_b=tenant_b)

        connector = PostgresConnector(tenant_id=uuid4() if False else uuid4(), config={"connection_url": sync_url})
        connector._tenant_id = uuid4()  # reset below with deterministic tenant
        connector._tenant_id = __import__("uuid").UUID(tenant_a)
        await connector.connect()

        plan = ReadExecutionPlan(
            plan_id="iso-1",
            entity="fees",
            fields=["tenant_id", "student_id", "amount_due"],
            filters=[QueryFilter(field="student_id", operator=FilterOperator.EQ, value="STU-001")],
            scope=ScopeFilter(tenant_id=tenant_a, user_alias="STU-001", department_id="CS"),
            limit=100,
        )
        result = await connector.execute(plan)

        assert result.row_count == 1
        assert all(row["tenant_id"] == tenant_a for row in result.rows)
        assert all(row["tenant_id"] != tenant_b for row in result.rows)

        table = await connector._get_table("fees")
        stmt, params = connector._build_select(plan=plan, table=table)
        assert "tenant_id" in str(stmt)
        assert params["tenant_id"] == tenant_a
