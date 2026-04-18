from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ActionExecuteRequest(BaseModel):
    action_names: list[str] = Field(min_length=1)
    persona: str
    payload: dict[str, Any] = Field(default_factory=dict)
    mode: str = Field(default="sequential", pattern="^(sequential|parallel)$")


class ActionExecutionResponse(BaseModel):
    execution_id: str
    status: str
    preview_only: bool
    result: dict[str, Any] = Field(default_factory=dict)


class ActionApprovalRequest(BaseModel):
    actor_user_id: str


class ActionRejectionRequest(BaseModel):
    actor_user_id: str
    reason: str | None = None
