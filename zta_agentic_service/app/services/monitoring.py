from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic


@dataclass
class SensitiveAccessEvent:
    tenant_id: str
    user_alias: str
    persona: str
    fields_accessed: list[str]
    data_subject_alias: str
    query_type: str
    result_row_count: int
    timestamp: datetime


class SensitiveMonitorInterceptor:
    def __init__(self) -> None:
        self._event_buffer: list[SensitiveAccessEvent] = []

    def intercept(self, event: SensitiveAccessEvent) -> dict[str, float | str]:
        start = monotonic()
        self._event_buffer.append(event)
        latency_ms = (monotonic() - start) * 1000

        return {
            "status": "accepted",
            "latency_ms": round(latency_ms, 3),
            "target_budget_ms": 20.0,
        }

    def evaluate_rules(self, tenant_id: str, now: datetime | None = None) -> list[dict[str, str]]:
        now = now or datetime.now(UTC)
        relevant = [e for e in self._event_buffer if e.tenant_id == tenant_id]

        alerts: list[dict[str, str]] = []
        for event in relevant:
            if event.result_row_count > 20:
                alerts.append(
                    {
                        "severity": "medium",
                        "rule": "bulk_result_access",
                        "user_alias": event.user_alias,
                        "at": now.isoformat(),
                    }
                )
        return alerts
