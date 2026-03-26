from datetime import datetime

from pydantic import BaseModel


class ChatSuggestion(BaseModel):
    id: str
    text: str


class ChatHistoryItem(BaseModel):
    role: str
    content: str
    created_at: datetime


class ChatResponse(BaseModel):
    answer: str
    source: str
    latency_ms: int


class TokenFrame(BaseModel):
    type: str
    content: str | None = None
    source: str | None = None
    latency_ms: int | None = None
    message: str | None = None
