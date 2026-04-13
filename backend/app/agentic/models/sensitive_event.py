from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID


class AlertSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class SensitiveAccessEvent:
    user_alias: str
    session_id: str
    tenant_id: UUID
    persona: str
    department: str
    fields_accessed: list[str]
    field_classifications: dict[str, str]
    data_subject_alias: str
    result_row_count: int
    query_type: str
    connector_type: str | None = None
    source_alias: str | None = None
    execution_time_ms: float | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AlertModel:
    alert_id: str
    tenant_id: UUID
    user_alias: str
    session_id: str
    severity: AlertSeverity
    patterns: list[str]
    status: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)
