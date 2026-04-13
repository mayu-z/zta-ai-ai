from __future__ import annotations

from app.agentic.agents.base_agent import BaseAgent
from app.agentic.core.compiler_interface import ExecutionPlan
from app.agentic.models.action_config import ActionConfig
from app.agentic.models.agent_context import AgentResult, AgentStatus, ClaimSet, RequestContext


class LeaveApprovalAgent(BaseAgent):
    async def execute(
        self,
        action: ActionConfig,
        claim_set: ClaimSet,
        execution_plan: ExecutionPlan,
        ctx: RequestContext,
    ) -> AgentResult:
        del claim_set
        status = str(execution_plan.metadata.get("approval_status") or "PENDING").upper()
        leave_type = str(execution_plan.metadata.get("leave_type") or "GENERAL")
        start_date = execution_plan.metadata.get("start_date")
        end_date = execution_plan.metadata.get("end_date")
        days = int(execution_plan.metadata.get("requested_days") or 1)

        try:
            write_result = await self._compiler.execute_write(
                action=action,
                payload={
                    "employee_id": ctx.user_alias,
                    "leave_type": leave_type,
                    "start_date": start_date,
                    "end_date": end_date,
                    "days": days,
                    "status": status,
                    "tenant_id": str(ctx.tenant_id),
                },
                ctx=ctx,
            )
        except Exception as exc:  # noqa: BLE001
            return AgentResult(status=AgentStatus.FAILED, message=f"Leave approval update failed: {exc}")

        return AgentResult(
            status=AgentStatus.SUCCESS,
            message=f"Leave request recorded with status {status}.",
            data={"leave_record_id": write_result.generated_id, "status": status},
        )
