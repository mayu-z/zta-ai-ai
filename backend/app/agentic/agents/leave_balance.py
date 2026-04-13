from __future__ import annotations

from app.agentic.agents.base_agent import BaseAgent
from app.agentic.core.compiler_interface import ExecutionPlan
from app.agentic.models.action_config import ActionConfig
from app.agentic.models.agent_context import AgentResult, AgentStatus, ClaimSet, RequestContext


class LeaveBalanceAgent(BaseAgent):
    async def execute(
        self,
        action: ActionConfig,
        claim_set: ClaimSet,
        execution_plan: ExecutionPlan,
        ctx: RequestContext,
    ) -> AgentResult:
        balance = float(claim_set.claims.get("casual_leave_balance") or claim_set.claims.get("leave_balance") or 0)

        if action.action_id.endswith("check_v1"):
            return AgentResult(
                status=AgentStatus.SUCCESS,
                message=f"Your current leave balance is {balance} days.",
                data={"leave_balance": balance},
            )

        requested_days = float(execution_plan.metadata.get("requested_days") or 0)
        if requested_days <= 0:
            return AgentResult(status=AgentStatus.FAILED, message="Requested leave days must be greater than zero.")
        if balance < requested_days:
            return AgentResult(
                status=AgentStatus.FAILED,
                message=f"Insufficient leave balance. Available: {balance} days.",
            )

        try:
            write_result = await self._compiler.execute_write(
                action=action,
                payload={
                    "employee_id": ctx.user_alias,
                    "leave_type": execution_plan.metadata.get("leave_type", "CASUAL"),
                    "start_date": execution_plan.metadata.get("start_date"),
                    "end_date": execution_plan.metadata.get("end_date"),
                    "days": requested_days,
                    "status": "APPLIED",
                    "tenant_id": str(ctx.tenant_id),
                },
                ctx=ctx,
            )
        except Exception as exc:  # noqa: BLE001
            return AgentResult(status=AgentStatus.FAILED, message=f"Leave request failed: {exc}")

        return AgentResult(
            status=AgentStatus.SUCCESS,
            message=f"Leave applied for {requested_days} days. Your manager has been notified.",
            data={"leave_record_id": write_result.generated_id},
        )
