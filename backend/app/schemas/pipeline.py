from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ScopeContext(BaseModel):
    tenant_id: str
    user_id: str
    email: str
    name: str
    persona_type: str
    department: str | None = None
    external_id: str
    admin_function: str | None = None
    course_ids: list[str] = Field(default_factory=list)
    allowed_domains: list[str] = Field(default_factory=list)
    denied_domains: list[str] = Field(default_factory=list)
    masked_fields: list[str] = Field(default_factory=list)
    aggregate_only: bool = False
    own_id: str | None = None
    chat_enabled: bool = True
    session_id: str
    session_ip: str | None = None
    device_trusted: bool = True
    mfa_verified: bool = True


class InterpretedIntent(BaseModel):
    name: str
    domain: str
    entity_type: str
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
    source_type: str = "mock_claims"
    domain: str
    entity_type: str
    select_claim_keys: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    slot_map: dict[str, str] = Field(default_factory=dict)
    requires_aggregate: bool = False
    parameterized_signature: str


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
    created_at: datetime
