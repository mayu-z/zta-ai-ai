from __future__ import annotations

from app.agentic.agents.base_agent import BaseAgent
from app.agentic.core.compiler_interface import ExecutionPlan
from app.agentic.models.action_config import ActionConfig
from app.agentic.models.agent_context import AgentResult, AgentStatus, ClaimSet, RequestContext


class MeetingSchedulerAgent(BaseAgent):
    async def execute(
        self,
        action: ActionConfig,
        claim_set: ClaimSet,
        execution_plan: ExecutionPlan,
        ctx: RequestContext,
    ) -> AgentResult:
        del claim_set
        attendees = execution_plan.metadata.get("attendee_aliases") or []
        if not attendees:
            attendees = [ctx.user_alias]

        try:
            write_result = await self._compiler.execute_write(
                action=action,
                payload={
                    "title": execution_plan.metadata.get("title") or "Meeting",
                    "start": execution_plan.metadata.get("start"),
                    "end": execution_plan.metadata.get("end"),
                    "attendee_aliases": attendees,
                    "location": execution_plan.metadata.get("location"),
                },
                ctx=ctx,
            )
        except Exception as exc:  # noqa: BLE001
            return AgentResult(status=AgentStatus.FAILED, message=f"Calendar scheduling failed: {exc}")

        return AgentResult(
            status=AgentStatus.SUCCESS,
            message="Meeting scheduled successfully.",
            data={"event_id": write_result.generated_id, "attendee_count": len(attendees)},
        )
