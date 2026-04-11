from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AuditLog
from app.schemas.pipeline import ScopeContext
from app.services.action_orchestrator import action_orchestrator_service


COMPLIANCE_ACTION_IDS = [
    "DSAR_EXECUTE",
    "ERASURE_EXECUTE",
    "INCIDENT_RESPONSE",
    "AUDIT_EXPORT",
    "CONSENT_WITHDRAWAL",
]


class ComplianceOperationsService:
    def get_summary(
        self,
        *,
        scope: ScopeContext,
        db: Session,
        from_at: datetime | None,
        to_at: datetime | None,
        limit: int,
    ) -> dict[str, object]:
        window_from, window_to = self._normalize_window(from_at=from_at, to_at=to_at)
        records = action_orchestrator_service.list_executions_for_tenant(
            db=db,
            tenant_id=scope.tenant_id,
            action_ids=COMPLIANCE_ACTION_IDS,
            from_at=window_from,
            to_at=window_to,
            limit=limit,
        )

        dsar_records = self._filter_records(records=records, action_id="DSAR_EXECUTE")
        erasure_records = self._filter_records(records=records, action_id="ERASURE_EXECUTE")
        incident_records = self._filter_records(records=records, action_id="INCIDENT_RESPONSE")

        summary = {
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "window": {
                "from": window_from.isoformat() if window_from else None,
                "to": window_to.isoformat() if window_to else None,
            },
            "dsar": self._build_action_summary(
                records=dsar_records,
                sla_days=30,
                as_of=window_to or datetime.now(tz=UTC),
            ),
            "erasure": self._build_action_summary(
                records=erasure_records,
                sla_days=45,
                as_of=window_to or datetime.now(tz=UTC),
            ),
            "incidents": self._build_incident_summary(
                records=incident_records,
                as_of=window_to or datetime.now(tz=UTC),
            ),
            "audit": self._audit_event_summary(
                scope=scope,
                db=db,
                from_at=window_from,
                to_at=window_to,
            ),
        }
        return summary

    def generate_forensic_export(
        self,
        *,
        scope: ScopeContext,
        db: Session,
        from_at: datetime,
        to_at: datetime,
        include_action_ids: list[str],
        include_blocked_queries_only: bool,
        max_items: int,
    ) -> dict[str, object]:
        window_from, window_to = self._normalize_window(from_at=from_at, to_at=to_at)
        selected_action_ids = [
            value.strip().upper()
            for value in include_action_ids
            if value and value.strip()
        ] or list(COMPLIANCE_ACTION_IDS)

        action_records = action_orchestrator_service.list_executions_for_tenant(
            db=db,
            tenant_id=scope.tenant_id,
            action_ids=selected_action_ids,
            from_at=window_from,
            to_at=window_to,
            limit=max_items,
        )

        audit_events = self._fetch_audit_events(
            scope=scope,
            db=db,
            from_at=window_from,
            to_at=window_to,
            include_blocked_queries_only=include_blocked_queries_only,
            max_items=max_items,
        )

        compliance_summary = self.get_summary(
            scope=scope,
            db=db,
            from_at=window_from,
            to_at=window_to,
            limit=max_items,
        )

        export_id = f"forensic_{datetime.now(tz=UTC).strftime('%Y%m%d%H%M%S')}"
        payload = {
            "export_id": export_id,
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "tenant_id": scope.tenant_id,
            "requested_by": scope.user_id,
            "window": {
                "from": window_from.isoformat(),
                "to": window_to.isoformat(),
            },
            "summary": {
                "action_count": len(action_records),
                "audit_event_count": len(audit_events),
                "blocked_audit_event_count": sum(
                    1 for event in audit_events if event["was_blocked"]
                ),
            },
            "compliance_summary": compliance_summary,
            "actions": action_records,
            "audit_events": audit_events,
        }

        signature_material = json.dumps(
            {
                "tenant_id": payload["tenant_id"],
                "window": payload["window"],
                "summary": payload["summary"],
                "actions": payload["actions"],
                "audit_events": payload["audit_events"],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        payload["signature"] = hashlib.sha256(
            signature_material.encode("utf-8")
        ).hexdigest()
        return payload

    @staticmethod
    def _normalize_window(
        *,
        from_at: datetime | None,
        to_at: datetime | None,
    ) -> tuple[datetime | None, datetime | None]:
        normalized_from = ComplianceOperationsService._normalize_datetime(from_at)
        normalized_to = ComplianceOperationsService._normalize_datetime(to_at)
        if normalized_from and normalized_to and normalized_from > normalized_to:
            normalized_from, normalized_to = normalized_to, normalized_from
        return normalized_from, normalized_to

    @staticmethod
    def _normalize_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        candidate = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(candidate)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def _filter_records(
        *,
        records: list[dict[str, object]],
        action_id: str,
    ) -> list[dict[str, object]]:
        return [row for row in records if row.get("action_id") == action_id]

    def _build_action_summary(
        self,
        *,
        records: list[dict[str, object]],
        sla_days: int,
        as_of: datetime,
    ) -> dict[str, object]:
        completed_count = 0
        pending_count = 0
        rolled_back_count = 0
        sla_breaches = 0
        duration_seconds: list[float] = []

        for record in records:
            status = str(record.get("status") or "").lower()
            requested_at = self._parse_datetime(record.get("requested_at"))
            output = record.get("output")
            completed_at = None
            if isinstance(output, dict):
                completed_at = self._parse_datetime(output.get("completed_at"))

            if status == "completed":
                completed_count += 1
            elif status in {"awaiting_approval", "executing"}:
                pending_count += 1
            elif status == "rolled_back":
                rolled_back_count += 1

            if requested_at is None:
                continue

            deadline = requested_at + timedelta(days=sla_days)
            if completed_at is not None:
                duration_seconds.append((completed_at - requested_at).total_seconds())
                if completed_at > deadline:
                    sla_breaches += 1
                continue

            if status != "completed" and as_of > deadline:
                sla_breaches += 1

        avg_completion = (
            round(sum(duration_seconds) / len(duration_seconds), 2)
            if duration_seconds
            else None
        )

        return {
            "total_requests": len(records),
            "completed": completed_count,
            "pending": pending_count,
            "rolled_back": rolled_back_count,
            "sla_breaches": sla_breaches,
            "avg_completion_seconds": avg_completion,
        }

    def _build_incident_summary(
        self,
        *,
        records: list[dict[str, object]],
        as_of: datetime,
    ) -> dict[str, object]:
        summary = self._build_action_summary(records=records, sla_days=3, as_of=as_of)
        severities = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for record in records:
            input_payload = record.get("input_payload")
            if not isinstance(input_payload, dict):
                continue
            severity = str(input_payload.get("severity") or "").lower()
            if severity in severities:
                severities[severity] += 1
        summary["by_severity"] = severities
        return summary

    def _audit_event_summary(
        self,
        *,
        scope: ScopeContext,
        db: Session,
        from_at: datetime | None,
        to_at: datetime | None,
    ) -> dict[str, int]:
        filters = [AuditLog.tenant_id == scope.tenant_id]
        if from_at is not None:
            filters.append(AuditLog.created_at >= from_at)
        if to_at is not None:
            filters.append(AuditLog.created_at <= to_at)

        total_events = int(
            db.scalar(select(func.count()).select_from(AuditLog).where(*filters)) or 0
        )
        blocked_events = int(
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(*filters, AuditLog.was_blocked.is_(True))
            )
            or 0
        )

        return {
            "total_query_events": total_events,
            "blocked_query_events": blocked_events,
        }

    def _fetch_audit_events(
        self,
        *,
        scope: ScopeContext,
        db: Session,
        from_at: datetime,
        to_at: datetime,
        include_blocked_queries_only: bool,
        max_items: int,
    ) -> list[dict[str, object]]:
        stmt = (
            select(AuditLog)
            .where(
                AuditLog.tenant_id == scope.tenant_id,
                AuditLog.created_at >= from_at,
                AuditLog.created_at <= to_at,
            )
            .order_by(AuditLog.created_at.desc())
            .limit(max_items)
        )
        if include_blocked_queries_only:
            stmt = stmt.where(AuditLog.was_blocked.is_(True))

        rows = db.scalars(stmt).all()
        return [
            {
                "id": row.id,
                "user_id": row.user_id,
                "session_id": row.session_id,
                "query_text": row.query_text,
                "domains_accessed": list(row.domains_accessed or []),
                "was_blocked": row.was_blocked,
                "block_reason": row.block_reason,
                "latency_ms": row.latency_ms,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]


compliance_operations_service = ComplianceOperationsService()
