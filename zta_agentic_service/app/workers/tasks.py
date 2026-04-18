from __future__ import annotations

from datetime import UTC, datetime

from app.actions.workflows import ScheduledReporting
from app.db.enums import ActionExecutionStatus
from app.db.models import ActionExecution
from app.db.session import SessionLocal
from app.workers.celery_app import celery_app


@celery_app.task(name="trigger.evaluate_scheduled")
def evaluate_scheduled() -> dict[str, str]:
    return {"status": "scheduled_trigger_task_stub"}


@celery_app.task(name="monitor.evaluate_sensitive")
def evaluate_sensitive() -> dict[str, str]:
    return {"status": "sensitive_monitor_task_stub"}


@celery_app.task(name="actions.manager_notification")
def manager_notification_task(execution_id: str, manager: str, reason: str) -> dict[str, str]:
    return {
        "status": "queued",
        "execution_id": execution_id,
        "manager": manager,
        "reason": reason,
    }


@celery_app.task(name="actions.escalation_timer")
def escalation_timer_task(execution_id: str) -> dict[str, str]:
    session = SessionLocal()
    try:
        row = session.get(ActionExecution, execution_id)
        if row is None:
            return {"status": "missing", "execution_id": execution_id}

        if row.status == ActionExecutionStatus.AWAITING_APPROVAL:
            result = dict(row.result or {})
            result["sla_breach"] = True
            result["sla_breach_at"] = datetime.now(UTC).isoformat()
            row.status = ActionExecutionStatus.REJECTED
            row.completed_at = datetime.now(UTC)
            row.result = result
            session.add(row)
            session.commit()
            manager_notification_task.delay(execution_id, "manager-on-call", "Approval SLA breached")
            return {"status": "escalated", "execution_id": execution_id}

        return {"status": "no_action", "execution_id": execution_id, "current_status": row.status.value}
    finally:
        session.close()


@celery_app.task(name="actions.scheduled_reporting")
def scheduled_reporting_task() -> dict[str, str]:
    session = SessionLocal()
    try:
        action = ScheduledReporting(db=session, actor="scheduler")
        execution = action.create_execution_record(
            triggered_by="scheduler",
            payload={"trigger": "periodic"},
            dry_run=False,
        )
        execution.status = ActionExecutionStatus.RUNNING
        session.add(execution)
        session.commit()

        result = action.execute({"execution_id": str(execution.id), "recipient": "compliance@example.com"})
        execution = session.get(ActionExecution, execution.id)
        if execution is not None:
            execution.status = ActionExecutionStatus.COMPLETED
            execution.completed_at = datetime.now(UTC)
            merged = dict(execution.result or {})
            merged["summary"] = result.summary
            execution.result = merged
            session.add(execution)
            session.commit()
        return {"status": "completed", "execution_id": str(execution.id)}
    finally:
        session.close()


@celery_app.task(name="actions.audit_export_delivery")
def audit_export_delivery_task(execution_id: str) -> dict[str, str]:
    session = SessionLocal()
    try:
        row = session.get(ActionExecution, execution_id)
        if row is None:
            return {"status": "missing", "execution_id": execution_id}

        result = dict(row.result or {})
        result["delivery_status"] = "delivered"
        result["delivered_at"] = datetime.now(UTC).isoformat()
        row.result = result
        session.add(row)
        session.commit()
        return {"status": "delivered", "execution_id": execution_id}
    finally:
        session.close()
