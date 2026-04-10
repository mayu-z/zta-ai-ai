from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import AuditLog
from app.schemas.pipeline import AuditEvent


def persist_audit_event(db: Session, event: AuditEvent) -> None:
    row = AuditLog(
        tenant_id=event.tenant_id,
        user_id=event.user_id,
        session_id=event.session_id,
        query_text=event.query_text,
        intent_hash=event.intent_hash,
        domains_accessed=event.domains_accessed,
        was_blocked=event.was_blocked,
        block_reason=event.block_reason,
        response_summary=event.response_summary[:200],
        latency_ms=event.latency_ms,
        latency_flag=event.latency_flag,
        created_at=event.created_at or datetime.now(tz=UTC),
    )
    db.add(row)
    db.commit()
