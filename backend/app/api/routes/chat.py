from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.api.deps import get_current_scope, get_scope_from_token
from app.core.exceptions import ZTAError
from app.db.session import SessionLocal, get_db
from app.schemas.chat import ChatHistoryItem, ChatSuggestion, TokenFrame
from app.schemas.pipeline import ScopeContext
from app.services.history_service import history_service
from app.services.pipeline import pipeline_service
from app.services.rate_limiter import rate_limiter_service
from app.services.suggestions import suggestion_service

router = APIRouter(prefix="/chat", tags=["chat"])


def _friendly_scope_error(scope: ScopeContext, exc: ZTAError) -> str | None:
    allowed_domains = ", ".join(scope.allowed_domains) or "your configured domains"

    if exc.code == "DOMAIN_FORBIDDEN":
        return (
            "That request is outside your current access scope. "
            f"You can ask about: {allowed_domains}. "
            "Try asking for a summary in one of those areas."
        )
    if exc.code == "DOMAIN_UNDETERMINED":
        return (
            "I could not map that question to a known data domain. "
            f"Try mentioning one of your allowed domains: {allowed_domains}."
        )
    if exc.code == "NO_CLAIMS_FOUND":
        return (
            "I could not find matching records for that request in your scoped data. "
            "Try adding a timeframe or asking for a broader summary."
        )
    if exc.code == "STUDENT_SCOPE_BLOCKED":
        return (
            "I can only answer with your own student scope. "
            "Try rephrasing without references to other students or cross-student records."
        )
    if exc.code == "EXEC_AGGREGATE_ONLY":
        return (
            "Your role is configured for aggregate insights only. "
            "Try asking for summaries, trends, or totals instead of individual records."
        )
    if exc.code == "IT_HEAD_CHAT_BLOCKED":
        return (
            "Your role currently has chat access disabled for business-domain queries. "
            "Use the admin observability endpoints or dashboards for this data."
        )
    return None


@router.get("/suggestions", response_model=list[ChatSuggestion])
def suggestions(
    scope: ScopeContext = Depends(get_current_scope),
) -> list[ChatSuggestion]:
    values = suggestion_service.suggestions_for(scope.persona_type)
    return [
        ChatSuggestion(id=f"q{idx + 1}", text=text) for idx, text in enumerate(values)
    ]


@router.get("/history", response_model=list[ChatHistoryItem])
def history(scope: ScopeContext = Depends(get_current_scope)) -> list[ChatHistoryItem]:
    rows = history_service.read_recent(
        scope.tenant_id, scope.user_id, scope.session_id, limit=20
    )
    response: list[ChatHistoryItem] = []
    for row in rows:
        created_at = row.get("created_at")
        parsed = (
            datetime.fromisoformat(created_at)
            if created_at
            else datetime.now(UTC).replace(tzinfo=None)
        )
        response.append(
            ChatHistoryItem(
                role=row.get("role", "assistant"),
                content=row.get("content", ""),
                created_at=parsed,
            )
        )
    return response


@router.websocket("/stream")
async def stream_chat(websocket: WebSocket, token: str = Query(default="")) -> None:
    await websocket.accept()
    db = SessionLocal()
    try:
        if not token:
            await websocket.send_json(
                TokenFrame(type="error", message="Missing token").model_dump()
            )
            await websocket.close(code=1008)
            return

        try:
            scope = get_scope_from_token(db=db, token=token)
        except ZTAError as exc:
            await websocket.send_json(
                TokenFrame(type="error", message=exc.message).model_dump()
            )
            await websocket.close(code=1008)
            return

        while True:
            payload = await websocket.receive_json()
            query_text = str(payload.get("query", "")).strip()
            if not query_text:
                await websocket.send_json(
                    TokenFrame(type="error", message="Query is required").model_dump()
                )
                continue

            try:
                rate_limiter_service.check_and_increment(scope.tenant_id, scope.user_id)
                result = pipeline_service.process_query(
                    db=db, scope=scope, query_text=query_text
                )

                for token_part in result.response_text.split(" "):
                    if not token_part:
                        continue
                    await websocket.send_json(
                        TokenFrame(type="token", content=f"{token_part} ").model_dump()
                    )
                    await asyncio.sleep(0.015)

                await websocket.send_json(
                    TokenFrame(
                        type="done",
                        source=result.source,
                        latency_ms=result.latency_ms,
                    ).model_dump()
                )
            except ZTAError as exc:
                friendly = _friendly_scope_error(scope, exc)
                if friendly is None:
                    await websocket.send_json(
                        TokenFrame(type="error", message=exc.message).model_dump()
                    )
                    continue

                history_service.append(
                    scope.tenant_id,
                    scope.user_id,
                    scope.session_id,
                    "assistant",
                    friendly,
                )

                for token_part in friendly.split(" "):
                    if not token_part:
                        continue
                    await websocket.send_json(
                        TokenFrame(type="token", content=f"{token_part} ").model_dump()
                    )
                    await asyncio.sleep(0.015)

                await websocket.send_json(
                    TokenFrame(type="done", source="policy_guard", latency_ms=0).model_dump()
                )
    except WebSocketDisconnect:
        return
    finally:
        db.close()
