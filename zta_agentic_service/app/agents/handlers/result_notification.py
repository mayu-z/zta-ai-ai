from __future__ import annotations

import operator
from typing import Any

from app.agents.base_handler import AgentContext, AgentResult, BaseAgentHandler


class ResultNotificationHandler(BaseAgentHandler):
    """Event-driven result notification with configurable improvement rule evaluation."""

    OPS = {
        "<": operator.lt,
        "<=": operator.le,
        ">": operator.gt,
        ">=": operator.ge,
        "==": operator.eq,
        "!=": operator.ne,
    }

    def __init__(self, notification_service: Any | None = None) -> None:
        self.notification_service = notification_service

    @property
    def is_side_effect(self) -> bool:
        return True

    async def execute(self, ctx: AgentContext) -> AgentResult:
        config = ctx.instance.config or {}
        rules = config.get("improvement_rules", [])
        suggestions = self._apply_rules(ctx.claim_set, rules)
        notification = self._build_notification(ctx.claim_set, suggestions, config)

        dispatch_result = await self._send_notification(
            channel=config.get("notification_channel", "in_app"),
            recipient_alias=ctx.claim_set.get("student_alias", "unknown-student"),
            subject=notification["subject"],
            body=notification["body"],
            tenant_id=ctx.tenant_id,
        )

        delivered = bool(dispatch_result.get("delivered", False))
        return AgentResult(
            status="success" if delivered else "failed",
            output={
                "notification_id": dispatch_result.get("notification_id"),
                "channel": config.get("notification_channel", "in_app"),
                "suggestions_triggered": [rule.get("rule_id") for rule in suggestions],
                "delivery_status": dispatch_result.get("status", "unknown"),
            },
            error=dispatch_result.get("error") if not delivered else None,
        )

    async def rollback(self, ctx: AgentContext, partial_result: AgentResult) -> None:
        notification_id = partial_result.output.get("notification_id")
        if notification_id and self.notification_service and hasattr(
            self.notification_service, "mark_orphaned"
        ):
            await self.notification_service.mark_orphaned(notification_id)

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if "notification_channel" not in config:
            errors.append("notification_channel is required")
        if "improvement_rules" not in config:
            errors.append("improvement_rules list is required (can be empty)")
        if "semester_filter" not in config:
            errors.append("semester_filter is required to scope trigger")
        return errors

    def _apply_rules(self, claim_set: dict[str, Any], rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
        triggered: list[dict[str, Any]] = []
        for rule in rules:
            condition = str(rule.get("condition", "")).strip()
            if condition and self._evaluate_condition(condition, claim_set):
                triggered.append(rule)
        return triggered

    def _evaluate_condition(self, condition: str, claim_set: dict[str, Any]) -> bool:
        parts = condition.split()
        if len(parts) != 3:
            return False
        lhs, op_symbol, rhs_raw = parts
        comparator = self.OPS.get(op_symbol)
        if comparator is None:
            return False

        rhs = self._coerce(rhs_raw)
        if lhs in {"score_pct", "grade", "class_avg"} and isinstance(claim_set.get("subjects"), list):
            for subject in claim_set["subjects"]:
                if comparator(self._coerce(subject.get(lhs)), rhs):
                    return True
            return False

        lhs_value = self._coerce(claim_set.get(lhs))
        try:
            return comparator(lhs_value, rhs)
        except TypeError:
            return False

    @staticmethod
    def _coerce(value: Any) -> Any:
        if value is None:
            return value
        try:
            if isinstance(value, str) and value.count(".") <= 1:
                return float(value) if "." in value else int(value)
            if isinstance(value, (int, float)):
                return value
        except ValueError:
            return value
        return value

    @staticmethod
    def _build_notification(
        claim_set: dict[str, Any],
        suggestions: list[dict[str, Any]],
        config: dict[str, Any],
    ) -> dict[str, str]:
        result_state = claim_set.get("overall_result", "UPDATED")
        subject = f"Result Update - {result_state}"

        suggestion_lines = [f"- {item.get('suggestion_text', 'Follow advisor guidance')}" for item in suggestions]
        if not suggestion_lines:
            suggestion_lines = ["- Keep your current performance momentum."]

        body_template = config.get(
            "message_template",
            "Your results are available. Attendance: {attendance_pct}%.\n\nSuggestions:\n{suggestions}",
        )
        body = body_template.format(
            attendance_pct=claim_set.get("attendance_pct", "N/A"),
            suggestions="\n".join(suggestion_lines),
        )
        return {"subject": subject, "body": body}

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
                "status": getattr(result, "status", "unknown"),
                "error": getattr(result, "error", None),
            }

        return {
            "delivered": True,
            "notification_id": f"stub-result-{recipient_alias}",
            "status": "delivered",
            "error": None,
        }
