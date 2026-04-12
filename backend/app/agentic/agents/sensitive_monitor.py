from __future__ import annotations

from dataclasses import dataclass

from app.agentic.core.sensitive_field_monitor import SensitiveFieldMonitor
from app.agentic.models.sensitive_event import AlertModel, SensitiveAccessEvent


@dataclass
class SensitiveMonitorAgent:
    """Infrastructure facade for sensitive field anomaly processing."""

    monitor: SensitiveFieldMonitor

    async def process(self, event: SensitiveAccessEvent) -> AlertModel | None:
        return await self.monitor.emit(event)
