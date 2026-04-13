from __future__ import annotations

from uuid import uuid4

from app.agentic.compiler.scope_injector import ScopeInjector
from app.agentic.models.action_config import ActionConfig
from app.agentic.models.agent_context import RequestContext


def _action(scopes: list[str]) -> ActionConfig:
    return ActionConfig(
        action_id="test_action",
        tenant_id=uuid4(),
        display_name="test",
        description="test",
        trigger_type="user_query",
        required_data_scope=scopes,
        output_type="response",
        allowed_personas=["student"],
    )


def _ctx(tenant_id) -> RequestContext:
    return RequestContext(
        tenant_id=tenant_id,
        user_alias="STU-00412",
        session_id="sid-1",
        persona="student",
        department_id="CS",
        jwt_claims={},
    )


def test_self_scope_injection() -> None:
    tenant_id = uuid4()
    action = _action(["fees.own"])
    ctx = _ctx(tenant_id)

    scope, filters = ScopeInjector().inject(action, ctx, "fees")

    assert scope.tenant_id == str(tenant_id)
    assert any(item.field == "student_id" and item.value == "STU-00412" for item in filters)


def test_department_scope_injection() -> None:
    tenant_id = uuid4()
    action = _action(["user_directory.dept"])
    ctx = _ctx(tenant_id)

    scope, filters = ScopeInjector().inject(action, ctx, "user_directory")

    assert scope.tenant_id == str(tenant_id)
    assert any(item.field == "department_id" and item.value == "CS" for item in filters)


def test_tenant_id_always_present() -> None:
    tenant_id = uuid4()
    action = _action(["results.own"])
    ctx = _ctx(tenant_id)

    scope, _ = ScopeInjector().inject(action, ctx, "results")

    assert scope.tenant_id == str(tenant_id)
    assert scope.tenant_id != ""
