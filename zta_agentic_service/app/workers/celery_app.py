from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery("zta_agentic", broker=settings.broker_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
celery_app.autodiscover_tasks(["app.workers"])
