from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.db.models import ComplianceCase
from app.schemas.pipeline import ScopeContext
from app.services.action_orchestrator import action_orchestrator_service


CASE_TYPE_TO_ACTION_ID = {
    "dsar": "DSAR_EXECUTE",
    "erasure": "ERASURE_EXECUTE",
}

CASE_TYPE_TO_SLA_DAYS = {
    "dsar": 30,
    "erasure": 45,
}

ACTION_STATUS_TO_CASE_STATUS = {
    "awaiting_approval": "pending_approval",
    "executing": "executing",
    "completed": "completed",
    "rolled_back": "rolled_back",
}


class ComplianceCaseService:
    def reset(self) -> None:
        # Backward-compatible helper retained for tests that previously relied
        # on in-memory service state.
        return

    def create_case(
        self,
        *,
        db: Session,
        scope: ScopeContext,
        case_type: str,
        subject_identifier: str,
        delivery_method: str | None,
        legal_basis: str | None,
    ) -> dict[str, object]:
        normalized_case_type = (case_type or "").strip().lower()
        action_id = CASE_TYPE_TO_ACTION_ID.get(normalized_case_type)
        if action_id is None:
            raise ValidationError(
                message="case_type must be one of dsar, erasure",
                code="COMPLIANCE_CASE_TYPE_INVALID",
            )

        normalized_subject = (subject_identifier or "").strip()
        if not normalized_subject:
            raise ValidationError(
                message="subject_identifier is required",
                code="COMPLIANCE_CASE_INPUT_INVALID",
            )

        action_input: dict[str, object] = {
            "subject_identifier": normalized_subject,
        }

        normalized_delivery = None
        normalized_legal_basis = None
        if normalized_case_type == "dsar":
            normalized_delivery = (delivery_method or "secure_portal").strip().lower()
            action_input["delivery_method"] = normalized_delivery
        else:
            normalized_legal_basis = (legal_basis or "gdpr_article_17").strip().lower()
            action_input["legal_basis"] = normalized_legal_basis

        execution = action_orchestrator_service.execute_action(
            db=db,
            scope=scope,
            action_id=action_id,
            input_payload=action_input,
            dry_run=False,
        )

        requested_at = self._parse_datetime(execution.get("requested_at")) or datetime.now(tz=UTC)
        last_action_status = str(execution.get("status") or "awaiting_approval").lower()
        now = datetime.now(tz=UTC)
        record = ComplianceCase(
            id=str(uuid4()),
            tenant_id=scope.tenant_id,
            case_type=normalized_case_type,
            subject_identifier=normalized_subject,
            action_execution_id=str(execution["execution_id"]),
            requested_by=scope.user_id,
            requested_at=requested_at,
            sla_due_at=requested_at + timedelta(days=CASE_TYPE_TO_SLA_DAYS[normalized_case_type]),
            status=ACTION_STATUS_TO_CASE_STATUS.get(last_action_status, "unknown"),
            updated_at=now,
            delivery_method=normalized_delivery,
            legal_basis=normalized_legal_basis,
            last_action_status=last_action_status,
            output=dict(execution.get("output") or {}),
        )
        self._append_case_event(
            record,
            event="case_created",
            actor=scope.user_id,
            detail=f"{normalized_case_type} compliance case created",
            at=now,
        )

        db.add(record)
        db.commit()
        db.refresh(record)
        return self._serialize_case(record)

    def list_cases(
        self,
        *,
        db: Session,
        scope: ScopeContext,
        case_type: str | None,
        status: str | None,
        limit: int,
    ) -> list[dict[str, object]]:
        normalized_case_type = (case_type or "").strip().lower() or None
        normalized_status = (status or "").strip().lower() or None

        stmt = (
            select(ComplianceCase)
            .where(ComplianceCase.tenant_id == scope.tenant_id)
            .order_by(ComplianceCase.requested_at.desc())
            .limit(limit)
        )
        if normalized_case_type:
            stmt = stmt.where(ComplianceCase.case_type == normalized_case_type)

        rows = db.scalars(stmt).all()
        changed = False
        filtered_rows: list[ComplianceCase] = []
        for row in rows:
            changed = self._refresh_case(db=db, record=row) or changed
            if normalized_status and row.status != normalized_status:
                continue
            filtered_rows.append(row)
            if len(filtered_rows) >= limit:
                break

        if changed:
            db.commit()

        return [self._serialize_case(row) for row in filtered_rows]

    def get_case(self, *, db: Session, scope: ScopeContext, case_id: str) -> dict[str, object]:
        record = self._require_case(db=db, case_id=case_id, tenant_id=scope.tenant_id)
        if self._refresh_case(db=db, record=record):
            db.commit()
            db.refresh(record)
        return self._serialize_case(record)

    def set_legal_hold(
        self,
        *,
        db: Session,
        scope: ScopeContext,
        case_id: str,
        active: bool,
        reason: str,
    ) -> dict[str, object]:
        record = self._require_case(db=db, case_id=case_id, tenant_id=scope.tenant_id)
        if active:
            hold_reason = (reason or "").strip()
            if not hold_reason:
                raise ValidationError(
                    message="reason is required when enabling legal hold",
                    code="LEGAL_HOLD_REASON_REQUIRED",
                )
            record.legal_hold_active = True
            record.legal_hold_reason = hold_reason
            event_name = "legal_hold_enabled"
            event_detail = hold_reason
        else:
            record.legal_hold_active = False
            record.legal_hold_reason = None
            event_name = "legal_hold_disabled"
            event_detail = (reason or "").strip() or "Legal hold released"

        now = datetime.now(tz=UTC)
        record.updated_at = now
        self._append_case_event(
            record,
            event=event_name,
            actor=scope.user_id,
            detail=event_detail,
            at=now,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return self._serialize_case(record)

    def approve_case(
        self,
        *,
        db: Session,
        scope: ScopeContext,
        case_id: str,
        comment: str | None,
    ) -> dict[str, object]:
        record = self._require_case(db=db, case_id=case_id, tenant_id=scope.tenant_id)
        self._assert_case_approvable(record)

        execution = action_orchestrator_service.approve_action(
            db=db,
            scope=scope,
            execution_id=record.action_execution_id,
            comment=comment,
        )

        self._sync_from_execution(record, execution=execution)
        self._append_case_event(
            record,
            event="case_approved",
            actor=scope.user_id,
            detail=(comment or "").strip() or "approved",
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return self._serialize_case(record)

    def assert_execution_approvable(
        self,
        *,
        db: Session,
        tenant_id: str,
        execution_id: str,
    ) -> None:
        record = db.scalar(
            select(ComplianceCase).where(
                ComplianceCase.tenant_id == tenant_id,
                ComplianceCase.action_execution_id == execution_id,
            )
        )
        if record is None:
            return

        self._assert_case_approvable(record)

    def _assert_case_approvable(self, record: ComplianceCase) -> None:
        if record.legal_hold_active and record.case_type == "erasure":
            raise ValidationError(
                message=(
                    "Erasure action cannot be approved while legal hold is active"
                ),
                code="LEGAL_HOLD_ACTIVE",
            )

    def _refresh_case(self, *, db: Session, record: ComplianceCase) -> bool:
        try:
            execution = action_orchestrator_service.get_execution_for_tenant(
                db=db,
                tenant_id=record.tenant_id,
                execution_id=record.action_execution_id,
            )
        except ValidationError as exc:
            if exc.code == "ACTION_EXECUTION_NOT_FOUND":
                return False
            raise
        return self._sync_from_execution(record, execution=execution)

    def _sync_from_execution(
        self,
        record: ComplianceCase,
        *,
        execution: dict[str, object],
    ) -> bool:
        changed = False
        action_status = str(execution.get("status") or "").lower()
        if record.last_action_status != action_status:
            record.last_action_status = action_status
            changed = True

        status = ACTION_STATUS_TO_CASE_STATUS.get(action_status, "unknown")
        if record.status != status:
            record.status = status
            changed = True

        updated_at = self._parse_datetime(execution.get("updated_at"))
        if updated_at is not None and record.updated_at != updated_at:
            record.updated_at = updated_at
            changed = True

        output = execution.get("output")
        if isinstance(output, dict):
            normalized_output = dict(output)
            if dict(record.output or {}) != normalized_output:
                record.output = normalized_output
                changed = True

        return changed

    @staticmethod
    def _append_case_event(
        record: ComplianceCase,
        *,
        event: str,
        actor: str,
        detail: str,
        at: datetime | None = None,
    ) -> None:
        events = list(record.case_events or [])
        events.append(
            {
                "event": event,
                "actor": actor,
                "detail": detail,
                "at": (at or datetime.now(tz=UTC)).isoformat(),
            }
        )
        record.case_events = events

    def _require_case(
        self,
        *,
        db: Session,
        case_id: str,
        tenant_id: str,
    ) -> ComplianceCase:
        record = db.scalar(
            select(ComplianceCase).where(
                ComplianceCase.id == case_id,
                ComplianceCase.tenant_id == tenant_id,
            )
        )
        if record is None:
            raise ValidationError(
                message="Compliance case not found",
                code="COMPLIANCE_CASE_NOT_FOUND",
            )
        return record

    @staticmethod
    def _serialize_case(record: ComplianceCase) -> dict[str, object]:
        return {
            "case_id": record.id,
            "tenant_id": record.tenant_id,
            "case_type": record.case_type,
            "subject_identifier": record.subject_identifier,
            "action_execution_id": record.action_execution_id,
            "requested_by": record.requested_by,
            "requested_at": record.requested_at.isoformat(),
            "sla_due_at": record.sla_due_at.isoformat(),
            "status": record.status,
            "updated_at": record.updated_at.isoformat(),
            "delivery_method": record.delivery_method,
            "legal_basis": record.legal_basis,
            "legal_hold_active": record.legal_hold_active,
            "legal_hold_reason": record.legal_hold_reason,
            "last_action_status": record.last_action_status,
            "output": dict(record.output or {}),
            "case_events": list(record.case_events or []),
        }

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)


compliance_case_service = ComplianceCaseService()
