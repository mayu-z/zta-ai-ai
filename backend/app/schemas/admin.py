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
