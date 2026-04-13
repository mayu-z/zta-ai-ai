from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest

from app.agentic.compiler.execution_planner import ExecutionPlanner, WriteFailure
from app.agentic.compiler.scope_injector import ScopeInjector
from app.agentic.compiler.write_guard import WriteGuard
from app.agentic.connectors.base import RawResult, WriteResult
from app.agentic.connectors.claimset_builder import ClaimSetBuilder, MaskingEngine, SchemaRegistry
from app.agentic.core.audit_logger import AuditLogger
from app.agentic.core.policy_engine import PolicyDecision
from app.agentic.models.action_config import ActionConfig
from app.agentic.models.agent_context import RequestContext


class StubRouter:
    def __init__(self):
        self.read_calls = 0
        self.write_calls = 0

    async def route_read(self, plan, tenant_id):
        del tenant_id
        self.read_calls += 1
        return RawResult(
            rows=[{"student_id": "STU-1", "outstanding_balance": 1200}],
            row_count=1,
            execution_time_ms=10,
            source_schema=plan.entity,
        )

    async def route_write(self, plan, tenant_id):
        del tenant_id
        self.write_calls += 1
        return WriteResult(rows_affected=1, generated_id="id-1", execution_time_ms=5)


@pytest.mark.asyncio
async def test_fetch_data_merges_claims() -> None:
    tenant_id = uuid4()
    action = ActionConfig(
        action_id="fee_reminder_v1",
        tenant_id=tenant_id,
        display_name="Fee",
        description="desc",
        trigger_type="user_query",
        required_data_scope=["fees.own"],
        output_type="response",
        allowed_personas=["student"],
        extra_config={"max_rows": 10},
    )
    ctx = RequestContext(
        tenant_id=tenant_id,
        user_alias="STU-1",
        session_id="sid",
        persona="student",
        department_id="CS",
        jwt_claims={},
    )

    router = StubRouter()
    planner = ExecutionPlanner(
        scope_injector=ScopeInjector(),
        connector_router=router,
        claimset_builder=ClaimSetBuilder(SchemaRegistry(), MaskingEngine()),
        write_guard=WriteGuard(),
        audit_logger=AuditLogger(),
    )

    claim_set = await planner.fetch_data(action, ctx, PolicyDecision(allowed=True))

    assert router.read_calls == 1
    assert claim_set.claims["outstanding_balance"] == 1200
    assert claim_set.row_count == 1


@pytest.mark.asyncio
async def test_execute_write_raises_when_no_rows() -> None:
    tenant_id = uuid4()

    class ZeroRowRouter(StubRouter):
        async def route_write(self, plan, tenant_id):
            del plan, tenant_id
            return WriteResult(rows_affected=0, generated_id=None, execution_time_ms=5)

    action = ActionConfig(
        action_id="leave_balance_apply_v1",
        tenant_id=tenant_id,
        display_name="Leave",
        description="desc",
        trigger_type="user_query",
        required_data_scope=["hr.own"],
        output_type="workflow",
        write_target="leave_records:INSERT",
        allowed_personas=["faculty"],
        extra_config={"expected_rows": 1},
    )
    ctx = RequestContext(
        tenant_id=tenant_id,
        user_alias="FAC-1",
        session_id="sid",
        persona="faculty",
        department_id="CS",
        jwt_claims={},
    )

    planner = ExecutionPlanner(
        scope_injector=ScopeInjector(),
        connector_router=ZeroRowRouter(),
        claimset_builder=ClaimSetBuilder(SchemaRegistry(), MaskingEngine()),
        write_guard=WriteGuard(),
        audit_logger=AuditLogger(),
    )

    with pytest.raises(WriteFailure):
        await planner.execute_write(action, payload={"employee_id": "FAC-1"}, ctx=ctx)
