from __future__ import annotations

from typing import Any, Callable

from app.core.config import get_settings

settings = get_settings()


try:
    from celery import Celery
except Exception:  # noqa: BLE001
    Celery = None  # type: ignore[assignment]


class _ImmediateTaskWrapper:
    def __init__(self, fn: Callable[..., Any]) -> None:
        self._fn = fn

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._fn(*args, **kwargs)

    def delay(self, *args: Any, **kwargs: Any) -> Any:
        return self._fn(*args, **kwargs)


class _DummyCelery:
    def task(self, name: str | None = None):
        def decorator(fn: Callable[..., Any]) -> _ImmediateTaskWrapper:
            return _ImmediateTaskWrapper(fn)

        return decorator

    def autodiscover_tasks(self, _packages: list[str]) -> None:
        return None


if Celery is None:
    celery_app = _DummyCelery()
else:
    celery_app = Celery(
        "zta_ai",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
    )

    celery_app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        # Fail fast when broker is unavailable so service-level fallback can persist audit synchronously.
        task_publish_retry=False,
        broker_connection_retry_on_startup=False,
        broker_transport_options={
            "max_retries": 0,
            "socket_connect_timeout": 1,
            "socket_timeout": 1,
        },
    )

    celery_app.autodiscover_tasks(["app.tasks"])
