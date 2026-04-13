from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from app.agentic.db_models import AgenticSensitiveAlertModel
from app.agentic.models.sensitive_event import AlertModel, AlertSeverity, SensitiveAccessEvent
from app.core.redis_client import redis_client
from app.db.session import SessionLocal


@dataclass
class PatternResult:
    name: str
    severity: AlertSeverity
    detail: str


class PatternDetector:
    async def detect(self, event: SensitiveAccessEvent) -> PatternResult | None:
        raise NotImplementedError


class VolumeSpike(PatternDetector):
    async def detect(self, event: SensitiveAccessEvent) -> PatternResult | None:
        key = (
            f"monitor:vol:{event.tenant_id}:{event.user_alias}:"
            f"{datetime.now(tz=UTC).strftime('%Y%m%d%H')}"
        )
        count = redis_client.client.incr(key)
        redis_client.client.expire(key, 3600)
        if count > 50:
            return PatternResult("volume_spike", AlertSeverity.CRITICAL, f"count={count}")
        if count > 25:
            return PatternResult("volume_spike", AlertSeverity.HIGH, f"count={count}")
        if count > 10:
            return PatternResult("volume_spike", AlertSeverity.MEDIUM, f"count={count}")
        return None


class AfterHoursAccess(PatternDetector):
    async def detect(self, event: SensitiveAccessEvent) -> PatternResult | None:
        hour = event.timestamp.hour
        if hour < 7 or hour > 21:
            return PatternResult("after_hours", AlertSeverity.MEDIUM, f"hour={hour}")
        return None


class BulkResultAccess(PatternDetector):
    async def detect(self, event: SensitiveAccessEvent) -> PatternResult | None:
        if event.result_row_count > 50:
            return PatternResult("bulk_result", AlertSeverity.HIGH, "row_count>50")
        if event.result_row_count > 20:
            return PatternResult("bulk_result", AlertSeverity.MEDIUM, "row_count>20")
        return None


class BoundaryProbing(PatternDetector):
    async def detect(self, event: SensitiveAccessEvent) -> PatternResult | None:
        field_set_hash = hashlib.sha256(",".join(sorted(event.fields_accessed)).encode()).hexdigest()[:16]
        key = f"monitor:boundary:{event.tenant_id}:{event.user_alias}:{event.data_subject_alias}"
        redis_client.client.rpush(key, field_set_hash)
        redis_client.client.expire(key, 600)
        recent = redis_client.client.lrange(key, 0, -1)
        unique_count = len(set(recent))
        if len(recent) >= 5 and unique_count >= 4:
            return PatternResult("boundary_probing", AlertSeverity.HIGH, "field-set variance")
        return None


class CrossContextAccess(PatternDetector):
    async def detect(self, event: SensitiveAccessEvent) -> PatternResult | None:
        key = f"monitor:ctx:{event.tenant_id}:{event.user_alias}"
        redis_client.client.rpush(key, event.department)
        redis_client.client.expire(key, 30 * 24 * 3600)
        recent = redis_client.client.lrange(key, -100, -1)
        if recent and recent.count(event.department) < 2:
            return PatternResult("cross_context", AlertSeverity.MEDIUM, "unusual department context")
        return None


class SeverityCalculator:
    def calculate(self, detected_patterns: list[PatternResult]) -> AlertSeverity:
        if not detected_patterns:
            return AlertSeverity.LOW

        severities = [pattern.severity for pattern in detected_patterns]
        if AlertSeverity.CRITICAL in severities:
            return AlertSeverity.CRITICAL
        if AlertSeverity.HIGH in severities and len(detected_patterns) > 1:
            return AlertSeverity.CRITICAL
        if severities.count(AlertSeverity.MEDIUM) >= 2:
            return AlertSeverity.HIGH
        if AlertSeverity.HIGH in severities:
            return AlertSeverity.HIGH
        if AlertSeverity.MEDIUM in severities:
            return AlertSeverity.MEDIUM
        return AlertSeverity.LOW


class AlertRouter:
    async def route(self, alert: AlertModel) -> None:
        db = SessionLocal()
        try:
            db.merge(
                AgenticSensitiveAlertModel(
                    alert_id=alert.alert_id,
                    tenant_id=str(alert.tenant_id),
                    user_alias=alert.user_alias,
                    session_id=alert.session_id,
                    severity=alert.severity.value,
                    patterns=alert.patterns,
                    status=alert.status,
                    alert_metadata=alert.metadata,
                    created_at=alert.created_at,
                )
            )
            db.commit()
        finally:
            db.close()

        if alert.severity in {AlertSeverity.HIGH, AlertSeverity.CRITICAL}:
            redis_client.client.setex(
                f"agentic:session_flagged:{alert.tenant_id}:{alert.session_id}",
                6 * 3600,
                "1",
            )
        if alert.severity == AlertSeverity.CRITICAL:
            auto_suspend = bool(alert.metadata.get("auto_suspend", False))
            if auto_suspend:
                redis_client.client.setex(
                    f"agentic:session_suspended:{alert.tenant_id}:{alert.session_id}",
                    6 * 3600,
                    "1",
                )


class SensitiveFieldMonitor:
    def __init__(self) -> None:
        self._detectors = [
            VolumeSpike(),
            AfterHoursAccess(),
            BulkResultAccess(),
            BoundaryProbing(),
            CrossContextAccess(),
        ]
        self._severity = SeverityCalculator()
        self._router = AlertRouter()

    async def emit(self, event: SensitiveAccessEvent) -> AlertModel | None:
        pattern_hits: list[PatternResult] = []
        for detector in self._detectors:
            result = await detector.detect(event)
            if result is not None:
                pattern_hits.append(result)

        severity = self._severity.calculate(pattern_hits)
        if severity == AlertSeverity.LOW:
            return None

        alert = AlertModel(
            alert_id=f"alert_{hashlib.sha256((event.session_id + event.user_alias + event.timestamp.isoformat()).encode()).hexdigest()[:16]}",
            tenant_id=event.tenant_id,
            user_alias=event.user_alias,
            session_id=event.session_id,
            severity=severity,
            patterns=[item.name for item in pattern_hits],
            status="open",
            metadata={
                "query_type": event.query_type,
                "result_row_count": event.result_row_count,
                "connector_type": event.connector_type,
                "source_alias": event.source_alias,
                "execution_time_ms": event.execution_time_ms,
                "details": [item.detail for item in pattern_hits],
            },
        )
        await self._router.route(alert)
        return alert
