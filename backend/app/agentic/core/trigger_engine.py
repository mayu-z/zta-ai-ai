from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.agentic.core.action_registry import ActionRegistry
from app.core.redis_client import redis_client
from app.tasks.celery_app import celery_app


@dataclass
class TriggerExecution:
    action_id: str
    tenant_id: str
    fired_at: datetime
    queued_count: int


class TriggerEngine:
    def __init__(self, registry: ActionRegistry) -> None:
        self._registry = registry

    async def run_scheduled(self, tenant_id: str) -> TriggerExecution:
        key = f"trigger:scheduled:{tenant_id}:{datetime.now(tz=UTC).strftime('%Y%m%d%H')}"
        redis_client.client.incr(key)
        redis_client.client.expire(key, 3600)
        return TriggerExecution(
            action_id="scheduled",
            tenant_id=tenant_id,
            fired_at=datetime.now(tz=UTC),
            queued_count=0,
        )

    async def poll_events(self, tenant_id: str) -> TriggerExecution:
        key = f"trigger:event:{tenant_id}:{datetime.now(tz=UTC).strftime('%Y%m%d%H%M')}"
        redis_client.client.incr(key)
        redis_client.client.expire(key, 1800)
        return TriggerExecution(
            action_id="event",
            tenant_id=tenant_id,
            fired_at=datetime.now(tz=UTC),
            queued_count=0,
        )

    async def evaluate_thresholds(self, tenant_id: str) -> TriggerExecution:
        key = f"trigger:threshold:{tenant_id}:{datetime.now(tz=UTC).strftime('%Y%m%d%H%M')}"
        redis_client.client.incr(key)
        redis_client.client.expire(key, 1800)
        return TriggerExecution(
            action_id="threshold",
            tenant_id=tenant_id,
            fired_at=datetime.now(tz=UTC),
            queued_count=0,
        )


@celery_app.task(name="trigger_engine.run_scheduled")
def run_scheduled_task(tenant_id: str) -> dict[str, Any]:
    redis_client.client.rpush("trigger:tasks", f"scheduled:{tenant_id}")
    return {"status": "queued", "type": "scheduled", "tenant_id": tenant_id}


@celery_app.task(name="trigger_engine.poll_events")
def poll_events_task(tenant_id: str) -> dict[str, Any]:
    redis_client.client.rpush("trigger:tasks", f"event:{tenant_id}")
    return {"status": "queued", "type": "event", "tenant_id": tenant_id}


@celery_app.task(name="trigger_engine.evaluate_thresholds")
def evaluate_thresholds_task(tenant_id: str) -> dict[str, Any]:
    redis_client.client.rpush("trigger:tasks", f"threshold:{tenant_id}")
    return {"status": "queued", "type": "threshold", "tenant_id": tenant_id}


@celery_app.task(name="trigger_engine.execute_for_user")
def execute_for_user_task(tenant_id: str, action_id: str, user_alias: str, trigger_context: dict[str, Any]) -> dict[str, Any]:
    dedup_key = f"trigger_dedup:{tenant_id}:{action_id}:{user_alias}:{datetime.now(tz=UTC).strftime('%Y%m%d')}"
    if redis_client.client.exists(dedup_key):
        return {"status": "deduped", "tenant_id": tenant_id, "action_id": action_id, "user_alias": user_alias}

    redis_client.client.setex(dedup_key, 3600, "1")
    redis_client.client.rpush(
        "trigger:execute",
        f"{tenant_id}:{action_id}:{user_alias}:{trigger_context.get('stage', 'na')}",
    )
    return {"status": "queued", "tenant_id": tenant_id, "action_id": action_id, "user_alias": user_alias}
