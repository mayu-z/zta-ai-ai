from __future__ import annotations

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.schemas.pipeline import AuditEvent
from app.services.audit_repository import persist_audit_event
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.audit_tasks.write_audit_event")
def write_audit_event_task(event_payload: dict) -> None:
    db = SessionLocal()
    try:
        event = AuditEvent(**event_payload)
        persist_audit_event(db, event)
    finally:
        db.close()
