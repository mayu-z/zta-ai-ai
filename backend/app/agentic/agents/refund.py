from __future__ import annotations

from app.agentic.agents.base_agent import BaseAgent
from app.agentic.core.compiler_interface import ExecutionPlan
from app.agentic.models.action_config import ActionConfig
from app.agentic.models.agent_context import AgentResult, AgentStatus, ClaimSet, RequestContext


class RefundAgent(BaseAgent):
    async def execute(
        self,
        action: ActionConfig,
        claim_set: ClaimSet,
        execution_plan: ExecutionPlan,
        ctx: RequestContext,
    ) -> AgentResult:
        refundable = claim_set.claims.get("refundable_amount")
        requested = execution_plan.metadata.get("requested_refund_amount", refundable)
        if requested is None:
            return AgentResult(status=AgentStatus.FAILED, message="Refund amount is missing.")

        if refundable is not None and float(requested) > float(refundable):
            return AgentResult(
                status=AgentStatus.FAILED,
                message=f"Requested refund exceeds available refundable amount ({refundable}).",
            )

        try:
            write_result = await self._compiler.execute_write(
                action=action,
                payload={
                    "student_id": ctx.user_alias,
                    "requested_amount": requested,
                    "reason": execution_plan.metadata.get("refund_reason", "Not specified"),
                    "status": "PENDING",
                    "tenant_id": str(ctx.tenant_id),
                },
                ctx=ctx,
            )
        except Exception as exc:  # noqa: BLE001
            return AgentResult(status=AgentStatus.FAILED, message=f"Refund request could not be submitted: {exc}")

        return AgentResult(
            status=AgentStatus.SUCCESS,
            message="Refund request submitted and routed for finance approval.",
            data={"refund_request_id": write_result.generated_id, "requested_amount": requested},
        )
