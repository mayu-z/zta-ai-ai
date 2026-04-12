from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class RateLimitConfig(BaseModel):
    max_per_window: int = Field(gt=0)
    window_seconds: int = Field(gt=0)


class NotificationConfig(BaseModel):
    template_id: str
    channels: list[Literal["email", "sms", "inapp"]]
    recipient_resolver: str


class ActionConfig(BaseModel):
    action_id: str
    tenant_id: UUID
    display_name: str
    description: str
    trigger_type: Literal["user_query", "scheduled", "event", "admin_initiated"]
    required_data_scope: list[str]
    output_type: Literal[
        "notification",
        "link",
        "workflow",
        "response",
        "email",
        "calendar_invite",
        "bulk_notification",
    ]
    write_target: str | None = None
    requires_confirmation: bool = True
    human_approval_required: bool = False
    approval_level: Literal[
        "self",
        "manager",
        "dept_head",
        "finance_officer",
        "hr_head",
        "admin",
        "org_hierarchy_configured",
    ] = "self"
    allowed_personas: list[str]
    financial_transaction: bool = False
    has_sensitive_fields: bool = False
    cache_results: bool = True
    rate_limit: RateLimitConfig | None = None
    notification_config: NotificationConfig | None = None
    extra_config: dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool = True
    version: int = 1

    @model_validator(mode="after")
    def validate_consistency(self) -> "ActionConfig":
        if self.financial_transaction and self.cache_results:
            raise ValueError("financial_transaction actions must have cache_results=False")
        if not self.allowed_personas:
            raise ValueError("allowed_personas must include at least one persona")
        if not self.required_data_scope:
            raise ValueError("required_data_scope must not be empty")
        self.action_id = self.action_id.strip()
        return self
