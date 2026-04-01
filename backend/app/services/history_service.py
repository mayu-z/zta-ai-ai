from __future__ import annotations

import json
from datetime import UTC, datetime

from app.core.redis_client import redis_client


class HistoryService:
    def _key(self, tenant_id: str, user_id: str, session_id: str) -> str:
        date_key = datetime.now(tz=UTC).strftime("%Y%m%d")
        return f"history:{tenant_id}:{user_id}:{session_id}:{date_key}"

    def append(
        self, tenant_id: str, user_id: str, session_id: str, role: str, content: str
    ) -> None:
        key = self._key(tenant_id, user_id, session_id)
        payload = {
            "role": role,
            "content": content,
            "created_at": datetime.now(tz=UTC).isoformat(),
        }
        redis_client.client.rpush(key, json.dumps(payload, ensure_ascii=True))
        redis_client.client.expire(key, 24 * 60 * 60)

    def read_recent(
        self, tenant_id: str, user_id: str, session_id: str, limit: int = 20
    ) -> list[dict]:
        key = self._key(tenant_id, user_id, session_id)
        rows = redis_client.client.lrange(key, max(0, -limit), -1)
        output: list[dict] = []
        for row in rows:
            try:
                output.append(json.loads(row))
            except json.JSONDecodeError:
                continue
        return output


history_service = HistoryService()
