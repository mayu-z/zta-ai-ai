from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.agentic.engine.agent_runner import AgentRunner
from app.agentic.engine.node_executor import NodeExecutor
from app.agentic.models.action_config import ActionConfig
from app.agentic.models.agent_context import AgentStatus, ClaimSet, IntentClassification, RequestContext
from app.agentic.models.agent_definition import AgentDefinition


class StaticDefinitionLoader:
    def __init__(self, definition: AgentDefinition | None):
        self._definition = definition

    async def load(self, agent_id, tenant_id):
        del tenant_id
        if self._definition and self._definition.agent_id == agent_id:
            return self._definition
        return None


class StaticActionRegistry:
    def __init__(self, action: ActionConfig | None):
        self._action = action

    async def get(self, action_id, tenant_id):
        del action_id, tenant_id
        return self._action


class StaticPolicy:
    def __init__(self, allowed: bool):
        self._allowed = allowed

    async def evaluate(self, action, ctx):
        del action, ctx
        return type("PolicyDecision", (), {"allowed": self._allowed, "denial_reason": "denied"})()


class StaticScope:
    def __init__(self, row_count: int):
        self._row_count = row_count

    async def fetch_scoped(self, action, ctx, policy_decision=None):
        del action, ctx, policy_decision
        return ClaimSet(
            claims={"amount": 1250},
            field_classifications={"amount": "GENERAL"},
            source_alias="fees",
            fetched_at=datetime.now(UTC).replace(tzinfo=None),
            row_count=self._row_count,
        )


class StaticApprovalLayer:
    def __init__(self, approved: bool):
        self._approved = approved

    async def evaluate(self, action, claim_set, ctx):
        del action, claim_set, ctx
        return type(
            "ApprovalDecision",
            (),
            {
                "approved": self._approved,
                "approver_alias": "APP-1" if self._approved else None,
                "timestamp": datetime.now(UTC).replace(tzinfo=None),
                "cancellation_reason": "confirmation_required" if not self._approved else None,
                "metadata": {"pending": True} if not self._approved else {},
            },
        )()


class RecordingAudit:
    def __init__(self):
        self.events = []

    async def write(self, event):
        self.events.append(event)


def _request_ctx(tenant_id) -> RequestContext:
    return RequestContext(
        tenant_id=tenant_id,
        user_alias="STU-1",
        session_id="sid-1",
        persona="student",
        department_id="CSE",
        jwt_claims={"tenant_id": str(tenant_id)},
    )


def _intent(action_id: str) -> IntentClassification:
    return IntentClassification(
        is_agentic=True,
        action_id=action_id,
        confidence=0.9,
        extracted_entities={},
        raw_intent_text="fee reminder",
    )


def _action(action_id: str, tenant_id) -> ActionConfig:
    return ActionConfig(
        action_id=action_id,
        tenant_id=tenant_id,
        display_name="Fee Reminder",
        description="desc",
        trigger_type="user_query",
        required_data_scope=["fees.own"],
        output_type="notification",
        allowed_personas=["student"],
        requires_confirmation=True,
    )


def _definition(action_id: str) -> AgentDefinition:
    return AgentDefinition.model_validate(
        {
            "agent_id": action_id,
            "display_name": "Fee Reminder",
            "version": "1.0.0",
            "description": "desc",
            "trigger": {"type": "user_query"},
            "intent": {"action_id": action_id},
            "policy": {"allowed_personas": ["student"], "required_data_scope": ["fees.own"]},
            "steps": [
                {"node_id": "validate", "type": "action", "config": {"action_id": action_id}},
                {
                    "node_id": "fetch",
                    "type": "fetch",
                    "config": {"action_id": action_id},
                    "output_key": "fees_data",
                },
                {
                    "node_id": "has_data",
                    "type": "condition",
                    "config": {"expression": "claim_set['fees_data'].row_count > 0"},
                },
                {
                    "node_id": "approve",
                    "type": "approval",
                    "config": {"action_id": action_id, "claim_set_key": "fees_data"},
                },
            ],
            "edges": [
                {"from": "START", "to": "validate"},
                {"from": "validate", "to": "fetch"},
                {"from": "fetch", "to": "has_data"},
                {"from": "has_data", "to": "approve", "condition": "true"},
                {"from": "has_data", "to": "END_NO_DATA", "condition": "false"},
                {"from": "approve", "to": "END_SUCCESS"},
            ],
        }
    )


@pytest.mark.asyncio
async def test_agent_runner_executes_dynamic_graph_and_audits() -> None:
    tenant_id = uuid4()
    action_id = "fee_reminder_v1"
    definition = _definition(action_id)
    audit = RecordingAudit()

    node_executor = NodeExecutor(
        action_registry=StaticActionRegistry(_action(action_id, tenant_id)),
        policy_engine=StaticPolicy(allowed=True),
        scope_guard=StaticScope(row_count=1),
        approval_layer=StaticApprovalLayer(approved=True),
    )
    runner = AgentRunner(
        definition_loader=StaticDefinitionLoader(definition),
        node_executor=node_executor,
        action_registry=StaticActionRegistry(_action(action_id, tenant_id)),
        policy_engine=StaticPolicy(allowed=True),
        audit_logger=audit,
    )

    result = await runner.run(agent_id=action_id, intent=_intent(action_id), ctx=_request_ctx(tenant_id))

    assert result.status == AgentStatus.SUCCESS
    assert result.data is not None
    assert len(result.data["steps_executed"]) == 4
    assert result.data["actions_triggered"] == [action_id]
    assert len(audit.events) == 1
    assert audit.events[0].metadata["terminal_node"] == "END_SUCCESS"


@pytest.mark.asyncio
async def test_agent_runner_fails_on_unknown_node_type() -> None:
    tenant_id = uuid4()
    action_id = "fee_reminder_v1"
    definition = AgentDefinition.model_validate(
        {
            "agent_id": action_id,
            "version": "1.0.0",
            "trigger": {"type": "user_query"},
            "intent": {"action_id": action_id},
            "policy": {"allowed_personas": ["student"], "required_data_scope": ["fees.own"]},
            "steps": [{"node_id": "write", "type": "write", "config": {}}],
            "edges": [{"from": "START", "to": "write"}, {"from": "write", "to": "END_SUCCESS"}],
        }
    )

    node_executor = NodeExecutor(
        action_registry=StaticActionRegistry(_action(action_id, tenant_id)),
        policy_engine=StaticPolicy(allowed=True),
        scope_guard=StaticScope(row_count=1),
        approval_layer=StaticApprovalLayer(approved=True),
    )
    runner = AgentRunner(
        definition_loader=StaticDefinitionLoader(definition),
        node_executor=node_executor,
        action_registry=StaticActionRegistry(_action(action_id, tenant_id)),
        policy_engine=StaticPolicy(allowed=True),
        audit_logger=RecordingAudit(),
    )

    result = await runner.execute_agent(definition, intent=_intent(action_id), ctx=_request_ctx(tenant_id))
    assert result.status == AgentStatus.FAILED
    assert "No handler registered for node type" in result.message


@pytest.mark.asyncio
async def test_agent_runner_fallback_when_definition_missing() -> None:
    tenant_id = uuid4()
    action_id = "fee_reminder_v1"
    runner = AgentRunner(
        definition_loader=StaticDefinitionLoader(None),
        node_executor=NodeExecutor(node_handlers={}),
        action_registry=StaticActionRegistry(_action(action_id, tenant_id)),
        policy_engine=StaticPolicy(allowed=True),
        audit_logger=RecordingAudit(),
    )

    result = await runner.run(agent_id=action_id, intent=_intent(action_id), ctx=_request_ctx(tenant_id))
    assert result.status == AgentStatus.FALLBACK_TO_INFO
