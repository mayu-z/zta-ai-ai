from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Protocol, cast


class RedisError(Exception):
    pass


class RedisPubSubProtocol(Protocol):
    def psubscribe(self, *patterns: str) -> Any:
        ...

    def get_message(self, timeout: float | None = None) -> dict[str, Any] | None:
        ...

    def punsubscribe(self, *patterns: str) -> Any:
        ...

    def close(self) -> Any:
        ...


class RedisProtocol(Protocol):
    def get(self, key: str) -> str | None:
        ...

    def setex(self, key: str, ttl_seconds: int, value: str) -> Any:
        ...

    def set(self, key: str, value: str) -> Any:
        ...

    def incr(self, key: str) -> int:
        ...

    def expire(self, key: str, ttl_seconds: int) -> Any:
        ...

    def ttl(self, key: str) -> int:
        ...

    def delete(self, *keys: str) -> int:
        ...

    def exists(self, key: str) -> int:
        ...

    def ping(self) -> Any:
        ...

    def rpush(self, key: str, value: str) -> int:
        ...

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        ...

    def publish(self, channel: str, message: str) -> int:
        ...

    def pubsub(self) -> RedisPubSubProtocol:
        ...

    def scan(
        self, cursor: int = 0, match: str | None = None, count: int | None = None
    ) -> tuple[int, list[str]]:
        ...

try:
    from redis import Redis as RedisSync
    from redis.exceptions import RedisError as RedisClientError
except Exception:  # noqa: BLE001
    RedisSync = None
    RedisClientError = RedisError


from app.core.config import get_settings


@dataclass
class _ValueEntry:
    value: str
    expires_at: float | None


class InMemoryRedis:
    def __init__(self) -> None:
        self._kv: dict[str, _ValueEntry] = {}
        self._lists: dict[str, list[str]] = {}
        self._lock = threading.Lock()

    def _cleanup_if_expired(self, key: str) -> None:
        entry = self._kv.get(key)
        if not entry:
            return
        if entry.expires_at is not None and entry.expires_at <= time.time():
            self._kv.pop(key, None)

    def get(self, key: str) -> str | None:
        with self._lock:
            self._cleanup_if_expired(key)
            entry = self._kv.get(key)
            return entry.value if entry else None

    def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        with self._lock:
            self._kv[key] = _ValueEntry(
                value=value, expires_at=time.time() + ttl_seconds
            )
        return True

    def set(self, key: str, value: str) -> bool:
        with self._lock:
            self._kv[key] = _ValueEntry(value=value, expires_at=None)
        return True

    def incr(self, key: str) -> int:
        with self._lock:
            self._cleanup_if_expired(key)
            current = self._kv.get(key)
            number = int(current.value) if current else 0
            number += 1
            expires_at = current.expires_at if current else None
            self._kv[key] = _ValueEntry(value=str(number), expires_at=expires_at)
            return number

    def expire(self, key: str, ttl_seconds: int) -> bool:
        with self._lock:
            self._cleanup_if_expired(key)
            if key not in self._kv:
                return False
            self._kv[key].expires_at = time.time() + ttl_seconds
            return True

    def ttl(self, key: str) -> int:
        with self._lock:
            self._cleanup_if_expired(key)
            if key not in self._kv:
                return -2
            expires_at = self._kv[key].expires_at
            if expires_at is None:
                return -1
            remaining = int(expires_at - time.time())
            return remaining if remaining > 0 else -2

    def delete(self, *keys: str) -> int:
        with self._lock:
            existed = 0
            for key in keys:
                if key in self._kv or key in self._lists:
                    existed += 1
                self._kv.pop(key, None)
                self._lists.pop(key, None)
            return existed

    def exists(self, key: str) -> int:
        with self._lock:
            self._cleanup_if_expired(key)
            return 1 if key in self._kv or key in self._lists else 0

    def ping(self) -> bool:
        return True

    def rpush(self, key: str, value: str) -> int:
        with self._lock:
            self._lists.setdefault(key, []).append(value)
            return len(self._lists[key])

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        with self._lock:
            data = self._lists.get(key, [])
            if end == -1:
                return data[start:]
            return data[start : end + 1]

    def publish(self, channel: str, message: str) -> int:
        _ = channel
        _ = message
        return 0

    def pubsub(self) -> "InMemoryPubSub":
        return InMemoryPubSub()

    def scan(
        self, cursor: int = 0, match: str | None = None, count: int | None = None
    ) -> tuple[int, list[str]]:
        _ = cursor
        _ = match
        _ = count
        return 0, []


class InMemoryPubSub:
    def psubscribe(self, *patterns: str) -> None:
        _ = patterns

    def get_message(self, timeout: float | None = None) -> dict[str, Any] | None:
        _ = timeout
        return None

    def punsubscribe(self, *patterns: str) -> None:
        _ = patterns

    def close(self) -> None:
        return None


class RedisClient:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._redis: RedisProtocol | None = None
        self._lock = threading.Lock()

    def _connect(self) -> RedisProtocol:
        if RedisSync is None:
            return InMemoryRedis()
        try:
            candidate = RedisSync.from_url(self._settings.redis_url, decode_responses=True)
            candidate.ping()
            return cast(RedisProtocol, candidate)
        except RedisClientError:
            return InMemoryRedis()

    @property
    def client(self) -> RedisProtocol:
        with self._lock:
            if self._redis is None:
                self._redis = self._connect()
            return self._redis

    def get_json(self, key: str) -> dict[str, Any] | None:
        payload = self.client.get(key)
        if payload is None:
            return None
        return cast(dict[str, Any], json.loads(payload))

    def set_json(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        self.client.setex(
            key, ttl_seconds, json.dumps(value, ensure_ascii=True, sort_keys=True)
        )


redis_client = RedisClient()
