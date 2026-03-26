import os

import pytest


os.environ["DATABASE_URL"] = "sqlite:///./test_zta.db"
os.environ["REDIS_URL"] = "redis://localhost:6399/0"
os.environ["CELERY_BROKER_URL"] = "redis://localhost:6399/1"
os.environ["CELERY_RESULT_BACKEND"] = "redis://localhost:6399/2"
os.environ["USE_MOCK_GOOGLE_OAUTH"] = "true"
os.environ["JWT_SECRET_KEY"] = "test-secret"

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.core.redis_client import redis_client  # noqa: E402
from app.db.models import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from scripts.seed_data import seed  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_state():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    seed()
    redis_client._redis = None
    yield


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
