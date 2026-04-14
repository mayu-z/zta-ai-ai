from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.agentic.engine.node_types.action_handler import ActionNodeHandler
from app.agentic.engine.node_types.approval_handler import ApprovalNodeHandler
from app.agentic.engine.node_types.fetch_handler import FetchNodeHandler
from app.agentic.models.action_config import ActionConfig
from app.agentic.models.agent_context import AgentStatus, ClaimSet, IntentClassification, RequestContext
from app.agentic.models.agent_definition import AgentDefinition, ExecutionContext, NodeDefinition, NodeTypeEnum


class StaticRegistry:
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
    async def fetch_scoped(self, action, ctx, policy_decision=None):
        del action, ctx, policy_decision
        return ClaimSet(
            claims={"tenant_id": str(uuid4()), "value": 1},
            field_classifications={"value": "GENERAL"},
            source_alias="mock",
            fetched_at=datetime.now(UTC).replace(tzinfo=None),
            row_count=1,
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


def _definition() -> AgentDefinition:
    return AgentDefinition.model_validate(
        {
            "agent_id": "fee_reminder_v1",
            "display_name": "Fee",
            "version": "1.0.0",
            "description": "desc",
            "trigger": {"type": "user_query"},
            "intent": {"action_id": "fee_reminder_v1"},
            "policy": {"allowed_personas": ["student"], "required_data_scope": ["fees.own"]},
            "steps": [
                {"node_id": "validate", "type": "action", "config": {"action_id": "fee_reminder_v1"}}
            ],
            "edges": [{"from": "START", "to": "validate"}, {"from": "validate", "to": "END_SUCCESS"}],
        }
    )


def _ctx(definition: AgentDefinition, tenant_id) -> ExecutionContext:
    return ExecutionContext(
        intent=IntentClassification(
            is_agentic=True,
            action_id=definition.agent_id,
            confidence=0.9,
            extracted_entities={},
            raw_intent_text="fees",
        ),
        ctx=RequestContext(
            tenant_id=tenant_id,
            user_alias="STU-1",
            session_id="sid",
            persona="student",
            department_id="CS",
            jwt_claims={"tenant_id": str(tenant_id)},
        ),
        definition=definition,
    )


@pytest.mark.asyncio
async def test_action_handler_validates_registry_action() -> None:
    tenant_id = uuid4()
    action = ActionConfig(
        action_id="fee_reminder_v1",
        tenant_id=tenant_id,
        display_name="Fee",
        description="desc",
        trigger_type="user_query",
        required_data_scope=["fees.own"],
        output_type="notification",
        allowed_personas=["student"],
    )
    handler = ActionNodeHandler(action_registry=StaticRegistry(action))
    node = NodeDefinition(node_id="validate", type=NodeTypeEnum.ACTION, config={"action_id": action.action_id})

    result = await handler.execute(node, _ctx(_definition(), tenant_id))
    assert result.should_halt is False
    assert result.output["action_id"] == "fee_reminder_v1"


@pytest.mark.asyncio
async def test_fetch_handler_applies_policy_gate() -> None:
    tenant_id = uuid4()
    action = ActionConfig(
        action_id="fee_reminder_v1",
        tenant_id=tenant_id,
        display_name="Fee",
        description="desc",
        trigger_type="user_query",
        required_data_scope=["fees.own"],
        output_type="notification",
        allowed_personas=["student"],
    )
    handler = FetchNodeHandler(
        action_registry=StaticRegistry(action),
        policy_engine=StaticPolicy(allowed=False),
        scope_guard=StaticScope(),
    )
    node = NodeDefinition(node_id="fetch", type=NodeTypeEnum.FETCH, config={"action_id": action.action_id})

    result = await handler.execute(node, _ctx(_definition(), tenant_id))
    assert result.should_halt is True
    assert result.halt_status == AgentStatus.PERMISSION_DENIED


@pytest.mark.asyncio
async def test_approval_handler_halts_when_pending() -> None:
    tenant_id = uuid4()
    action = ActionConfig(
        action_id="email_send_v1",
        tenant_id=tenant_id,
        display_name="Email Send",
        description="desc",
        trigger_type="user_query",
        required_data_scope=["user_profile.own"],
        output_type="email",
        allowed_personas=["student"],
        requires_confirmation=True,
    )
    handler = ApprovalNodeHandler(
        action_registry=StaticRegistry(action),
        approval_layer=StaticApprovalLayer(approved=False),
    )
    node = NodeDefinition(node_id="approve", type=NodeTypeEnum.APPROVAL, config={"action_id": action.action_id})

    result = await handler.execute(node, _ctx(_definition(), tenant_id))
    assert result.should_halt is True
    assert result.halt_status == AgentStatus.PENDING_APPROVAL
