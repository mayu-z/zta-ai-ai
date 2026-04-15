from __future__ import annotations

from typing import Any

from app.agents.base_handler import AgentContext, AgentResult, BaseAgentHandler


class MeetingSchedulerHandler(BaseAgentHandler):
    """Proposes and confirms meetings before calendar writes and invite dispatch."""

    def __init__(self, calendar_connector: Any | None = None) -> None:
        self.calendar_connector = calendar_connector

    @property
    def is_side_effect(self) -> bool:
        return True

    async def execute(self, ctx: AgentContext) -> AgentResult:
        claim_set = ctx.claim_set
        best_slot = claim_set.get("best_slot")
        if not best_slot:
            return AgentResult(
                status="success",
                output={
                    "found_slot": False,
                    "message": "No common availability found for the requested range.",
                },
            )

        if not ctx.confirmed:
            return AgentResult(
                status="pending_confirmation",
                requires_confirmation=True,
                confirmation_prompt=(
                    f"Schedule '{claim_set.get('meeting_title', 'Meeting')}'\n"
                    f"Time: {best_slot.get('start')} - {best_slot.get('end')}\n"
                    f"Invitees: {len(claim_set.get('invitee_aliases', []))} people\n"
                    "Send calendar invites to all?"
                ),
                output={"best_slot": best_slot},
            )

        event = await self._create_event(ctx, best_slot)
        return AgentResult(
            status="success",
            output={
                "event_id": event["event_id"],
                "message": (
                    f"Meeting scheduled. Invites sent to {len(claim_set.get('invitee_aliases', []))} people."
                ),
            },
        )

    async def rollback(self, ctx: AgentContext, partial_result: AgentResult) -> None:
        event_id = partial_result.output.get("event_id")
        if event_id and self.calendar_connector and hasattr(self.calendar_connector, "delete_event"):
            await self.calendar_connector.delete_event(
                event_id,
                (ctx.instance.config or {}).get("calendar_system"),
            )

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        return [] if "calendar_system" in config else ["calendar_system config is required"]

    async def _create_event(self, ctx: AgentContext, best_slot: dict[str, Any]) -> dict[str, Any]:
        claim_set = ctx.claim_set
        if self.calendar_connector and hasattr(self.calendar_connector, "create_event"):
            event = await self.calendar_connector.create_event(
                connector_config=(ctx.instance.config or {}).get("calendar_system"),
                organiser_alias=claim_set.get("organiser_alias", ctx.user_id),
                invitee_aliases=claim_set.get("invitee_aliases", []),
                title=claim_set.get("meeting_title", "Meeting"),
                start=best_slot.get("start"),
                end=best_slot.get("end"),
                tenant_id=ctx.tenant_id,
            )
            if isinstance(event, dict):
                return {"event_id": event.get("event_id")}
            return {"event_id": getattr(event, "event_id", f"meeting-{ctx.action_id}")}

        return {"event_id": f"meeting-{ctx.action_id}"}
