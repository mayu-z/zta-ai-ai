from __future__ import annotations

from uuid import uuid4

import pytest

from app.agentic.connectors.calendar import MockCalendarConnector
from app.agentic.models.execution_plan import ReadExecutionPlan, ScopeFilter


@pytest.mark.asyncio
async def test_calendar_free_busy_only_output() -> None:
    connector = MockCalendarConnector(tenant_id=uuid4(), config={})
    await connector.connect()

    plan = ReadExecutionPlan(
        plan_id="cal-1",
        entity="calendar",
        fields=[],
        filters=[],
        scope=ScopeFilter(tenant_id=str(connector.tenant_id), user_alias="FAC-1", department_id="CS"),
        operation="free_busy",
        payload={
            "user_aliases": ["FAC-1", "STU-1"],
            "start": "2026-04-15T09:00:00Z",
            "end": "2026-04-15T17:00:00Z",
        },
        limit=10,
    )

    result = await connector.execute(plan)

    assert result.row_count == 2
    for row in result.rows:
        assert set(row.keys()) == {"user_alias", "busy_start", "busy_end"}
        assert "title" not in row
        assert "description" not in row
        assert "attendees" not in row
