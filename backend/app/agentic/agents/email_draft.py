from __future__ import annotations

from app.agentic.agents.base_agent import BaseAgent
from app.agentic.core.compiler_interface import ExecutionPlan
from app.agentic.models.action_config import ActionConfig
from app.agentic.models.agent_context import AgentResult, AgentStatus, ClaimSet, RequestContext


class EmailDraftAgent(BaseAgent):
    async def execute(
        self,
        action: ActionConfig,
        claim_set: ClaimSet,
        execution_plan: ExecutionPlan,
        ctx: RequestContext,
    ) -> AgentResult:
        del action, claim_set, ctx
        subject = str(execution_plan.metadata.get("subject") or "Draft Email")
        body = str(execution_plan.metadata.get("body") or "Please review and edit this draft before sending.")
        recipients = execution_plan.metadata.get("to", [])
        return AgentResult(
            status=AgentStatus.SUCCESS,
            message="Email draft prepared.",
            data={"subject": subject, "body": body, "to": recipients},
        )
