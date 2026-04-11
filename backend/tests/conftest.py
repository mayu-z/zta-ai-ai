import os
import re
from unittest.mock import MagicMock

import pytest


os.environ["DATABASE_URL"] = "sqlite:///./test_zta.db"
os.environ["REDIS_URL"] = "redis://localhost:6399/0"
os.environ["CELERY_BROKER_URL"] = "redis://localhost:6399/1"
os.environ["CELERY_RESULT_BACKEND"] = "redis://localhost:6399/2"
os.environ["AUTH_PROVIDER"] = "mock_google"
os.environ["USE_MOCK_GOOGLE_OAUTH"] = "true"
os.environ["DEV_AUTO_CREATE_TENANT_ON_LOGIN"] = "true"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-that-is-at-least-thirty-two-chars"
os.environ["SLM_PROVIDER"] = "nvidia"
os.environ["SLM_API_KEY"] = "test-key"

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.core.redis_client import redis_client  # noqa: E402
from app.db.models import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from scripts.ipeds_import import seed_ipeds_claims  # noqa: E402


def _bootstrap_test_dataset() -> None:
    db = SessionLocal()
    try:
        seed_ipeds_claims(db, profile="test")
        db.commit()
    finally:
        db.close()


def _create_mock_slm_response(slot_count: int = 2) -> MagicMock:
    """Create a mock OpenAI API response with slot placeholders."""
    slots = " and ".join(f"[SLOT_{i+1}]" for i in range(slot_count))
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content=f"The requested data shows {slots}."))
    ]
    return mock_response


@pytest.fixture(autouse=True)
def _reset_state():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    _bootstrap_test_dataset()
    redis_client._redis = None
    yield


@pytest.fixture(autouse=True)
def mock_slm_client():
    """Mock the SLM client for all tests by patching _get_client method."""
    from app.slm.simulator import slm_simulator

    mock_client = MagicMock()

    def create_completion(*args, **kwargs):
        messages = kwargs.get("messages", [])
        user_msg = next((m for m in messages if m.get("role") == "user"), {})
        content = user_msg.get("content", "")

        # Parse the explicit required slot count from the simulator prompt.
        slot_count = 0
        required_match = re.search(r"exactly\s+(\d+)\s+slot", content, re.IGNORECASE)
        if required_match:
            slot_count = int(required_match.group(1))
        else:
            available_match = re.search(
                r"Data slots available \((\d+)\s+slots total",
                content,
                re.IGNORECASE,
            )
            if available_match:
                slot_count = int(available_match.group(1))

        if slot_count <= 0:
            slot_count = 2

        return _create_mock_slm_response(slot_count)

    mock_client.chat.completions.create = MagicMock(side_effect=create_completion)

    # Patch _get_client to always return mock - this prevents real API calls
    original_get_client = slm_simulator._get_client
    slm_simulator._get_client = lambda: mock_client

    yield mock_client

    # Reset after test
    slm_simulator._get_client = original_get_client


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def db(db_session):
    return db_session
