from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ScopeContext(BaseModel):
    tenant_id: str
    user_id: str
    email: str
    name: str = ""
    persona_type: str
    department: str | None = None
    external_id: str
    admin_function: str | None = None
    role_key: str | None = None
    course_ids: list[str] = Field(default_factory=list)
    row_scope_mode: str | None = None
    row_scope_filters: dict[str, Any] = Field(default_factory=dict)
    allowed_domains: list[str] = Field(default_factory=list)
    denied_domains: list[str] = Field(default_factory=list)
    masked_fields: list[str] = Field(default_factory=list)
    aggregate_only: bool = False
    own_id: str | None = None
    chat_enabled: bool = True
    sensitive_domains: list[str] = Field(
        default_factory=lambda: ["finance", "hr"]
    )
    require_business_hours_for_sensitive: bool = True
    business_hours_start: int = 9
    business_hours_end: int = 19
    require_trusted_device_for_sensitive: bool = True
    require_mfa_for_sensitive: bool = True
    session_id: str = "session-unknown"
    session_ip: str | None = None
    device_trusted: bool = True
    mfa_verified: bool = True


class InterpretedIntent(BaseModel):
    name: str
    domain: str
    entity_type: str
    persona_type: str | None = None
    request_style: str | None = None
    persona_types: tuple[str, ...] = ()
    raw_prompt: str
    sanitized_prompt: str
    aliased_prompt: str
    filters: dict[str, Any] = Field(default_factory=dict)
    aggregation: str | None = None
    slot_keys: list[str] = Field(default_factory=list)
    detected_domains: list[str] = Field(default_factory=list)

    def normalized(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "domain": self.domain,
            "entity_type": self.entity_type,
            "persona_type": self.persona_type,
            "request_style": self.request_style,
            "filters": self.filters,
            "aggregation": self.aggregation,
            "slot_keys": self.slot_keys,
            "detected_domains": sorted(self.detected_domains),
        }


class InterpreterOutput(BaseModel):
    intent: InterpretedIntent
    intent_hash: str
    cached_template: str | None = None
    cached_compiled_query: dict[str, Any] | None = None
    schema_real_identifiers: list[str] = Field(default_factory=list)


class CompiledQueryPlan(BaseModel):
    tenant_id: str
    source_type: str = "ipeds_claims"
    data_source_id: str | None = None
    source_binding_id: str | None = None
    domain: str
    entity_type: str
    select_keys: list[str] = Field(default_factory=list)
    select_claim_keys: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    slot_map: dict[str, str] = Field(default_factory=dict)
    requires_aggregate: bool = False
    parameterized_signature: str

    @model_validator(mode="after")
    def _sync_select_key_fields(self) -> "CompiledQueryPlan":
        if self.select_keys and not self.select_claim_keys:
            self.select_claim_keys = list(self.select_keys)
        elif self.select_claim_keys and not self.select_keys:
            self.select_keys = list(self.select_claim_keys)
        return self


class PolicyDecision(BaseModel):
    allowed: bool
    reason: str | None = None


class QueryExecutionResult(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    masked_fields_applied: list[str] = Field(default_factory=list)


class PipelineResult(BaseModel):
    response_text: str
    source: str
    latency_ms: int
    intent_hash: str
    domains_accessed: list[str]
    policy_proof_ids: list[str] = Field(default_factory=list)
    was_blocked: bool = False
    block_reason: str | None = None


class AuditEvent(BaseModel):
    tenant_id: str
    user_id: str
    session_id: str
    query_text: str
    intent_hash: str
    domains_accessed: list[str]
    was_blocked: bool
    block_reason: str | None
    response_summary: str
    latency_ms: int
    latency_flag: str | None = None
    created_at: datetime
