from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.redis_client import redis_client
from app.db.models import IntentCacheEntry


class IntentCacheService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _redis_key(self, tenant_id: str, intent_hash: str) -> str:
        return f"intent:{tenant_id}:{intent_hash}"

    def get(self, db: Session, tenant_id: str, intent_hash: str) -> dict[str, Any] | None:
        redis_key = self._redis_key(tenant_id, intent_hash)
        cached = redis_client.get_json(redis_key)
        if cached:
            redis_client.client.expire(redis_key, self.settings.intent_cache_ttl_seconds)
            return cached

        row = db.scalar(
            select(IntentCacheEntry).where(
                IntentCacheEntry.intent_hash == intent_hash,
                IntentCacheEntry.tenant_id == tenant_id,
            )
        )
        if not row:
            return None

        now = datetime.now(tz=UTC)
        if row.expires_at <= now:
            return None

        row.hit_count += 1
        row.expires_at = now + timedelta(seconds=self.settings.intent_cache_ttl_seconds)
        db.add(row)
        db.commit()

        payload = {
            "response_template": row.response_template,
            "compiled_query": row.compiled_query,
        }
        redis_client.set_json(redis_key, payload, self.settings.intent_cache_ttl_seconds)
        return payload

    def set(
        self,
        db: Session,
        tenant_id: str,
        intent_hash: str,
        normalized_intent: dict[str, Any],
        response_template: str,
        compiled_query: dict[str, Any],
    ) -> None:
        expires_at = datetime.now(tz=UTC) + timedelta(seconds=self.settings.intent_cache_ttl_seconds)

        row = db.scalar(select(IntentCacheEntry).where(IntentCacheEntry.intent_hash == intent_hash))
        if row:
            row.response_template = response_template
            row.compiled_query = compiled_query
            row.expires_at = expires_at
            row.hit_count += 1
            row.normalized_intent = normalized_intent
        else:
            row = IntentCacheEntry(
                intent_hash=intent_hash,
                tenant_id=tenant_id,
                normalized_intent=normalized_intent,
                response_template=response_template,
                compiled_query=compiled_query,
                hit_count=1,
                expires_at=expires_at,
            )
        db.add(row)
        db.commit()

        redis_payload = {
            "response_template": response_template,
            "compiled_query": compiled_query,
        }
        redis_client.set_json(self._redis_key(tenant_id, intent_hash), redis_payload, self.settings.intent_cache_ttl_seconds)


intent_cache_service = IntentCacheService()
