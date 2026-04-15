from __future__ import annotations

import json
from typing import Any

from redis import Redis

from app.core.config import get_settings


class RegistryCache:
    def __init__(self, redis_client: Redis | None = None) -> None:
        settings = get_settings()
        self.redis = redis_client or Redis.from_url(settings.redis_url, decode_responses=True)

    @staticmethod
    def _key(tenant_id: str, agent_id: str, definition_version: str, config_version: str) -> str:
        return f"registry:{tenant_id}:{agent_id}:{definition_version}:{config_version}"

    def get(
        self,
        tenant_id: str,
        agent_id: str,
        definition_version: str,
        config_version: str,
    ) -> dict[str, Any] | None:
        key = self._key(tenant_id, agent_id, definition_version, config_version)
        payload = self.redis.get(key)
        return json.loads(payload) if payload else None

    def set(
        self,
        tenant_id: str,
        agent_id: str,
        definition_version: str,
        config_version: str,
        payload: dict[str, Any],
        ttl_seconds: int = 300,
    ) -> None:
        key = self._key(tenant_id, agent_id, definition_version, config_version)
        self.redis.set(key, json.dumps(payload), ex=ttl_seconds)

    def invalidate_tenant(self, tenant_id: str) -> None:
        cursor = 0
        pattern = f"registry:{tenant_id}:*"
        while True:
            cursor, keys = self.redis.scan(cursor=cursor, match=pattern, count=500)
            if keys:
                self.redis.delete(*keys)
            if cursor == 0:
                break
