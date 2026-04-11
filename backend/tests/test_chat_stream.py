from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import ZTAError
from app.main import app


def _mock_login(client: TestClient, email: str) -> str:
    response = client.post(
        "/auth/google",
        json={"google_token": f"mock:{email}"},
    )
    assert response.status_code == 200
    return response.json()["jwt"]


def _collect_frames_until_terminal(ws) -> list[dict[str, object]]:
    frames: list[dict[str, object]] = []
    for _ in range(200):
        frame = ws.receive_json()
        frames.append(frame)
        if frame.get("type") in {"done", "error"}:
            return frames
    pytest.fail("Did not receive a terminal websocket frame")


def test_chat_stream_missing_token_returns_error() -> None:
    with TestClient(app) as client:
        with client.websocket_connect("/chat/stream") as websocket:
            frame = websocket.receive_json()

    assert frame["type"] == "error"
    assert frame["message"] == "Missing token"


@pytest.mark.parametrize(
    ("error_code", "expected_fragment"),
    [
        ("DOMAIN_FORBIDDEN", "outside your current access scope"),
        ("DOMAIN_UNDETERMINED", "could not map that question to a known data domain"),
        ("NO_CLAIMS_FOUND", "could not find matching records for that request"),
    ],
)
def test_chat_stream_known_scope_errors_stream_friendly_guidance(
    monkeypatch: pytest.MonkeyPatch,
    error_code: str,
    expected_fragment: str,
) -> None:
    from app.api.routes import chat as chat_route

    def _raise_scope_error(*args, **kwargs):  # noqa: ANN002, ANN003
        raise ZTAError(message="blocked", code=error_code, status_code=403)

    monkeypatch.setattr(chat_route.pipeline_service, "process_query", _raise_scope_error)

    with TestClient(app) as client:
        token = _mock_login(client, "student@ipeds.local")
        with client.websocket_connect(f"/chat/stream?token={token}") as websocket:
            websocket.send_json({"query": "show salary records"})
            frames = _collect_frames_until_terminal(websocket)

    terminal = frames[-1]
    assert terminal["type"] == "done"
    assert terminal["source"] == "policy_guard"

    streamed_text = "".join(
        str(frame.get("content", ""))
        for frame in frames
        if frame.get("type") == "token"
    ).lower()
    assert expected_fragment in streamed_text
    assert all(frame.get("type") != "error" for frame in frames)


def test_chat_stream_unmapped_zta_error_returns_error_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import chat as chat_route

    def _raise_unmapped_error(*args, **kwargs):  # noqa: ANN002, ANN003
        raise ZTAError(message="raw pipeline failure", code="UNMAPPED_CODE", status_code=400)

    monkeypatch.setattr(chat_route.pipeline_service, "process_query", _raise_unmapped_error)

    with TestClient(app) as client:
        token = _mock_login(client, "student@ipeds.local")
        with client.websocket_connect(f"/chat/stream?token={token}") as websocket:
            websocket.send_json({"query": "any query"})
            frame = websocket.receive_json()

    assert frame["type"] == "error"
    assert frame["message"] == "raw pipeline failure"