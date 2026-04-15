from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import TriggerType
from app.db.models import AgentTriggerRule


class TriggerEngine:
    def __init__(self, db: Session):
        self.db = db

    def evaluate_scheduled_triggers(self) -> list[dict[str, Any]]:
        rows = self.db.scalars(
            select(AgentTriggerRule).where(
                AgentTriggerRule.is_enabled.is_(True),
                AgentTriggerRule.trigger_type == TriggerType.SCHEDULED,
            )
        ).all()

        fired: list[dict[str, Any]] = []
        now = datetime.now(UTC)
        for row in rows:
            row.last_fired_at = now
            fired.append(
                {
                    "rule_id": str(row.id),
                    "tenant_id": str(row.tenant_id),
                    "agent_definition_id": str(row.agent_definition_id),
                }
            )
        return fired

    def evaluate_event_trigger(
        self,
        event_type: str,
        event_data: dict[str, Any],
        tenant_id: str,
    ) -> list[dict[str, Any]]:
        rows = self.db.scalars(
            select(AgentTriggerRule).where(
                AgentTriggerRule.tenant_id == tenant_id,
                AgentTriggerRule.is_enabled.is_(True),
                AgentTriggerRule.trigger_type.in_([TriggerType.EVENT, TriggerType.THRESHOLD]),
            )
        ).all()

        matched: list[dict[str, Any]] = []
        for row in rows:
            condition_type = row.event_condition.get("event_type")
            if condition_type and condition_type != event_type:
                continue
            matched.append(
                {
                    "rule_id": str(row.id),
                    "tenant_id": str(row.tenant_id),
                    "event_type": event_type,
                    "event_data": event_data,
                }
            )
        return matched
