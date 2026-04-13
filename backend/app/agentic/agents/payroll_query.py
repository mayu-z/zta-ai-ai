from __future__ import annotations

from app.agentic.agents.base_agent import BaseAgent
from app.agentic.core.compiler_interface import ExecutionPlan
from app.agentic.models.action_config import ActionConfig
from app.agentic.models.agent_context import AgentResult, AgentStatus, ClaimSet, RequestContext


class PayrollQueryAgent(BaseAgent):
    async def execute(
        self,
        action: ActionConfig,
        claim_set: ClaimSet,
        execution_plan: ExecutionPlan,
        ctx: RequestContext,
    ) -> AgentResult:
        del action, execution_plan, ctx
        salary = claim_set.claims.get("salary")
        deductions = claim_set.claims.get("deductions")
        net_pay = claim_set.claims.get("net_pay")

        return AgentResult(
            status=AgentStatus.SUCCESS,
            message="Payroll details generated from your scoped records.",
            data={
                "salary": salary,
                "deductions": deductions,
                "net_pay": net_pay,
                "field_classifications": claim_set.field_classifications,
            },
        )
