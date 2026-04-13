from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.agentic.models.action_config import ActionConfig
from app.agentic.models.agent_context import ClaimSet, RequestContext


@dataclass
class ExecutionPlan:
    action_id: str
    steps: list[str]
    write_target: str | None
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    async def execute(self) -> dict[str, Any]:
        """Default execution contract for agent execute() methods."""
        return {
            "action_id": self.action_id,
            "executed_steps": list(self.steps),
            "write_target": self.write_target,
            "payload": self.payload,
        }


class CompilerInterface:
    """Final planner for execution-ready operations."""

    def __init__(self, planner: Any | None = None) -> None:
        self._planner = planner

    def _require_planner_method(self, method_name: str) -> Any:
        if self._planner is None or not hasattr(self._planner, method_name):
            raise RuntimeError(f"Planner-backed '{method_name}' is not configured")
        return getattr(self._planner, method_name)

    async def fetch_data(
        self,
        action: ActionConfig,
        ctx: RequestContext,
        policy_decision: Any,
    ) -> ClaimSet:
        fetch_data_impl = self._require_planner_method("fetch_data")
        return await fetch_data_impl(action, ctx, policy_decision)

    async def build_plan(
        self,
        action: ActionConfig,
        claim_set: ClaimSet,
        approval: Any,
        ctx: RequestContext,
    ) -> ExecutionPlan:
        build_plan_impl = self._require_planner_method("build_plan")
        return await build_plan_impl(action, claim_set, approval, ctx)

    async def execute_write(
        self,
        action: ActionConfig,
        payload: dict[str, Any],
        ctx: RequestContext,
    ) -> Any:
        execute_write_impl = self._require_planner_method("execute_write")
        return await execute_write_impl(action=action, payload=payload, ctx=ctx)
