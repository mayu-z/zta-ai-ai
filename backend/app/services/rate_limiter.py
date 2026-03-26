from __future__ import annotations

from datetime import datetime

from app.core.config import get_settings
from app.core.exceptions import RateLimitError
from app.core.redis_client import redis_client


class RateLimiterService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def check_and_increment(self, tenant_id: str, user_id: str) -> int:
        day_key = datetime.utcnow().strftime("%Y%m%d")
        key = f"rate:{tenant_id}:{user_id}:{day_key}"

        count = redis_client.client.incr(key)
        ttl = redis_client.client.ttl(key)
        if ttl < 0:
            redis_client.client.expire(key, 24 * 60 * 60)

        if count > self.settings.daily_query_limit:
            raise RateLimitError(
                message=f"Daily limit exceeded ({self.settings.daily_query_limit} queries)",
                code="DAILY_LIMIT_EXCEEDED",
            )
        return int(count)


rate_limiter_service = RateLimiterService()
