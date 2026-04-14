from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class UserUpdateRequest(BaseModel):
    persona_type: str | None = None
    department: str | None = None
    status: str | None = None


class DataSourceCreateRequest(BaseModel):
    name: str
    source_type: str
    config: dict = Field(default_factory=dict)
    department_scope: list[str] = Field(default_factory=list)


class DataSourceUpdateRequest(BaseModel):
    name: str | None = None
    config: dict[str, object] | None = None
    department_scope: list[str] | None = None
    status: Literal["connected", "disconnected", "paused"] | None = None


class FieldMaskingPolicyUpdateRequest(BaseModel):
    schema_field_id: str
    visibility: Literal["visible", "masked", "hidden"] | None = None
    pii_flag: bool | None = None
    masked_for_personas: list[str] | None = None
    display_name: str | None = None
    sync_role_policies: bool = True


class RowLevelPolicyUpdateRequest(BaseModel):
    row_scope_mode: Literal[
        "owner_id",
        "course_ids",
        "department_id",
        "admin_function",
    ] | None = None
    sensitive_domains: list[str] | None = None
    require_business_hours_for_sensitive: bool | None = None
    business_hours_start: int | None = Field(default=None, ge=0, le=23)
    business_hours_end: int | None = Field(default=None, ge=0, le=23)
    require_trusted_device_for_sensitive: bool | None = None
    require_mfa_for_sensitive: bool | None = None


class KillSwitchRequest(BaseModel):
    scope: str
    target_id: str | None = None


class RolePolicyUpsertRequest(BaseModel):
    role_key: str
    display_name: str
    description: str | None = None
    allowed_domains: list[str] = Field(default_factory=list)
    masked_fields: list[str] = Field(default_factory=list)
    aggregate_only: bool = False
    chat_enabled: bool = True
    row_scope_mode: str | None = None
    sensitive_domains: list[str] = Field(
        default_factory=lambda: ["finance", "hr"]
    )
    require_business_hours_for_sensitive: bool = True
    business_hours_start: int = 9
    business_hours_end: int = 19
    require_trusted_device_for_sensitive: bool = True
    require_mfa_for_sensitive: bool = True
    is_active: bool = True


class DomainKeywordUpsertRequest(BaseModel):
    domain: str
    keywords: list[str] = Field(default_factory=list)
    is_active: bool = True


class IntentDefinitionUpsertRequest(BaseModel):
    intent_name: str
    domain: str
    entity_type: str
    slot_keys: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    persona_types: list[str] = Field(default_factory=list)
    requires_aggregation: bool = False
    is_default: bool = False
    priority: int = 100
    is_active: bool = True


class DomainSourceBindingUpsertRequest(BaseModel):
    domain: str
    source_type: str | None = None
    data_source_id: str | None = None
    is_active: bool = True


class IntentDetectionKeywordUpsertRequest(BaseModel):
    """Request schema for creating/updating intent detection keywords.

    Detection keywords are used to identify and route specific intents.
    For example, grade markers (gpa, grade, grades, etc.) are used to route
    student queries to the student_grades intent.

    Example:
        {
            "intent_name": "student_grades",
            "keyword_type": "grade_marker",
            "keyword": "gpa",
            "priority": 100,
            "is_active": true
        }
    """

    intent_name: str
    keyword_type: str
    keyword: str
    priority: int = 100
    is_active: bool = True


class ActionExecuteRequest(BaseModel):
    action_id: str
    input_payload: dict[str, object] = Field(default_factory=dict)
    dry_run: bool = False


class ActionTemplateOverrideUpsertRequest(BaseModel):
    is_enabled: bool | None = None
    trigger: str | None = None
    approval_required: bool | None = None
    approver_role: str | None = None
    sla_hours: int | None = Field(default=None, ge=1, le=168)
    execution_steps: list[str] | None = None


class AgentDefinitionOverrideUpsertRequest(BaseModel):
    override: dict[str, Any] = Field(default_factory=dict)


class AgentDefinitionCacheInvalidationRequest(BaseModel):
    agent_ids: list[str] | None = None
    include_action_cache: bool = True


class ActionApprovalRequest(BaseModel):
    comment: str | None = None


class ActionRollbackRequest(BaseModel):
    reason: str = ""


class ComplianceForensicExportRequest(BaseModel):
    from_at: datetime
    to_at: datetime
    include_action_ids: list[str] = Field(default_factory=list)
    include_blocked_queries_only: bool = False
    max_items: int = Field(default=250, ge=10, le=1000)


class ComplianceRetentionRunRequest(BaseModel):
    retention_days: int = Field(default=365, ge=1, le=3650)
    dry_run: bool = True
    max_items: int = Field(default=500, ge=1, le=5000)
    as_of: datetime | None = None


class ComplianceAttestationCreateRequest(BaseModel):
    framework: str
    from_at: datetime | None = None
    to_at: datetime | None = None
    max_items: int = Field(default=500, ge=10, le=5000)
    statement: str | None = None


class ComplianceCaseCreateRequest(BaseModel):
    case_type: str
    subject_identifier: str
    delivery_method: str | None = None
    legal_basis: str | None = None


class ComplianceCaseLegalHoldRequest(BaseModel):
    active: bool
    reason: str = ""
