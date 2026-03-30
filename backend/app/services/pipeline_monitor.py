"""Service for emitting pipeline execution events to Redis pub/sub."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import  Any

from app.core.redis_client import redis_client
from app.schemas.pipeline_monitor import (
    PipelineCompleteEvent,
    PipelineMetadata,
    PipelineStageEvent,
)


class PipelineMonitorService:
    """Service for emitting pipeline events to Redis pub/sub channels."""

    CHANNEL_PREFIX = "pipeline:"

    def _publish(self, pipeline_id: str, event: dict[str, Any]) -> None:
        """
        Publish event to Redis pub/sub channel.

        Fails silently to avoid breaking pipeline execution if Redis is unavailable.
        """
        try:
            channel = f"{self.CHANNEL_PREFIX}{pipeline_id}"
            redis_client.client.publish(channel, json.dumps(event))
        except Exception:
            # Silently fail - monitoring should never break the pipeline
            pass

    def emit_pipeline_start(
        self,
        pipeline_id: str,
        tenant_id: str,
        user_id: str,
        session_id: str,
        query_text: str,
    ) -> None:
        """Emit initial pipeline metadata when execution begins."""
        metadata = PipelineMetadata(
            pipeline_id=pipeline_id,
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            query_text=query_text,
            started_at=datetime.now(tz=UTC),
        )
        self._publish(
            pipeline_id, {"type": "pipeline_start", "data": metadata.model_dump(mode="json")}
        )

    def emit_stage_event(
        self,
        pipeline_id: str,
        stage_name: str,
        stage_index: int,
        status: str,
        duration_ms: int | None = None,
        metadata: dict | None = None,
        error_message: str | None = None,
    ) -> None:
        """Emit stage-level event (started/completed/error/skipped)."""
        event = PipelineStageEvent(
            event_id=str(uuid.uuid4()),
            pipeline_id=pipeline_id,
            stage_name=stage_name,
            stage_index=stage_index,
            status=status,  # type: ignore
            timestamp=datetime.now(tz=UTC),
            duration_ms=duration_ms,
            metadata=metadata or {},
            error_message=error_message,
        )
        self._publish(
            pipeline_id, {"type": "stage_event", "data": event.model_dump(mode="json")}
        )

    def emit_pipeline_complete(
        self,
        pipeline_id: str,
        status: str,
        total_duration_ms: int,
        final_message: str | None = None,
    ) -> None:
        """Emit pipeline completion event (success/error)."""
        event = PipelineCompleteEvent(
            pipeline_id=pipeline_id,
            status=status,  # type: ignore
            total_duration_ms=total_duration_ms,
            final_message=final_message,
        )
        self._publish(
            pipeline_id,
            {"type": "pipeline_complete", "data": event.model_dump(mode="json")},
        )


pipeline_monitor = PipelineMonitorService()
