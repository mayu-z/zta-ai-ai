import os
from unittest.mock import MagicMock, patch

import pytest


os.environ["DATABASE_URL"] = "sqlite:///./test_zta.db"
os.environ["REDIS_URL"] = "redis://localhost:6399/0"
os.environ["CELERY_BROKER_URL"] = "redis://localhost:6399/1"
os.environ["CELERY_RESULT_BACKEND"] = "redis://localhost:6399/2"
os.environ["USE_MOCK_GOOGLE_OAUTH"] = "true"
os.environ["JWT_SECRET_KEY"] = "test-secret"
os.environ["SLM_PROVIDER"] = "nvidia"
os.environ["SLM_API_KEY"] = "test-key"

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.core.redis_client import redis_client  # noqa: E402
from app.db.models import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from scripts.seed_data import seed  # noqa: E402


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
    seed()
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

        # Count slots from the prompt
        slot_count = content.count("[SLOT_")
        if slot_count == 0:
            slot_count = 2

        return _create_mock_slm_response(slot_count)

    mock_client.chat.completions.create = MagicMock(side_effect=create_completion)

    # Directly inject mock client
    original_client = slm_simulator._client
    slm_simulator._client = mock_client

    yield mock_client

    # Reset after test
    slm_simulator._client = original_client


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
