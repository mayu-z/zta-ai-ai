from __future__ import annotations

from typing import Any

from app.agents.base_handler import AgentContext, AgentResult, BaseAgentHandler


class LeaveApprovalHandler(BaseAgentHandler):
    """Checks leave policies from claim_set and submits HR leave requests on confirmation."""

    def __init__(self, hr_connector: Any | None = None, notification_service: Any | None = None) -> None:
        self.hr_connector = hr_connector
        self.notification_service = notification_service

    @property
    def is_side_effect(self) -> bool:
        return True

    async def execute(self, ctx: AgentContext) -> AgentResult:
        claim_set = ctx.claim_set
        leave_type = claim_set.get("leave_type", "casual")
        balance = int((claim_set.get("leave_balance") or {}).get(leave_type, 0))
        requested_days = int(claim_set.get("days_requested", 0))

        if requested_days > balance:
            return AgentResult(
                status="success",
                output={
                    "eligible": False,
                    "message": (
                        f"Insufficient {leave_type} leave balance. "
                        f"Available: {balance} days. Requested: {requested_days} days."
                    ),
                },
            )

        if claim_set.get("blackout_dates"):
            blackout = ", ".join(claim_set["blackout_dates"])
            return AgentResult(
                status="success",
                output={
                    "eligible": False,
                    "message": f"Leave cannot be applied during: {blackout}",
                },
            )

        if not ctx.confirmed:
            dates_str = ", ".join(claim_set.get("requested_dates", []))
            return AgentResult(
                status="pending_confirmation",
                requires_confirmation=True,
                confirmation_prompt=(
                    f"Apply {leave_type.title()} Leave for {dates_str} ({requested_days} day(s))?\n"
                    f"Remaining balance after approval: {balance - requested_days} days."
                ),
                output={"eligible": True, "balance_after": balance - requested_days},
            )

        leave_request = await self._create_leave_request(ctx)
        await self._notify_approver(ctx, leave_request["request_id"])

        return AgentResult(
            status="success",
            output={
                "request_id": leave_request["request_id"],
                "message": (
                    f"Leave request submitted (ID: {leave_request['request_id']}). "
                    "Your manager has been notified."
                ),
            },
        )

    async def rollback(self, ctx: AgentContext, partial_result: AgentResult) -> None:
        request_id = partial_result.output.get("request_id")
        if request_id and self.hr_connector and hasattr(self.hr_connector, "cancel_leave_request"):
            await self.hr_connector.cancel_leave_request(
                request_id,
                (ctx.instance.config or {}).get("hr_system"),
            )

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        return [] if "hr_system" in config else ["hr_system config block is required"]

    async def _create_leave_request(self, ctx: AgentContext) -> dict[str, Any]:
        claim_set = ctx.claim_set
        if self.hr_connector and hasattr(self.hr_connector, "create_leave_request"):
            request = await self.hr_connector.create_leave_request(
                connector_config=(ctx.instance.config or {}).get("hr_system"),
                applicant_alias=claim_set.get("applicant_alias", ctx.user_id),
                leave_type=claim_set.get("leave_type", "casual"),
                dates=claim_set.get("requested_dates", []),
                approver_alias=claim_set.get("approver_alias", "approver"),
            )
            if isinstance(request, dict):
                return {"request_id": request.get("request_id")}
            return {"request_id": getattr(request, "request_id", f"leave-{ctx.action_id}")}

        return {"request_id": f"leave-{ctx.action_id}"}

    async def _notify_approver(self, ctx: AgentContext, request_id: str) -> None:
        claim_set = ctx.claim_set
        if self.notification_service and hasattr(self.notification_service, "send"):
            await self.notification_service.send(
                channel="email",
                recipient_alias=claim_set.get("approver_alias", "approver"),
                subject="Leave Approval Required",
                body=f"Leave request submitted for your review. Request ID: {request_id}.",
                tenant_id=ctx.tenant_id,
            )
