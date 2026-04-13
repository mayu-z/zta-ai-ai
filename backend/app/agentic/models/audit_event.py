from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass
class AuditEvent:
    event_type: str
    action_id: str
    user_alias: str
    tenant_id: UUID
    status: str
    timestamp: datetime = field(default_factory=_utcnow_naive)
    payload_hash: str | None = None
    data_accessed: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)
