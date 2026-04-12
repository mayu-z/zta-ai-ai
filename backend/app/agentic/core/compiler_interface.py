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

    async def build_plan(
        self,
        action: ActionConfig,
        claim_set: ClaimSet,
        approval: Any,
        ctx: RequestContext,
    ) -> ExecutionPlan:
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
