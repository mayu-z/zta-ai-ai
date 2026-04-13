from __future__ import annotations

from app.agentic.agents.base_agent import BaseAgent
from app.agentic.core.compiler_interface import ExecutionPlan
from app.agentic.models.action_config import ActionConfig
from app.agentic.models.agent_context import AgentResult, AgentStatus, ClaimSet, RequestContext


class FeeReminderAgent(BaseAgent):
    async def execute(
        self,
        action: ActionConfig,
        claim_set: ClaimSet,
        execution_plan: ExecutionPlan,
        ctx: RequestContext,
    ) -> AgentResult:
        del action, execution_plan, ctx
        amount = claim_set.claims.get("outstanding_balance")
        due_date = claim_set.claims.get("due_date")
        if amount in (None, 0, 0.0):
            return AgentResult(status=AgentStatus.SUCCESS, message="No outstanding fees were found.")

        return AgentResult(
            status=AgentStatus.SUCCESS,
            message=f"Outstanding balance: {amount}. Due date: {due_date or 'not available'}.",
            data={"outstanding_balance": amount, "due_date": due_date},
        )
