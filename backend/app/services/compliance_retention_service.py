from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ActionExecution, ComplianceCase
from app.schemas.pipeline import ScopeContext


TERMINAL_CASE_STATUSES = {"completed", "rolled_back"}
TERMINAL_ACTION_STATUSES = {"completed", "rolled_back", "failed", "cancelled"}
COMPLIANCE_ACTION_IDS = {
    "DSAR_EXECUTE",
    "ERASURE_EXECUTE",
    "INCIDENT_RESPONSE",
    "AUDIT_EXPORT",
    "CONSENT_WITHDRAWAL",
}


class ComplianceRetentionService:
    def run_retention(
        self,
        *,
        db: Session,
        scope: ScopeContext,
        retention_days: int,
        dry_run: bool,
        max_items: int,
        as_of: datetime | None,
    ) -> dict[str, object]:
        evaluated_at = self._normalize_datetime(as_of) or datetime.now(tz=UTC)
        cutoff_at = evaluated_at - timedelta(days=retention_days)

        old_cases = db.scalars(
            select(ComplianceCase)
            .where(
                ComplianceCase.tenant_id == scope.tenant_id,
                ComplianceCase.updated_at <= cutoff_at,
            )
            .order_by(ComplianceCase.updated_at.asc())
            .limit(max_items)
        ).all()

        eligible_cases: list[ComplianceCase] = []
        skipped_legal_hold = 0
        skipped_non_terminal_cases = 0

        for case in old_cases:
            if case.legal_hold_active:
                skipped_legal_hold += 1
                continue
            if case.status not in TERMINAL_CASE_STATUSES:
                skipped_non_terminal_cases += 1
                continue
            eligible_cases.append(case)

        deleted_cases = 0
        deleted_actions = 0
        skipped_referenced_actions = 0
        skipped_non_terminal_actions = 0

        if not dry_run:
            # Delete cases first so action cleanup can safely remove unreferenced executions.
            for case in eligible_cases:
                db.delete(case)
                deleted_cases += 1
            db.flush()

            old_actions = db.scalars(
                select(ActionExecution)
                .where(
                    ActionExecution.tenant_id == scope.tenant_id,
                    ActionExecution.updated_at <= cutoff_at,
                    ActionExecution.action_id.in_(COMPLIANCE_ACTION_IDS),
                )
                .order_by(ActionExecution.updated_at.asc())
                .limit(max_items)
            ).all()

            for action in old_actions:
                if action.status not in TERMINAL_ACTION_STATUSES:
                    skipped_non_terminal_actions += 1
                    continue

                references = int(
                    db.scalar(
                        select(func.count())
                        .select_from(ComplianceCase)
                        .where(
                            ComplianceCase.tenant_id == scope.tenant_id,
                            ComplianceCase.action_execution_id == action.execution_id,
                        )
                    )
                    or 0
                )
                if references > 0:
                    skipped_referenced_actions += 1
                    continue

                db.delete(action)
                deleted_actions += 1

            db.commit()

        return {
            "evaluated_at": evaluated_at.isoformat(),
            "cutoff_at": cutoff_at.isoformat(),
            "retention_days": retention_days,
            "dry_run": dry_run,
            "max_items": max_items,
            "eligible_cases": len(eligible_cases),
            "deleted_cases": deleted_cases,
            "deleted_action_executions": deleted_actions,
            "skipped_legal_hold": skipped_legal_hold,
            "skipped_non_terminal_cases": skipped_non_terminal_cases,
            "skipped_non_terminal_actions": skipped_non_terminal_actions,
            "skipped_referenced_actions": skipped_referenced_actions,
            "items": [
                {
                    "case_id": case.id,
                    "case_type": case.case_type,
                    "status": case.status,
                    "action_execution_id": case.action_execution_id,
                    "updated_at": case.updated_at.isoformat(),
                }
                for case in eligible_cases
            ],
        }

    @staticmethod
    def _normalize_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


compliance_retention_service = ComplianceRetentionService()
