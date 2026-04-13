from __future__ import annotations

from app.agentic.agents.base_agent import BaseAgent
from app.agentic.core.compiler_interface import ExecutionPlan
from app.agentic.models.action_config import ActionConfig
from app.agentic.models.agent_context import AgentResult, AgentStatus, ClaimSet, RequestContext


class ResultNotificationAgent(BaseAgent):
    async def execute(
        self,
        action: ActionConfig,
        claim_set: ClaimSet,
        execution_plan: ExecutionPlan,
        ctx: RequestContext,
    ) -> AgentResult:
        del action, execution_plan, ctx
        score = claim_set.claims.get("result_score") or claim_set.claims.get("score")
        grade = claim_set.claims.get("grade")
        attendance = claim_set.claims.get("attendance_percent")

        parts = ["Your latest result summary is ready."]
        if score is not None:
            parts.append(f"Score: {score}.")
        if grade is not None:
            parts.append(f"Grade: {grade}.")
        if attendance is not None:
            parts.append(f"Attendance: {attendance}%.")

        return AgentResult(
            status=AgentStatus.SUCCESS,
            message=" ".join(parts),
            data={
                "result_score": score,
                "grade": grade,
                "attendance_percent": attendance,
            },
        )
