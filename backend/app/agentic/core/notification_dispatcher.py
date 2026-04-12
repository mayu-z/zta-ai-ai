from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.agentic.models.action_config import NotificationConfig
from app.agentic.models.agent_context import AgentResult, RequestContext
from app.core.redis_client import redis_client


@dataclass
class NotificationResult:
    dispatched: bool
    channels: list[str]
    rate_limited: bool
    metadata: dict[str, Any]


class NotificationDispatcher:
    def _rate_key(self, ctx: RequestContext, channel: str) -> str:
        day_key = datetime.now(tz=UTC).strftime("%Y%m%d")
        return f"rate:{ctx.tenant_id}:daily:{channel}:{ctx.user_alias}:{day_key}"

    def _emit(self, channel: str, payload: dict[str, Any]) -> None:
        key = f"notifications:{channel}"
        redis_client.client.rpush(key, json.dumps(payload, sort_keys=True, ensure_ascii=True))

    async def dispatch(
        self,
        config: NotificationConfig,
        result: AgentResult,
        ctx: RequestContext,
    ) -> NotificationResult:
        dispatched_channels: list[str] = []
        rate_limited = False

        for channel in config.channels:
            key = self._rate_key(ctx, channel)
            count = redis_client.client.incr(key)
            ttl = redis_client.client.ttl(key)
            if ttl < 0:
                redis_client.client.expire(key, 24 * 60 * 60)

            if count > 3:
                rate_limited = True
                continue

            payload = {
                "template_id": config.template_id,
                "recipient_resolver": config.recipient_resolver,
                "tenant_id": str(ctx.tenant_id),
                "user_alias": ctx.user_alias,
                "channel": channel,
                "message": result.message,
                "data": result.data or {},
            }
            self._emit(channel, payload)
            dispatched_channels.append(channel)

        return NotificationResult(
            dispatched=bool(dispatched_channels),
            channels=dispatched_channels,
            rate_limited=rate_limited,
            metadata={"workflow_id": result.workflow_id},
        )
