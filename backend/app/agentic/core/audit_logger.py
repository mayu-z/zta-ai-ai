from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.agentic.db_models import AgenticAuditEventModel
from app.agentic.models.audit_event import AuditEvent
from app.db.session import SessionLocal


class AuditLogger:
    """Immutable append-only writer for agentic events."""

    async def write(self, event: AuditEvent) -> str:
        return await asyncio.to_thread(self._write_sync, event)

    def _write_sync(self, event: AuditEvent) -> str:
        event_id = ""
        db = SessionLocal()
        try:
            row = AgenticAuditEventModel(
                tenant_id=str(event.tenant_id),
                user_alias=event.user_alias,
                action_id=event.action_id,
                event_type=event.event_type,
                status=event.status,
                payload_hash=event.payload_hash,
                data_accessed=list(event.data_accessed),
                event_metadata=dict(event.metadata),
                created_at=event.timestamp,
            )
            db.add(row)
            db.commit()
            event_id = row.id
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        return event_id

    async def exists_success(
        self,
        *,
        tenant_id: str,
        action_id: str,
        user_alias: str,
        correlation_key: str,
    ) -> bool:
        return await asyncio.to_thread(
            self._exists_success_sync,
            tenant_id,
            action_id,
            user_alias,
            correlation_key,
        )

    def _exists_success_sync(
        self,
        tenant_id: str,
        action_id: str,
        user_alias: str,
        correlation_key: str,
    ) -> bool:
        db = SessionLocal()
        try:
            row = db.scalar(
                select(AgenticAuditEventModel)
                .where(AgenticAuditEventModel.tenant_id == tenant_id)
                .where(AgenticAuditEventModel.action_id == action_id)
                .where(AgenticAuditEventModel.user_alias == user_alias)
                .where(AgenticAuditEventModel.status == "SUCCESS")
                .where(AgenticAuditEventModel.payload_hash == correlation_key)
            )
            return row is not None
        finally:
            db.close()
