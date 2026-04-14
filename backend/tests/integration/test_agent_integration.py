from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.agentic.compiler.execution_planner import ExecutionPlanner
from app.agentic.compiler.scope_injector import ScopeInjector
from app.agentic.compiler.write_guard import WriteGuard
from app.agentic.connectors.base import ConnectorTimeoutError, RawResult
from app.agentic.connectors.claimset_builder import ClaimSetBuilder, FieldSchema, MaskingEngine, SchemaRegistry
from app.agentic.core.approval_layer import ApprovalDecision
from app.agentic.core.audit_logger import AuditLogger
from app.agentic.core.compiler_interface import CompilerInterface
from app.agentic.core.policy_engine import PolicyDecision
from app.agentic.core.scope_guard import ScopeGuard
from app.agentic.engine.agent_runner import AgentRunner
from app.agentic.engine.node_executor import NodeExecutor
from app.agentic.models.action_config import ActionConfig
from app.agentic.models.agent_context import AgentStatus, ClaimSet, IntentClassification, RequestContext
from app.agentic.models.agent_definition import AgentDefinition


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


class StaticDefinitionLoader:
    def __init__(self, definition: AgentDefinition):
        self._definition = definition

    async def load(self, agent_id, tenant_id):
        del tenant_id
        if agent_id == self._definition.agent_id:
            return self._definition
        return None


class TimeoutRouter:
    async def route_read(self, plan, tenant_id):
        del plan, tenant_id
        raise ConnectorTimeoutError("timeout")

    async def route_write(self, plan, tenant_id):
        del plan, tenant_id
        raise ConnectorTimeoutError("timeout")


def _definition(action_id: str, expression: str | None = None) -> AgentDefinition:
    steps: list[dict[str, object]] = [
        {"node_id": "validate_action", "type": "action", "config": {"action_id": action_id}},
        {
            "node_id": "fetch_scope",
            "type": "fetch",
            "config": {"action_id": action_id},
            "output_key": "payroll_data",
        },
    ]
    edges: list[dict[str, object]] = [
        {"from": "START", "to": "validate_action"},
        {"from": "validate_action", "to": "fetch_scope"},
    ]

    if expression:
        steps.append({"node_id": "verify_claims", "type": "condition", "config": {"expression": expression}})
        edges.append({"from": "fetch_scope", "to": "verify_claims"})
        edges.append({"from": "verify_claims", "to": "END_SUCCESS", "condition": "true"})
        edges.append({"from": "verify_claims", "to": "END_FAILED", "condition": "false"})
    else:
        edges.append({"from": "fetch_scope", "to": "END_SUCCESS"})

    return AgentDefinition.model_validate(
        {
            "agent_id": action_id,
            "display_name": "Payroll Query",
            "version": "1.0.0",
            "description": "dynamic agent test",
            "trigger": {"type": "user_query"},
            "intent": {"action_id": action_id},
            "policy": {"allowed_personas": ["faculty"], "required_data_scope": ["payroll.own"]},
            "steps": steps,
            "edges": edges,
        }
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
    registry = StaticRegistry(action)
    runner = AgentRunner(
        definition_loader=StaticDefinitionLoader(_definition(action.action_id)),
        node_executor=NodeExecutor(
            action_registry=registry,
            policy_engine=StaticPolicy(),
            scope_guard=ScopeGuard(compiler=compiler),
            approval_layer=StaticApproval(),
        ),
        action_registry=registry,
        policy_engine=StaticPolicy(),
        audit_logger=AuditLogger(),
    )

    result = await runner.run(
        agent_id=action.action_id,
        intent=IntentClassification(
            is_agentic=True,
            action_id="payroll_query_v1",
            confidence=0.9,
            extracted_entities={},
            raw_intent_text="show payroll",
        ),
        ctx=RequestContext(
            tenant_id=tenant_id,
            user_alias="FAC-1",
            session_id="sid",
            persona="faculty",
            department_id="CS",
            jwt_claims={},
        ),
    )

    assert result.status == AgentStatus.FAILED
    assert "ConnectorTimeoutError" in result.message


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

    registry = StaticRegistry(action)
    runner = AgentRunner(
        definition_loader=StaticDefinitionLoader(
            _definition(action.action_id, expression="payroll_data.field_classifications.salary == 'SENSITIVE'")
        ),
        node_executor=NodeExecutor(
            action_registry=registry,
            policy_engine=StaticPolicy(),
            scope_guard=StaticScope(),
            approval_layer=StaticApproval(),
        ),
        action_registry=registry,
        policy_engine=StaticPolicy(),
        audit_logger=AuditLogger(),
    )

    result = await runner.run(
        agent_id=action.action_id,
        intent=IntentClassification(
            is_agentic=True,
            action_id="payroll_query_v1",
            confidence=0.9,
            extracted_entities={},
            raw_intent_text="payroll",
        ),
        ctx=RequestContext(
            tenant_id=tenant_id,
            user_alias="FAC-1",
            session_id="sid",
            persona="faculty",
            department_id="CS",
            jwt_claims={},
        ),
    )

    assert result.status == AgentStatus.SUCCESS
    assert result.data is not None
    assert len(result.data.get("steps_executed", [])) == 3
