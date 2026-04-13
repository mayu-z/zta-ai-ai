from __future__ import annotations

from datetime import UTC, datetime
import asyncio
from uuid import uuid4

import pytest

from app.agentic.agents.payroll_query import PayrollQueryAgent
from app.agentic.compiler.execution_planner import ExecutionPlanner
from app.agentic.compiler.scope_injector import ScopeInjector
from app.agentic.compiler.write_guard import WriteGuard
from app.agentic.connectors.base import ConnectorTimeoutError, RawResult
from app.agentic.connectors.claimset_builder import ClaimSetBuilder, FieldSchema, MaskingEngine, SchemaRegistry
from app.agentic.core.approval_layer import ApprovalDecision
from app.agentic.core.audit_logger import AuditLogger
from app.agentic.core.compiler_interface import CompilerInterface, ExecutionPlan
from app.agentic.core.notification_dispatcher import NotificationDispatcher
from app.agentic.core.policy_engine import PolicyDecision
from app.agentic.core.scope_guard import ScopeGuard
from app.agentic.models.action_config import ActionConfig
from app.agentic.models.agent_context import AgentStatus, ClaimSet, IntentClassification, RequestContext


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class StaticRegistry:
    def __init__(self, action: ActionConfig):
        self._action = action

    async def get(self, action_id, tenant_id):
        del action_id, tenant_id
        return self._action


class StaticPolicy:
    async def evaluate(self, action, ctx):
        del action, ctx
        return PolicyDecision(allowed=True)


class StaticApproval:
    async def evaluate(self, action, claim_set, ctx):
        del action, claim_set
        return ApprovalDecision(approved=True, approver_alias=ctx.user_alias, timestamp=_utcnow_naive())


class CaptureMonitor:
    def __init__(self):
        self.events = []

    async def emit(self, event):
        self.events.append(event)
        return None


class TimeoutRouter:
    async def route_read(self, plan, tenant_id):
        del plan, tenant_id
        raise ConnectorTimeoutError("timeout")

    async def route_write(self, plan, tenant_id):
        del plan, tenant_id
        raise ConnectorTimeoutError("timeout")


class StaticPlanner:
    async def build_plan(self, action, claim_set, approval, ctx):
        del claim_set, approval, ctx
        return ExecutionPlan(
            action_id=action.action_id,
            steps=["prepare_response"],
            write_target=action.write_target,
            payload={},
            metadata={},
        )


@pytest.mark.asyncio
async def test_agent_returns_graceful_error_on_connector_timeout() -> None:
    tenant_id = uuid4()
    action = ActionConfig(
        action_id="payroll_query_v1",
        tenant_id=tenant_id,
        display_name="Payroll",
        description="desc",
        trigger_type="user_query",
        required_data_scope=["payroll.own"],
        output_type="response",
        allowed_personas=["faculty"],
        has_sensitive_fields=True,
        requires_confirmation=False,
    )

    planner = ExecutionPlanner(
        scope_injector=ScopeInjector(),
        connector_router=TimeoutRouter(),
        claimset_builder=ClaimSetBuilder(SchemaRegistry(), MaskingEngine()),
        write_guard=WriteGuard(),
        audit_logger=AuditLogger(),
    )
    compiler = CompilerInterface(planner=planner)
    monitor = CaptureMonitor()

    agent = PayrollQueryAgent(
        action_registry=StaticRegistry(action),
        policy_engine=StaticPolicy(),
        scope_guard=ScopeGuard(compiler=compiler),
        compiler=compiler,
        audit_logger=AuditLogger(),
        sensitive_monitor=monitor,
        notification_dispatcher=NotificationDispatcher(),
        approval_layer=StaticApproval(),
    )

    result = await agent.run(
        IntentClassification(
            is_agentic=True,
            action_id="payroll_query_v1",
            confidence=0.9,
            extracted_entities={},
            raw_intent_text="show payroll",
        ),
        RequestContext(
            tenant_id=tenant_id,
            user_alias="FAC-1",
            session_id="sid",
            persona="faculty",
            department_id="CS",
            jwt_claims={},
        ),
    )

    assert result.status == AgentStatus.FAILED
    assert "Execution error" in result.message


def test_claimset_builder_tokenises_raw_identifiers() -> None:
    tenant_id = uuid4()
    registry = SchemaRegistry()
    registry.register(
        tenant_id=tenant_id,
        entity="payroll",
        fields={
            "employee_id": FieldSchema(raw_name="employee_id", alias="employee_id", classification="IDENTIFIER"),
            "salary": FieldSchema(raw_name="salary", alias="salary", classification="SENSITIVE"),
        },
    )

    builder = ClaimSetBuilder(registry, MaskingEngine())
    claim_set = builder.build(
        RawResult(
            rows=[{"employee_id": 42, "salary": 1000}],
            row_count=1,
            execution_time_ms=1,
            source_schema="payroll",
        ),
        entity="payroll",
        tenant_id=tenant_id,
        policy_decision=PolicyDecision(allowed=True),
    )

    assert str(claim_set.claims["employee_id"]).startswith("TKN-")


@pytest.mark.asyncio
async def test_sensitive_classifications_are_forwarded_from_claimset() -> None:
    tenant_id = uuid4()
    action = ActionConfig(
        action_id="payroll_query_v1",
        tenant_id=tenant_id,
        display_name="Payroll",
        description="desc",
        trigger_type="user_query",
        required_data_scope=["payroll.own"],
        output_type="response",
        allowed_personas=["faculty"],
        has_sensitive_fields=True,
        requires_confirmation=False,
    )

    monitor = CaptureMonitor()

    class StaticScope:
        async def fetch_scoped(self, action, ctx, policy_decision=None):
            del action, ctx, policy_decision
            return ClaimSet(
                claims={"salary": 1000},
                field_classifications={"salary": "SENSITIVE"},
                source_alias="payroll",
                fetched_at=_utcnow_naive(),
                row_count=1,
            )

    agent = PayrollQueryAgent(
        action_registry=StaticRegistry(action),
        policy_engine=StaticPolicy(),
        scope_guard=StaticScope(),
        compiler=CompilerInterface(planner=StaticPlanner()),
        audit_logger=AuditLogger(),
        sensitive_monitor=monitor,
        notification_dispatcher=NotificationDispatcher(),
        approval_layer=StaticApproval(),
    )

    result = await agent.run(
        IntentClassification(
            is_agentic=True,
            action_id="payroll_query_v1",
            confidence=0.9,
            extracted_entities={},
            raw_intent_text="payroll",
        ),
        RequestContext(
            tenant_id=tenant_id,
            user_alias="FAC-1",
            session_id="sid",
            persona="faculty",
            department_id="CS",
            jwt_claims={},
        ),
    )
    await asyncio.sleep(0)

    assert result.status == AgentStatus.SUCCESS
    assert monitor.events
    assert monitor.events[0].field_classifications.get("salary") == "SENSITIVE"
