from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
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

    async def fetch_data(
        self,
        action: ActionConfig,
        ctx: RequestContext,
        policy_decision: Any,
    ) -> ClaimSet:
        if self._planner is not None and hasattr(self._planner, "fetch_data"):
            return await self._planner.fetch_data(action, ctx, policy_decision)

        return ClaimSet(
            claims={
                "tenant_id": str(ctx.tenant_id),
                "user_alias": ctx.user_alias,
                "department_id": ctx.department_id,
            },
            field_classifications={
                "tenant_id": "GENERAL",
                "user_alias": "IDENTIFIER",
                "department_id": "GENERAL",
            },
            source_alias="compiler_interface",
            fetched_at=datetime.now(tz=UTC).replace(tzinfo=None),
            row_count=1,
        )

    async def build_plan(
        self,
        action: ActionConfig,
        claim_set: ClaimSet,
        approval: Any,
        ctx: RequestContext,
    ) -> ExecutionPlan:
        if self._planner is not None and hasattr(self._planner, "build_plan"):
            return await self._planner.build_plan(action, claim_set, approval, ctx)

        steps = [
            "validate_write_guard",
            "prepare_payload",
            "execute",
        ]
        return ExecutionPlan(
            action_id=action.action_id,
            steps=steps,
            write_target=action.write_target,
            payload={
                "claims": claim_set.claims,
                "approval": {
                    "approved": bool(getattr(approval, "approved", False)),
                    "approver_alias": getattr(approval, "approver_alias", None),
                },
                "ctx": {
                    "tenant_id": str(ctx.tenant_id),
                    "user_alias": ctx.user_alias,
                    "persona": ctx.persona,
                },
            },
        )

    async def execute_write(
        self,
        action: ActionConfig,
        payload: dict[str, Any],
        ctx: RequestContext,
    ) -> Any:
        if self._planner is None or not hasattr(self._planner, "execute_write"):
            raise RuntimeError("Planner-backed write execution is not configured")
        return await self._planner.execute_write(action=action, payload=payload, ctx=ctx)
