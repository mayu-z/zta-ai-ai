from datetime import datetime

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    code: str
    message: str


class Pagination(BaseModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=500)


class TraceEnvelope(BaseModel):
    trace_id: str
    execution_id: str | None = None
    timestamp: datetime
