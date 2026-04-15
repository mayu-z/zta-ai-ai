from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.agents.base_handler import AgentContext, AgentResult, BaseAgentHandler


class FeeReminderHandler(BaseAgentHandler):
    """Scheduled fee reminders with deduplication guard per due-date window."""

    def __init__(self, notification_service: Any | None = None, dedup_store: Any | None = None) -> None:
        self.notification_service = notification_service
        self.dedup_store = dedup_store

    @property
    def is_side_effect(self) -> bool:
        return True

    async def execute(self, ctx: AgentContext) -> AgentResult:
        claim_set = ctx.claim_set
        config = ctx.instance.config or {}

        dedup_key = (
            f"fee_reminder:{ctx.tenant_id}:{claim_set.get('student_alias','unknown')}:{claim_set.get('due_date','') }"
        )
        dedup_hours = int(config.get("dedup_window_hours", 24))

        if await self._dedup_check(dedup_key, dedup_hours):
            return AgentResult(
                status="success",
                output={"skipped": True, "reason": "dedup_window_active"},
            )

        message = self._personalise_reminder(claim_set, config.get("message_template"))
        dispatch = await self._send_notification(
            channel=config.get("channel", "in_app"),
            recipient_alias=claim_set.get("student_alias", "unknown-student"),
            subject=f"Fee Payment Reminder - Due {claim_set.get('due_date', 'N/A')}",
            body=message,
            tenant_id=ctx.tenant_id,
        )

        if dispatch.get("delivered"):
            await self._dedup_set(dedup_key, dedup_hours)

        return AgentResult(
            status="success" if dispatch.get("delivered") else "failed",
            output={
                "notification_id": dispatch.get("notification_id"),
                "amount_reminded": claim_set.get("outstanding_amount"),
                "due_date": claim_set.get("due_date"),
                "channel": config.get("channel", "in_app"),
            },
            error=dispatch.get("error") if not dispatch.get("delivered") else None,
        )

    async def rollback(self, ctx: AgentContext, partial_result: AgentResult) -> None:
        _ = (ctx, partial_result)

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        required = ["channel", "message_template", "days_before_due"]
        for field in required:
            if field not in config:
                errors.append(f"{field} is required")
        if int(config.get("days_before_due", 0)) < 1:
            errors.append("days_before_due must be >= 1")
        return errors

    @staticmethod
    def _personalise_reminder(claim_set: dict[str, Any], message_template: str | None) -> str:
        template = (
            message_template
            or "Reminder: Your outstanding amount is Rs. {outstanding_amount} due on {due_date}. Pay via: {payment_link}"
        )
        return template.format(
            outstanding_amount=claim_set.get("outstanding_amount", "N/A"),
            due_date=claim_set.get("due_date", datetime.now(UTC).date().isoformat()),
            payment_link=claim_set.get("payment_link", "link-unavailable"),
        )

    async def _dedup_check(self, key: str, ttl_hours: int) -> bool:
        if self.dedup_store and hasattr(self.dedup_store, "check"):
            result = self.dedup_store.check(key=key, ttl_hours=ttl_hours)
            if hasattr(result, "__await__"):
                result = await result
            return bool(result)
        return False

    async def _dedup_set(self, key: str, ttl_hours: int) -> None:
        if self.dedup_store and hasattr(self.dedup_store, "set"):
            result = self.dedup_store.set(key=key, ttl_hours=ttl_hours)
            if hasattr(result, "__await__"):
                await result

    async def _send_notification(
        self,
        channel: str,
        recipient_alias: str,
        subject: str,
        body: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        if self.notification_service and hasattr(self.notification_service, "send"):
            result = await self.notification_service.send(
                channel=channel,
                recipient_alias=recipient_alias,
                subject=subject,
                body=body,
                tenant_id=tenant_id,
            )
            if isinstance(result, dict):
                return result
            return {
                "delivered": bool(getattr(result, "delivered", False)),
                "notification_id": getattr(result, "notification_id", None),
                "error": getattr(result, "error", None),
            }

        return {
            "delivered": True,
            "notification_id": f"stub-fee-{recipient_alias}",
            "error": None,
        }
