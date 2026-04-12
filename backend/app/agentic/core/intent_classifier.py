from __future__ import annotations

from dataclasses import dataclass

from app.agentic.models.agent_context import IntentClassification


@dataclass
class IntentClassifier:
    """Deterministic keyword classifier for agentic entry routing."""

    keyword_to_action: dict[str, str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.keyword_to_action is None:
            self.keyword_to_action = {
                "result": "result_notification_v1",
                "fee": "fee_reminder_v1",
                "payment": "upi_payment_link_v1",
                "refund": "refund_request_v1",
                "leave approval": "leave_approval_v1",
                "leave balance": "leave_balance_check_v1",
                "apply leave": "leave_balance_apply_v1",
                "meeting": "meeting_scheduler_v1",
                "schedule": "meeting_scheduler_v1",
                "payroll": "payroll_query_v1",
                "bulk notify": "bulk_notification_v1",
                "email": "email_draft_v1",
            }

    async def classify(self, message: str) -> IntentClassification:
        lowered = (message or "").strip().lower()
        if not lowered:
            return IntentClassification(
                is_agentic=False,
                action_id=None,
                confidence=0.0,
                extracted_entities={},
                raw_intent_text="",
                fallback_to_info=True,
            )

        best_action: str | None = None
        best_keyword_len = -1
        for keyword, action_id in self.keyword_to_action.items():
            if keyword in lowered and len(keyword) > best_keyword_len:
                best_keyword_len = len(keyword)
                best_action = action_id

        if best_action is None:
            return IntentClassification(
                is_agentic=False,
                action_id=None,
                confidence=0.35,
                extracted_entities={},
                raw_intent_text=lowered,
                fallback_to_info=True,
            )

        confidence = 0.9 if best_keyword_len > 5 else 0.75
        return IntentClassification(
            is_agentic=True,
            action_id=best_action,
            confidence=confidence,
            extracted_entities={},
            raw_intent_text=lowered,
            fallback_to_info=False,
        )
