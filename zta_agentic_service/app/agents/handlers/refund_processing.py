from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.base_handler import AgentContext, AgentResult, BaseAgentHandler


@dataclass
class EligibilityResult:
    eligible: bool
    reason: str | None = None


class RefundProcessingHandler(BaseAgentHandler):
    """Creates finance workflow requests after eligibility and user confirmation checks."""

    def __init__(self, workflow_client: Any | None = None, notification_service: Any | None = None) -> None:
        self.workflow_client = workflow_client
        self.notification_service = notification_service

    @property
    def is_side_effect(self) -> bool:
        return True

    async def execute(self, ctx: AgentContext) -> AgentResult:
        config = ctx.instance.config or {}
        claim_set = ctx.claim_set

        eligibility = self._check_eligibility(claim_set, config.get("eligibility_rules", []))
        if not eligibility.eligible:
            return AgentResult(
                status="success",
                output={
                    "eligible": False,
                    "reason": eligibility.reason,
                    "message": f"Refund request cannot proceed: {eligibility.reason}",
                },
            )

        if not ctx.confirmed:
            return AgentResult(
                status="pending_confirmation",
                requires_confirmation=True,
                confirmation_prompt=(
                    f"Submit a refund request for Rs. {claim_set.get('refund_amount')} "
                    f"(Reason: {claim_set.get('reason')})?\n"
                    f"Processing time: {config.get('processing_days', 7)} business days."
                ),
                output={"eligible": True},
            )

        ticket = await self._create_ticket(ctx)
        await self._notify_finance_team(ctx, ticket["ticket_id"])

        return AgentResult(
            status="success",
            output={
                "ticket_id": ticket["ticket_id"],
                "message": (
                    f"Your refund request has been submitted (Ticket: {ticket['ticket_id']}). "
                    f"Expected processing: {config.get('processing_days', 7)} business days."
                ),
            },
        )

    async def rollback(self, ctx: AgentContext, partial_result: AgentResult) -> None:
        ticket_id = partial_result.output.get("ticket_id")
        if ticket_id and self.workflow_client and hasattr(self.workflow_client, "cancel_ticket"):
            await self.workflow_client.cancel_ticket(
                ticket_id,
                reason="audit_write_failure_rollback",
            )

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        required = [
            "workflow_system",
            "finance_team_queue",
            "finance_team_alias",
            "eligibility_rules",
        ]
        for field in required:
            if field not in config:
                errors.append(f"{field} is required")
        return errors

    @staticmethod
    def _check_eligibility(claim_set: dict[str, Any], rules: list[dict[str, Any]]) -> EligibilityResult:
        for rule in rules:
            field = rule.get("field")
            op_name = rule.get("operator", "eq")
            expected = rule.get("value")
            actual = claim_set.get(field)

            if op_name == "eq" and actual != expected:
                return EligibilityResult(False, rule.get("reason", f"{field} must equal {expected}"))
            if op_name == "gte" and (actual is None or actual < expected):
                return EligibilityResult(False, rule.get("reason", f"{field} must be >= {expected}"))
            if op_name == "lte" and (actual is None or actual > expected):
                return EligibilityResult(False, rule.get("reason", f"{field} must be <= {expected}"))

        return EligibilityResult(True)

    async def _create_ticket(self, ctx: AgentContext) -> dict[str, Any]:
        config = ctx.instance.config or {}
        claim_set = ctx.claim_set
        if self.workflow_client and hasattr(self.workflow_client, "create_ticket"):
            ticket = await self.workflow_client.create_ticket(
                system=config.get("workflow_system"),
                ticket_type="refund_request",
                data={
                    "student_alias": claim_set.get("student_alias"),
                    "amount": claim_set.get("refund_amount"),
                    "reason": claim_set.get("reason"),
                    "original_payment_ref": claim_set.get("payment_alias"),
                },
                assigned_team=config.get("finance_team_queue"),
            )
            if isinstance(ticket, dict):
                return {"ticket_id": ticket.get("ticket_id")}
            return {"ticket_id": getattr(ticket, "ticket_id", "ticket-stub")}

        return {"ticket_id": f"refund-{ctx.action_id}"}

    async def _notify_finance_team(self, ctx: AgentContext, ticket_id: str) -> None:
        config = ctx.instance.config or {}
        if self.notification_service and hasattr(self.notification_service, "send"):
            await self.notification_service.send(
                channel="email",
                recipient_alias=config.get("finance_team_alias", "finance-team"),
                subject=f"New Refund Request - {ticket_id}",
                body=f"Refund request submitted. Ticket: {ticket_id}. Review required.",
                tenant_id=ctx.tenant_id,
            )
