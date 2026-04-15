from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from app.agents.base_handler import AgentResult, BaseAgentHandler
from app.agents.executor import AgentExecutor


class DummyHandler(BaseAgentHandler):
    def __init__(self, result: AgentResult) -> None:
        self._result = result
        self.execute_calls = 0

    @property
    def is_side_effect(self) -> bool:
        return False

    async def execute(self, ctx):
        _ = ctx
        self.execute_calls += 1
        return self._result

    async def rollback(self, ctx, partial_result):
        _ = (ctx, partial_result)

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        _ = config
        return []


class FakeDB:
    def __init__(self, template: Any) -> None:
        self.template = template
        self.added: list[Any] = []
        self.commit_calls = 0

    def get(self, model: Any, key: Any) -> Any:
        _ = (model, key)
        return self.template

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        self.commit_calls += 1


class FakeLoader:
    def __init__(self, instance: Any, handler: BaseAgentHandler, dependencies_active: bool = True) -> None:
        self.instance = instance
        self.handler = handler
        self.dependencies_active = dependencies_active

    async def get_instance_for_template(self, tenant_id: str, template_id: str):
        _ = tenant_id
        if template_id == "sensitive_field_monitor_v1" and not self.dependencies_active:
            return None
        return self.instance

    def instantiate_handler_by_class(self, handler_class: str) -> BaseAgentHandler:
        _ = handler_class
        return self.handler


@pytest.mark.asyncio
async def test_executor_returns_pending_confirmation_for_side_effect() -> None:
    template = SimpleNamespace(
        agent_definition_id=uuid.uuid4(),
        template_id="upi_payment_v1",
        name="UPI Payment",
        is_active=True,
        allowed_personas=["student"],
        trigger_config={},
        handler_class="UpiPaymentHandler",
        is_side_effect=True,
        requires_confirmation=False,
        confirmation_prompt="Confirm UPI link generation?",
    )
    instance = SimpleNamespace(
        id=uuid.uuid4(),
        agent_definition_id=template.agent_definition_id,
        is_enabled=True,
        config={},
        trigger_count=0,
        last_triggered_at=None,
    )
    handler = DummyHandler(result=AgentResult(status="success", output={"message": "ok"}))
    db = FakeDB(template=template)
    loader = FakeLoader(instance=instance, handler=handler)
    executor = AgentExecutor(db_session=db, loader=loader)

    result = await executor.execute_action(
        tenant_id="00000000-0000-0000-0000-000000000001",
        template_id="upi_payment_v1",
        user_id="student-1",
        user_persona="student",
        trigger_payload={"triggered_by": "api_execute", "query": "pay fees"},
        claim_set={},
        confirmed=False,
    )

    assert result.status == "pending_confirmation"
    assert result.requires_confirmation is True
    assert handler.execute_calls == 0
    assert db.commit_calls == 1
    assert result.output.get("action_id")


@pytest.mark.asyncio
async def test_executor_executes_read_only_handler() -> None:
    template = SimpleNamespace(
        agent_definition_id=uuid.uuid4(),
        template_id="leave_balance_v1",
        name="Leave Balance",
        is_active=True,
        allowed_personas=["staff"],
        trigger_config={},
        handler_class="LeaveBalanceHandler",
        is_side_effect=False,
        requires_confirmation=False,
        confirmation_prompt=None,
    )
    instance = SimpleNamespace(
        id=uuid.uuid4(),
        agent_definition_id=template.agent_definition_id,
        is_enabled=True,
        config={},
        trigger_count=0,
        last_triggered_at=None,
    )
    handler = DummyHandler(result=AgentResult(status="success", output={"message": "balance ready"}))
    db = FakeDB(template=template)
    loader = FakeLoader(instance=instance, handler=handler)
    executor = AgentExecutor(db_session=db, loader=loader)

    result = await executor.execute_action(
        tenant_id="00000000-0000-0000-0000-000000000001",
        template_id="leave_balance_v1",
        user_id="staff-1",
        user_persona="staff",
        trigger_payload={"triggered_by": "api_execute", "query": "check leave"},
        claim_set={},
        confirmed=False,
    )

    assert result.status == "success"
    assert handler.execute_calls == 1
    assert db.commit_calls == 1
    assert result.output.get("action_id")


@pytest.mark.asyncio
async def test_executor_fails_on_missing_dependency() -> None:
    template = SimpleNamespace(
        agent_definition_id=uuid.uuid4(),
        template_id="payroll_query_v1",
        name="Payroll Query",
        is_active=True,
        allowed_personas=["staff"],
        trigger_config={"depends_on": ["sensitive_field_monitor_v1"]},
        handler_class="PayrollQueryHandler",
        is_side_effect=False,
        requires_confirmation=False,
        confirmation_prompt=None,
    )
    instance = SimpleNamespace(
        id=uuid.uuid4(),
        agent_definition_id=template.agent_definition_id,
        is_enabled=True,
        config={},
        trigger_count=0,
        last_triggered_at=None,
    )
    handler = DummyHandler(result=AgentResult(status="success", output={}))
    db = FakeDB(template=template)
    loader = FakeLoader(instance=instance, handler=handler, dependencies_active=False)
    executor = AgentExecutor(db_session=db, loader=loader)

    result = await executor.execute_action(
        tenant_id="00000000-0000-0000-0000-000000000001",
        template_id="payroll_query_v1",
        user_id="staff-1",
        user_persona="staff",
        trigger_payload={"triggered_by": "api_execute", "query": "show salary"},
        claim_set={},
        confirmed=False,
    )

    assert result.status == "failed"
    assert "Required dependency" in (result.error or "")
    assert handler.execute_calls == 0
    assert db.commit_calls == 0
