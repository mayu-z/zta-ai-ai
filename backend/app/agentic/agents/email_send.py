from __future__ import annotations

from app.agentic.agents.base_agent import BaseAgent
from app.agentic.core.compiler_interface import ExecutionPlan
from app.agentic.models.action_config import ActionConfig
from app.agentic.models.agent_context import AgentResult, AgentStatus, ClaimSet, RequestContext


class EmailSendAgent(BaseAgent):
    async def execute(
        self,
        action: ActionConfig,
        claim_set: ClaimSet,
        execution_plan: ExecutionPlan,
        ctx: RequestContext,
    ) -> AgentResult:
        del claim_set
        to_list = execution_plan.metadata.get("to") or []
        cc_list = execution_plan.metadata.get("cc") or []
        subject = str(execution_plan.metadata.get("subject") or "Notification")
        body = str(execution_plan.metadata.get("body") or "")

        try:
            write_result = await self._compiler.execute_write(
                action=action,
                payload={
                    "from_alias": ctx.user_alias,
                    "to": to_list,
                    "cc": cc_list,
                    "subject": subject,
                    "body": body,
                    "tenant_id": str(ctx.tenant_id),
                },
                ctx=ctx,
            )
        except Exception as exc:  # noqa: BLE001
            return AgentResult(status=AgentStatus.FAILED, message=f"Email delivery failed: {exc}")

        message_hash = (write_result.details or {}).get("message_hash")
        return AgentResult(
            status=AgentStatus.SUCCESS,
            message="Email sent successfully.",
            data={"message_hash": message_hash, "recipient_count": write_result.rows_affected},
        )
