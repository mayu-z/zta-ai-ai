"""Schemas for real-time pipeline monitoring and event streaming."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class PipelineStageEvent(BaseModel):
    """Event emitted at each pipeline stage transition."""

    event_id: str
    pipeline_id: str
    stage_name: str
    stage_index: int
    status: Literal["started", "completed", "error", "skipped"]
    timestamp: datetime
    duration_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None


class PipelineMetadata(BaseModel):
    """Initial metadata emitted when pipeline execution begins."""

    pipeline_id: str
    tenant_id: str
    user_id: str
    session_id: str
    query_text: str
    started_at: datetime


class PipelineCompleteEvent(BaseModel):
    """Final event emitted when pipeline completes or fails."""

    pipeline_id: str
    status: Literal["success", "error"]
    total_duration_ms: int
    final_message: str | None = None
