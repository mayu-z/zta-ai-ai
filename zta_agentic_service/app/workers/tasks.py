from app.workers.celery_app import celery_app


@celery_app.task(name="trigger.evaluate_scheduled")
def evaluate_scheduled() -> dict[str, str]:
    return {"status": "scheduled_trigger_task_stub"}


@celery_app.task(name="monitor.evaluate_sensitive")
def evaluate_sensitive() -> dict[str, str]:
    return {"status": "sensitive_monitor_task_stub"}
