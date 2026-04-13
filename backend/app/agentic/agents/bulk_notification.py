from __future__ import annotations

from app.agentic.agents.base_agent import BaseAgent
from app.agentic.core.compiler_interface import ExecutionPlan
from app.agentic.models.action_config import ActionConfig
from app.agentic.models.agent_context import AgentResult, AgentStatus, ClaimSet, RequestContext


class BulkNotificationAgent(BaseAgent):
    async def execute(
        self,
        action: ActionConfig,
        claim_set: ClaimSet,
        execution_plan: ExecutionPlan,
        ctx: RequestContext,
    ) -> AgentResult:
        del action, ctx
        recipients = claim_set.claims.get("recipient_aliases") or execution_plan.metadata.get("recipient_aliases") or []
        if isinstance(recipients, str):
            recipients = [recipients]
        count = len(recipients) if isinstance(recipients, list) else 0
        message = str(execution_plan.metadata.get("message") or "Notification queued.")
        return AgentResult(
            status=AgentStatus.SUCCESS,
            message=f"Bulk notification prepared for {count} recipients.",
            data={"recipient_count": count, "message": message},
        )
