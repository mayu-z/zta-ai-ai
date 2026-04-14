from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.agentic.models.action_config import ActionConfig
from app.agentic.models.agent_context import AgentResult, AgentStatus, IntentClassification
from app.agentic.runtime_bridge import AgenticRuntimeBridge
from app.core.exceptions import AuthorizationError
from app.schemas.pipeline import ScopeContext


class StaticClassifier:
    def __init__(self, classification: IntentClassification):
        self._classification = classification

    async def classify(self, query_text: str) -> IntentClassification:
        del query_text
        return self._classification


class StaticRegistry:
    def __init__(self, action: ActionConfig | None):
        self._action = action

    async def get(self, action_id: str, tenant_id):
        del action_id, tenant_id
        return self._action


class StaticRunner:
    def __init__(self, result: AgentResult):
        self._result = result

    async def run(self, agent_id: str, intent: IntentClassification, ctx):
        del agent_id, intent, ctx
        return self._result


def _scope(tenant_id: str) -> ScopeContext:
    return ScopeContext(
        tenant_id=tenant_id,
        user_id="u-1",
        email="u1@example.edu",
        name="Student 1",
        persona_type="student",
        department="CSE",
        external_id="STU-1",
        role_key="student",
        session_id="sid-1",
    )


def _classification(action_id: str) -> IntentClassification:
    return IntentClassification(
        is_agentic=True,
        action_id=action_id,
        confidence=0.92,
        extracted_entities={},
        raw_intent_text="send fee reminder",
    )


def _action(action_id: str, tenant_id) -> ActionConfig:
    return ActionConfig(
        action_id=action_id,
        tenant_id=tenant_id,
        display_name="Fee Reminder",
        description="desc",
        trigger_type="user_query",
        required_data_scope=["fees.own", "finance.own"],
        output_type="notification",
        allowed_personas=["student"],
    )


def _bridge(monkeypatch, *, classification: IntentClassification, action: ActionConfig | None, result: AgentResult):
    monkeypatch.setattr(AgenticRuntimeBridge, "_run_async", staticmethod(lambda coro: asyncio.run(coro)))
    bridge = object.__new__(AgenticRuntimeBridge)
    bridge._classifier = StaticClassifier(classification)
    bridge._registry = StaticRegistry(action)
    bridge._runner = StaticRunner(result)
    return bridge


def test_runtime_bridge_maps_pending_approval_to_confirmation_required(monkeypatch) -> None:
    tenant_uuid = uuid4()
    action_id = "fee_reminder_v1"
    bridge = _bridge(
        monkeypatch,
        classification=_classification(action_id),
        action=_action(action_id, tenant_uuid),
        result=AgentResult(status=AgentStatus.PENDING_APPROVAL, message="Approval required"),
    )

    outcome = bridge.maybe_execute(query_text="Send fee reminder", scope=_scope(str(tenant_uuid)))

    assert outcome is not None
    assert outcome.was_blocked is True
    assert outcome.block_reason == "CONFIRMATION_REQUIRED"


def test_runtime_bridge_raises_authorization_on_permission_denied(monkeypatch) -> None:
    tenant_uuid = uuid4()
    action_id = "fee_reminder_v1"
    bridge = _bridge(
        monkeypatch,
        classification=_classification(action_id),
        action=_action(action_id, tenant_uuid),
        result=AgentResult(status=AgentStatus.PERMISSION_DENIED, message="Denied"),
    )

    with pytest.raises(AuthorizationError, match="Denied"):
        bridge.maybe_execute(query_text="Send fee reminder", scope=_scope(str(tenant_uuid)))
