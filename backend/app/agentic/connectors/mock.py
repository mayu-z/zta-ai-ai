from __future__ import annotations

from datetime import UTC, datetime
import time
from typing import Any

from app.agentic.models.execution_plan import ReadExecutionPlan, WriteExecutionPlan

from .base import BaseConnector, ConnectorHealth, HealthStatus, RawResult, WriteResult


class MockConnector(BaseConnector):
    """Deterministic connector for tests and local fallback execution."""

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def discover_schema(self) -> dict[str, Any]:
        schemas = self._config.get("mock_schema")
        if isinstance(schemas, dict):
            return schemas
        return {
            "default": {
                "id": {"type": "string", "classification": "IDENTIFIER", "nullable": False},
                "value": {"type": "string", "classification": "GENERAL", "nullable": True},
            }
        }

    async def execute(self, plan: ReadExecutionPlan) -> RawResult:
        self._validate_scope(plan.scope)
        self._validate_scope_filters(plan.filters, plan.scope, plan.scope_filters_required)
        self._validate_filter_values(plan.filters)

        started = time.perf_counter()
        data = self._config.get("mock_rows", {})
        rows = data.get(plan.entity, []) if isinstance(data, dict) else []
        if not isinstance(rows, list):
            rows = []

        limited = rows[plan.offset : plan.offset + plan.limit]
        elapsed = (time.perf_counter() - started) * 1000
        return RawResult(
            rows=[dict(item) for item in limited if isinstance(item, dict)],
            row_count=len(limited),
            execution_time_ms=elapsed,
            source_schema=f"mock:{plan.entity}",
        )

    async def write(self, plan: WriteExecutionPlan) -> WriteResult:
        self._validate_scope(plan.scope)
        self._validate_scope_filters(plan.filters, plan.scope, plan.scope_filters_required)
        return WriteResult(rows_affected=1, generated_id="mock-generated-id", execution_time_ms=1.0)

    async def health_check(self) -> ConnectorHealth:
        return ConnectorHealth(
            status=HealthStatus.HEALTHY,
            latency_ms=0.5,
            last_checked_at=datetime.now(tz=UTC),
        )
