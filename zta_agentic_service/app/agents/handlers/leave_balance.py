from __future__ import annotations

from typing import Any

from app.agents.base_handler import AgentContext, AgentResult, BaseAgentHandler


class LeaveBalanceHandler(BaseAgentHandler):
    """Leave balance summary with optional apply-mode hinting."""

    @property
    def is_side_effect(self) -> bool:
        return False

    async def execute(self, ctx: AgentContext) -> AgentResult:
        balance = ctx.claim_set.get("leave_balance", {})
        pending = ctx.claim_set.get("pending_requests", [])

        balance_lines = "\n".join([f"  {k.title()}: {v} days" for k, v in balance.items()])
        pending_note = f"\n\nPending approval: {len(pending)} request(s)." if pending else ""
        check_only = bool((ctx.instance.config or {}).get("check_only", True))

        return AgentResult(
            status="success",
            output={
                "balance": balance,
                "pending_count": len(pending),
                "message": (
                    f"Your leave balance:\n{balance_lines}{pending_note}"
                    + ("\n\nWould you like to apply for leave?" if not check_only else "")
                ),
                "can_apply": not check_only,
            },
        )

    async def rollback(self, ctx: AgentContext, partial_result: AgentResult) -> None:
        _ = (ctx, partial_result)

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        _ = config
        return []
