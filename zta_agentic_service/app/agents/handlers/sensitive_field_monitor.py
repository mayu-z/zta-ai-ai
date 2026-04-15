from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.agents.base_handler import AgentContext, AgentResult, BaseAgentHandler


class SensitiveFieldMonitorHandler(BaseAgentHandler):
    """Infrastructure anomaly detector for sensitive-field audit access patterns."""

    DEFAULT_THRESHOLDS = {
        "volume_per_hour": 10,
        "bulk_result_rows": 20,
        "probing_queries": 5,
        "probing_window_minutes": 10,
        "after_hours_start": 20,
        "after_hours_end": 8,
    }

    SENSITIVE_FIELD_CATEGORIES = {
        "FINANCIAL": {"salary", "bonus", "bank_account_number", "pan_number", "tax_deduction"},
        "PERSONAL": {"aadhaar_number", "passport_number", "personal_email", "home_address"},
        "ACADEMIC_CONFIDENTIAL": {"internal_marks_before_moderation", "answer_sheet_scans"},
    }

    def __init__(self, notification_service: Any | None = None, session_store: Any | None = None) -> None:
        self.notification_service = notification_service
        self.session_store = session_store

    @property
    def is_side_effect(self) -> bool:
        return True

    async def execute(self, ctx: AgentContext) -> AgentResult:
        event = dict(ctx.trigger_payload or {})
        session_state = dict(ctx.claim_set or {})
        thresholds = {**self.DEFAULT_THRESHOLDS, **((ctx.instance.config or {}).get("thresholds") or {})}

        detected_patterns: list[dict[str, str]] = []

        hourly_count = int(session_state.get("sensitive_accesses_this_hour", 0)) + 1
        if hourly_count > int(thresholds["volume_per_hour"]):
            detected_patterns.append(
                {
                    "pattern": "P1_VOLUME_SPIKE",
                    "detail": (
                        f"{hourly_count} sensitive field accesses in the last hour "
                        f"(threshold: {thresholds['volume_per_hour']})"
                    ),
                }
            )

        timestamp = event.get("timestamp")
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp)
            except ValueError:
                timestamp = datetime.now(UTC)
        if not isinstance(timestamp, datetime):
            timestamp = datetime.now(UTC)

        hour = timestamp.hour
        after_hours = hour >= int(thresholds["after_hours_start"]) or hour < int(
            thresholds["after_hours_end"]
        )
        if after_hours and session_state.get("sensitive_field_accessed"):
            detected_patterns.append(
                {
                    "pattern": "P2_AFTER_HOURS",
                    "detail": f"Sensitive field access at {hour:02d}:00 (outside normal hours)",
                }
            )

        if int(event.get("result_row_count", 0)) > int(thresholds["bulk_result_rows"]):
            detected_patterns.append(
                {
                    "pattern": "P3_BULK_RESULT",
                    "detail": (
                        f"Result contained {event.get('result_row_count')} rows with sensitive fields"
                    ),
                }
            )

        recent_fields = session_state.get("recent_field_combinations", [])
        if len(recent_fields) >= int(thresholds["probing_queries"]):
            is_expanding = self._is_field_combination_expanding(recent_fields)
            if is_expanding:
                detected_patterns.append(
                    {
                        "pattern": "P4_BOUNDARY_PROBING",
                        "detail": (
                            f"Progressive field expansion detected over {len(recent_fields)} queries"
                        ),
                    }
                )

        normal_dept = session_state.get("normal_department_scope")
        current_dept = event.get("data_subject_department")
        if normal_dept and current_dept and normal_dept != current_dept:
            detected_patterns.append(
                {
                    "pattern": "P5_CROSS_CONTEXT",
                    "detail": f"Access to {current_dept} data (normal scope: {normal_dept})",
                }
            )

        if not detected_patterns:
            return AgentResult(status="success", output={"patterns_detected": 0})

        severity = self._calculate_severity(detected_patterns)
        await self._route_alert(ctx, detected_patterns, severity, event)

        return AgentResult(
            status="success",
            output={
                "patterns_detected": len(detected_patterns),
                "severity": severity,
                "patterns": [p["pattern"] for p in detected_patterns],
            },
        )

    async def rollback(self, ctx: AgentContext, partial_result: AgentResult) -> None:
        _ = (ctx, partial_result)

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if config.get("auto_suspend_on_critical") and "it_head_email" not in config:
            errors.append("it_head_email required when auto_suspend_on_critical=true")
        return errors

    @staticmethod
    def _calculate_severity(patterns: list[dict[str, str]]) -> str:
        pattern_types = {pattern["pattern"] for pattern in patterns}
        if {"P1_VOLUME_SPIKE", "P2_AFTER_HOURS", "P3_BULK_RESULT"}.issubset(pattern_types):
            return "CRITICAL"
        if len(patterns) >= 3:
            return "HIGH"
        if {"P4_BOUNDARY_PROBING", "P5_CROSS_CONTEXT"} & pattern_types:
            return "HIGH"
        if len(patterns) == 2:
            return "MEDIUM"
        return "LOW"

    async def _route_alert(
        self,
        ctx: AgentContext,
        patterns: list[dict[str, str]],
        severity: str,
        event: dict[str, Any],
    ) -> None:
        if severity == "LOW":
            return

        message = self._build_alert_message(patterns, severity, event)
        config = ctx.instance.config or {}

        if severity in {"MEDIUM", "HIGH", "CRITICAL"} and self.notification_service and hasattr(
            self.notification_service, "send_security_alert"
        ):
            await self.notification_service.send_security_alert(
                tenant_id=ctx.tenant_id,
                severity=severity,
                message=message,
                recipients=["it_head", "compliance_officer"],
                config=config,
            )

        if severity in {"HIGH", "CRITICAL"} and self.session_store and hasattr(
            self.session_store, "flag_session"
        ):
            await self.session_store.flag_session(
                user_alias=event.get("user_alias", "unknown"),
                tenant_id=ctx.tenant_id,
                reason=f"security_alert:{severity}",
            )

        if severity == "CRITICAL" and config.get("auto_suspend_on_critical", False):
            if self.session_store and hasattr(self.session_store, "suspend_session"):
                await self.session_store.suspend_session(
                    user_alias=event.get("user_alias", "unknown"),
                    tenant_id=ctx.tenant_id,
                    reason="auto_suspend_critical_security_alert",
                )

    @staticmethod
    def _build_alert_message(
        patterns: list[dict[str, str]], severity: str, event: dict[str, Any]
    ) -> str:
        pattern_lines = "\n".join([f"- {item['pattern']}: {item['detail']}" for item in patterns])
        return (
            f"Sensitive-field anomaly detected. Severity={severity}.\n"
            f"User={event.get('user_alias', 'unknown')}\n"
            f"Patterns:\n{pattern_lines}"
        )

    @staticmethod
    def _is_field_combination_expanding(recent_combos: list[Any]) -> bool:
        if len(recent_combos) < 2:
            return False

        normalized: list[set[str]] = []
        for item in recent_combos:
            if isinstance(item, set):
                normalized.append({str(value) for value in item})
            elif isinstance(item, list):
                normalized.append({str(value) for value in item})
            else:
                normalized.append({str(item)})

        for idx in range(1, len(normalized)):
            if not normalized[idx].issuperset(normalized[idx - 1]):
                return False
        return True
