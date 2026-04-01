from __future__ import annotations

import socket
import time
from datetime import UTC, datetime
from urllib.parse import urlparse

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.schemas.pipeline import AuditEvent
from app.services.audit_repository import persist_audit_event
from app.tasks.audit_tasks import write_audit_event_task


class AuditService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._broker_unavailable_until = 0.0

    def _persist_sync(self, event: AuditEvent) -> None:
        db = SessionLocal()
        try:
            event.created_at = event.created_at or datetime.now(tz=UTC)
            persist_audit_event(db, event)
        finally:
            db.close()

    def _broker_is_reachable(self) -> bool:
        now = time.time()
        if now < self._broker_unavailable_until:
            return False

        parsed = urlparse(self._settings.celery_broker_url)
        host = parsed.hostname
        port = parsed.port or 6379
        if not host:
            return True

        try:
            with socket.create_connection((host, port), timeout=0.2):
                return True
        except OSError:
            self._broker_unavailable_until = now + 5
            return False

    def enqueue(self, event: AuditEvent) -> None:
        if not self._broker_is_reachable():
            self._persist_sync(event)
            return

        try:
            write_audit_event_task.delay(event.model_dump(mode="json"))
        except Exception:  # noqa: BLE001
            # Fallback path keeps logging append-only guarantees if broker is unavailable.
            self._broker_unavailable_until = time.time() + 5
            self._persist_sync(event)


audit_service = AuditService()
