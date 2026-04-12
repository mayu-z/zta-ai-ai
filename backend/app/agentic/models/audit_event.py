from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass
class AuditEvent:
    event_type: str
    action_id: str
    user_alias: str
    tenant_id: UUID
    status: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    payload_hash: str | None = None
    data_accessed: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)
