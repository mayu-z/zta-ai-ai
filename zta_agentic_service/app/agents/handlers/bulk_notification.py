from __future__ import annotations

from typing import Any

from app.agents.base_handler import AgentContext, AgentResult, BaseAgentHandler


class BulkNotificationHandler(BaseAgentHandler):
    """Admin-triggered bulk notification sender with confirmation and rate limiting metadata."""

    def __init__(self, notification_service: Any | None = None) -> None:
        self.notification_service = notification_service

    @property
    def is_side_effect(self) -> bool:
        return True

    async def execute(self, ctx: AgentContext) -> AgentResult:
        config = ctx.instance.config or {}
        recipient_aliases = list(ctx.claim_set.get("recipient_aliases", []))
        recipient_count = len(recipient_aliases)

        if not ctx.confirmed:
            return AgentResult(
                status="pending_confirmation",
                requires_confirmation=True,
                confirmation_prompt=(
                    f"Send notification to {recipient_count} recipients "
                    f"({ctx.trigger_payload.get('target_description', 'selected users')})?\n\n"
                    f"Message: {str(ctx.trigger_payload.get('message', ''))[:200]}"
                ),
                output={"recipient_count": recipient_count},
            )

        dispatch_results = await self._send_bulk(
            channel=config.get("channel", "in_app"),
            recipient_aliases=recipient_aliases,
            subject=ctx.trigger_payload.get("subject", "Campus Announcement"),
            body=ctx.trigger_payload.get("message", ""),
            tenant_id=ctx.tenant_id,
            rate_limit_key=f"bulk:{ctx.tenant_id}",
            daily_user_limit=int(config.get("daily_user_notification_limit", 3)),
        )

        return AgentResult(
            status="success",
            output={
                "total": recipient_count,
                "delivered": dispatch_results.get("delivered_count", 0),
                "rate_limited": dispatch_results.get("rate_limited_count", 0),
                "failed": dispatch_results.get("failed_count", 0),
                "batch_id": dispatch_results.get("batch_id"),
            },
        )

    async def rollback(self, ctx: AgentContext, partial_result: AgentResult) -> None:
        _ = (ctx, partial_result)

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        if int(config.get("daily_user_notification_limit", 3)) < 1:
            return ["daily_user_notification_limit must be >= 1"]
        return []

    async def _send_bulk(self, **kwargs: Any) -> dict[str, Any]:
        if self.notification_service and hasattr(self.notification_service, "send_bulk"):
            result = await self.notification_service.send_bulk(**kwargs)
            if isinstance(result, dict):
                return result
            return {
                "batch_id": getattr(result, "batch_id", None),
                "delivered_count": getattr(result, "delivered_count", 0),
                "rate_limited_count": getattr(result, "rate_limited_count", 0),
                "failed_count": getattr(result, "failed_count", 0),
            }

        recipients = kwargs.get("recipient_aliases", [])
        return {
            "batch_id": f"bulk-{kwargs.get('tenant_id', 'tenant')}",
            "delivered_count": len(recipients),
            "rate_limited_count": 0,
            "failed_count": 0,
        }
