from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class RequestContext:
    """Immutable context for every agent execution."""

    tenant_id: UUID
    user_alias: str
    session_id: str
    persona: str
    department_id: str
    jwt_claims: dict[str, Any]


@dataclass
class IntentClassification:
    is_agentic: bool
    action_id: str | None
    confidence: float
    extracted_entities: dict[str, Any]
    raw_intent_text: str
    fallback_to_info: bool = False


@dataclass
class ClaimSet:
    """Connector output sanitized to abstract claims only."""

    claims: dict[str, Any]
    field_classifications: dict[str, str]
    source_alias: str
    fetched_at: datetime
    row_count: int


class AgentStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    SCOPE_DENIED = "SCOPE_DENIED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    FALLBACK_TO_INFO = "FALLBACK_TO_INFO"


@dataclass
class AgentResult:
    status: AgentStatus
    message: str
    data: dict[str, Any] | None = None
    workflow_id: str | None = None
    audit_event_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
