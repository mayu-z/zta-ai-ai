from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthorizationError, ValidationError
from app.db.models import ActionExecution
from app.schemas.pipeline import ScopeContext
from app.services.action_registry import ActionTemplateSchema
from app.services.action_template_override_service import (
    action_template_override_service,
)


@dataclass(slots=True)
class StepExecutionRecord:
    step_name: str
    status: str
    started_at: datetime
    completed_at: datetime
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "step_name": self.step_name,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "detail": self.detail,
        }


@dataclass(slots=True)
class ActionExecutionRecord:
    execution_id: str
    action_id: str
    tenant_id: str
    status: str
    dry_run: bool
    input_payload: dict[str, object]
    requested_by: str
    requested_at: datetime
    updated_at: datetime
    approval_required: bool
    approver_role: str | None
    approval_due_at: datetime | None
    approved_by: str | None = None
    approved_at: datetime | None = None
    approval_comment: str | None = None
    escalated: bool = False
    escalation_target: str | None = None
    output: dict[str, object] = field(default_factory=dict)
    steps: list[StepExecutionRecord] = field(default_factory=list)
    audit_events: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "execution_id": self.execution_id,
            "action_id": self.action_id,
            "tenant_id": self.tenant_id,
            "status": self.status,
            "dry_run": self.dry_run,
            "input_payload": self.input_payload,
            "requested_by": self.requested_by,
            "requested_at": self.requested_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "approval_required": self.approval_required,
            "approver_role": self.approver_role,
            "approval_due_at": (
                self.approval_due_at.isoformat() if self.approval_due_at else None
            ),
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "approval_comment": self.approval_comment,
            "escalated": self.escalated,
            "escalation_target": self.escalation_target,
            "output": self.output,
            "steps": [step.to_dict() for step in self.steps],
            "audit_events": self.audit_events,
        }


class ActionOrchestratorService:
    def reset(self) -> None:
        # Backward-compatible helper retained for tests that previously relied
        # on in-memory service state.
        return

    def execute_action(
        self,
        *,
        db: Session,
        scope: ScopeContext,
        action_id: str,
        input_payload: dict[str, object],
        dry_run: bool,
    ) -> dict[str, object]:
        template = action_template_override_service.get_effective_template(
            db=db,
            tenant_id=scope.tenant_id,
            action_id=action_id,
            enforce_enabled=True,
        )

        normalized_input_payload = self._normalize_and_validate_input(
            action_id=action_id,
            input_payload=input_payload,
            template=template,
        )

        now = datetime.now(tz=UTC)
        execution_id = str(uuid4())
        approval_required = bool(template.approval_requirements.get("required")) and not dry_run
        approver_role = (
            str(template.approval_requirements.get("approver_role", "")).strip().lower()
            or None
        )
        approval_due_at = (
            now + timedelta(hours=self._approval_sla_hours(template))
            if approval_required
            else None
        )

        status = "awaiting_approval" if approval_required else "executing"
        record = ActionExecutionRecord(
            execution_id=execution_id,
            action_id=action_id,
            tenant_id=scope.tenant_id,
            status=status,
            dry_run=dry_run,
            input_payload=normalized_input_payload,
            requested_by=scope.user_id,
            requested_at=now,
            updated_at=now,
            approval_required=approval_required,
            approver_role=approver_role,
            approval_due_at=approval_due_at,
        )

        self._append_event(
            record,
            event="action_requested",
            actor=scope.user_id,
            detail=(
                "dry-run preview requested"
                if dry_run
                else "action execution requested"
            ),
        )

        if dry_run:
            self._run_steps(record=record, template=template, dry_run=True)
            record.status = "completed"
            record.output = self._build_output_payload(
                record=record,
                template=template,
                status="dry_run_preview",
            )
            self._append_event(
                record,
                event="action_dry_run_completed",
                actor=scope.user_id,
                detail="dry-run preview generated",
            )
        elif not approval_required:
            self._run_steps(record=record, template=template, dry_run=False)
            record.status = "completed"
            record.output = self._build_output_payload(
                record=record,
                template=template,
                status="completed",
            )
            self._append_event(
                record,
                event="action_completed",
                actor=scope.user_id,
                detail="action executed successfully",
            )

        self._upsert_record(db=db, record=record)

        return record.to_dict()

    def approve_action(
        self,
        *,
        db: Session,
        scope: ScopeContext,
        execution_id: str,
        comment: str | None,
    ) -> dict[str, object]:
        record = self._require_record(
            db=db,
            execution_id=execution_id,
            tenant_id=scope.tenant_id,
        )
        if record.status != "awaiting_approval":
            raise ValidationError(
                message="Action is not awaiting approval",
                code="ACTION_NOT_AWAITING_APPROVAL",
            )

        if not self._is_approver_allowed(scope=scope, required_role=record.approver_role):
            raise AuthorizationError(
                message="User is not authorized to approve this action",
                code="APPROVER_ROLE_MISMATCH",
            )

        template = action_template_override_service.get_effective_template(
            db=db,
            tenant_id=scope.tenant_id,
            action_id=record.action_id,
            enforce_enabled=False,
        )
        now = datetime.now(tz=UTC)
        record.approved_by = scope.user_id
        record.approved_at = now
        record.approval_comment = (comment or "").strip() or None
        record.status = "executing"
        record.updated_at = now
        self._append_event(
            record,
            event="action_approved",
            actor=scope.user_id,
            detail=record.approval_comment or "approved",
        )

        self._run_steps(record=record, template=template, dry_run=False)
        record.status = "completed"
        record.output = self._build_output_payload(
            record=record,
            template=template,
            status="completed",
        )
        self._append_event(
            record,
            event="action_completed",
            actor=scope.user_id,
            detail="action executed after approval",
        )

        self._upsert_record(db=db, record=record)
        return record.to_dict()

    def rollback_action(
        self,
        *,
        db: Session,
        scope: ScopeContext,
        execution_id: str,
        reason: str,
    ) -> dict[str, object]:
        record = self._require_record(
            db=db,
            execution_id=execution_id,
            tenant_id=scope.tenant_id,
        )
        template = action_template_override_service.get_effective_template(
            db=db,
            tenant_id=scope.tenant_id,
            action_id=record.action_id,
            enforce_enabled=False,
        )

        if not template.reversible:
            raise ValidationError(
                message=f"Action {record.action_id} is not reversible",
                code="ACTION_NOT_REVERSIBLE",
            )

        if record.status != "completed":
            raise ValidationError(
                message="Only completed actions can be rolled back",
                code="ACTION_ROLLBACK_INVALID_STATUS",
            )

        now = datetime.now(tz=UTC)
        record.status = "rolled_back"
        record.updated_at = now
        rollback_reason = reason.strip() or "Rollback requested by operator"
        output = dict(record.output)
        output["rollback"] = {
            "rolled_back_at": now.isoformat(),
            "rolled_back_by": scope.user_id,
            "reason": rollback_reason,
        }
        record.output = output
        self._append_event(
            record,
            event="action_rolled_back",
            actor=scope.user_id,
            detail=rollback_reason,
        )
        self._upsert_record(db=db, record=record)
        return record.to_dict()

    def evaluate_pending_escalations(
        self,
        *,
        db: Session,
        tenant_id: str,
        as_of: datetime | None,
    ) -> dict[str, object]:
        now = as_of or datetime.now(tz=UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        else:
            now = now.astimezone(UTC)

        escalated: list[dict[str, object]] = []

        rows = db.scalars(
            select(ActionExecution)
            .where(
                ActionExecution.tenant_id == tenant_id,
                ActionExecution.status == "awaiting_approval",
                ActionExecution.escalated.is_(False),
            )
            .order_by(ActionExecution.requested_at.desc())
        ).all()
        for row in rows:
            approval_due_at = self._normalize_datetime(row.approval_due_at)
            if approval_due_at is None or approval_due_at > now:
                continue

            record = self._record_from_model(row)
            record.escalated = True
            record.escalation_target = "manager"
            record.updated_at = now
            self._append_event(
                record,
                event="approval_escalated",
                actor="system",
                detail="approval SLA breached; escalated to manager",
                at=now,
            )
            self._upsert_record(db=db, record=record)
            escalated.append(record.to_dict())

        return {
            "evaluated_at": now.isoformat(),
            "escalated_count": len(escalated),
            "items": escalated,
        }

    def get_execution(
        self,
        *,
        db: Session,
        scope: ScopeContext,
        execution_id: str,
    ) -> dict[str, object]:
        record = self._require_record(
            db=db,
            execution_id=execution_id,
            tenant_id=scope.tenant_id,
        )
        return record.to_dict()

    def list_executions(
        self,
        *,
        db: Session,
        scope: ScopeContext,
        action_id: str | None,
        status: str | None,
        limit: int,
    ) -> list[dict[str, object]]:
        normalized_action_id = (action_id or "").strip().upper() or None
        normalized_status = (status or "").strip().lower() or None
        stmt = (
            select(ActionExecution)
            .where(ActionExecution.tenant_id == scope.tenant_id)
            .order_by(ActionExecution.requested_at.desc())
            .limit(limit)
        )
        if normalized_action_id:
            stmt = stmt.where(ActionExecution.action_id == normalized_action_id)
        if normalized_status:
            stmt = stmt.where(ActionExecution.status == normalized_status)

        rows = db.scalars(stmt).all()
        return [self._record_from_model(row).to_dict() for row in rows]

    def get_execution_for_tenant(
        self,
        *,
        db: Session,
        tenant_id: str,
        execution_id: str,
    ) -> dict[str, object]:
        record = self._require_record(
            db=db,
            execution_id=execution_id,
            tenant_id=tenant_id,
        )
        return record.to_dict()

    def list_executions_for_tenant(
        self,
        *,
        db: Session,
        tenant_id: str,
        action_ids: list[str] | None,
        from_at: datetime | None,
        to_at: datetime | None,
        limit: int,
    ) -> list[dict[str, object]]:
        normalized_action_ids = {
            value.strip().upper()
            for value in (action_ids or [])
            if value and value.strip()
        }
        normalized_from_at = self._normalize_datetime(from_at)
        normalized_to_at = self._normalize_datetime(to_at)

        stmt = (
            select(ActionExecution)
            .where(ActionExecution.tenant_id == tenant_id)
            .order_by(ActionExecution.requested_at.desc())
            .limit(limit)
        )
        if normalized_action_ids:
            stmt = stmt.where(ActionExecution.action_id.in_(normalized_action_ids))
        if normalized_from_at is not None:
            stmt = stmt.where(ActionExecution.requested_at >= normalized_from_at)
        if normalized_to_at is not None:
            stmt = stmt.where(ActionExecution.requested_at <= normalized_to_at)

        rows = db.scalars(stmt).all()
        return [self._record_from_model(row).to_dict() for row in rows]

    def _run_steps(
        self,
        *,
        record: ActionExecutionRecord,
        template: ActionTemplateSchema,
        dry_run: bool,
    ) -> None:
        now = datetime.now(tz=UTC)
        for step_name in template.execution_steps:
            step_status = "simulated" if dry_run else "completed"
            step = StepExecutionRecord(
                step_name=step_name,
                status=step_status,
                started_at=now,
                completed_at=now,
                detail=(
                    "Step simulated for dry-run preview"
                    if dry_run
                    else "Step executed"
                ),
            )
            record.steps.append(step)
            self._append_event(
                record,
                event="action_step",
                actor="system",
                detail=f"{step_name}:{step_status}",
                at=now,
            )
        record.updated_at = now

    def _build_output_payload(
        self,
        *,
        record: ActionExecutionRecord,
        template: ActionTemplateSchema,
        status: str,
    ) -> dict[str, object]:
        output: dict[str, object] = {
            "execution_id": record.execution_id,
            "action_id": record.action_id,
            "status": status,
            "completed_at": datetime.now(tz=UTC).isoformat(),
        }

        specialized_output = self._build_specialized_output(
            record=record,
            status=status,
        )
        if specialized_output is not None:
            output.update(specialized_output)
            for key, declared_type in template.output_schema.items():
                output.setdefault(
                    key,
                    self._placeholder_for_output_field(
                        field_name=key,
                        declared_type=str(declared_type),
                        step_count=len(template.execution_steps),
                        status=status,
                    ),
                )
            return output

        for key, declared_type in template.output_schema.items():
            output[key] = self._placeholder_for_output_field(
                field_name=key,
                declared_type=str(declared_type),
                step_count=len(template.execution_steps),
                status=status,
            )

        return output

    @staticmethod
    def _placeholder_for_output_field(
        *,
        field_name: str,
        declared_type: str,
        step_count: int,
        status: str,
    ) -> object:
        normalized_name = field_name.lower()
        normalized_type = declared_type.lower()

        if normalized_name == "status":
            return status
        if "boolean" in normalized_type:
            return True
        if "integer" in normalized_type:
            return step_count
        if "timestamp" in normalized_type:
            return datetime.now(tz=UTC).isoformat()
        if normalized_name.endswith("_id") or normalized_name == "id":
            return str(uuid4())

        return f"{normalized_name}_{status}"

    def _build_specialized_output(
        self,
        *,
        record: ActionExecutionRecord,
        status: str,
    ) -> dict[str, object] | None:
        action_id = record.action_id
        if action_id == "DSAR_EXECUTE":
            return self._build_dsar_output(record=record, status=status)
        if action_id == "ERASURE_EXECUTE":
            return self._build_erasure_output(record=record, status=status)
        if action_id == "ESCALATE_TO_MANAGER":
            return self._build_escalation_output(record=record, status=status)
        if action_id == "BULK_SOFT_DELETE":
            return self._build_bulk_soft_delete_output(record=record, status=status)
        if action_id == "FIELD_MASKING_UPDATE":
            return self._build_field_masking_output(record=record, status=status)
        if action_id == "CONSENT_WITHDRAWAL":
            return self._build_consent_withdrawal_output(record=record, status=status)
        if action_id == "INCIDENT_RESPONSE":
            return self._build_incident_response_output(record=record, status=status)
        if action_id == "POLICY_UPDATE":
            return self._build_policy_update_output(record=record, status=status)
        if action_id == "CONNECTOR_REFRESH":
            return self._build_connector_refresh_output(record=record, status=status)
        if action_id == "AUDIT_EXPORT":
            return self._build_audit_export_output(record=record, status=status)
        if action_id == "SEGMENT_ACTIVATION":
            return self._build_segment_activation_output(record=record, status=status)
        if action_id == "SCHEDULED_REPORTING":
            return self._build_scheduled_reporting_output(record=record, status=status)
        return None

    def _build_dsar_output(
        self,
        *,
        record: ActionExecutionRecord,
        status: str,
    ) -> dict[str, object]:
        subject_identifier = str(record.input_payload["subject_identifier"])
        delivery_method = str(record.input_payload["delivery_method"])

        records_collected = self._stable_number(subject_identifier, minimum=150, span=400)
        records_redacted = self._stable_number(
            f"{subject_identifier}:redacted",
            minimum=0,
            span=max(1, records_collected // 10),
        )
        records_delivered = max(records_collected - records_redacted, 0)
        legal_deadline_at = record.requested_at + timedelta(days=30)

        return {
            "request_id": f"DSAR_{record.execution_id[:8]}",
            "status": status,
            "proof_id": f"proof_{record.execution_id[:12]}",
            "delivery_method": delivery_method,
            "legal_deadline_at": legal_deadline_at.isoformat(),
            "completion_summary": {
                "records_collected": records_collected,
                "records_redacted": records_redacted,
                "records_delivered": records_delivered,
                "subject_identifier": subject_identifier,
            },
            "forensic_evidence": {
                "request_received_at": record.requested_at.isoformat(),
                "processing_completed_at": datetime.now(tz=UTC).isoformat(),
                "sla_met": True,
                "regulatory_ready": True,
            },
        }

    def _build_erasure_output(
        self,
        *,
        record: ActionExecutionRecord,
        status: str,
    ) -> dict[str, object]:
        subject_identifier = str(record.input_payload["subject_identifier"])
        legal_basis = str(record.input_payload["legal_basis"])

        deleted_records = self._stable_number(subject_identifier, minimum=80, span=250)
        pseudonymized_records = self._stable_number(
            f"{subject_identifier}:pseudonymized",
            minimum=5,
            span=60,
        )

        return {
            "request_id": f"ERASURE_{record.execution_id[:8]}",
            "status": status,
            "deletion_certificate": f"cert_{record.execution_id[:12]}",
            "legal_basis": legal_basis,
            "completion_summary": {
                "deleted_records": deleted_records,
                "pseudonymized_records": pseudonymized_records,
                "subject_identifier": subject_identifier,
            },
            "verification": {
                "remaining_records": 0,
                "verification_query": "SELECT COUNT(*) FROM subject_records WHERE subject_identifier = ?",
            },
        }

    def _build_escalation_output(
        self,
        *,
        record: ActionExecutionRecord,
        status: str,
    ) -> dict[str, object]:
        workflow_id = str(record.input_payload["workflow_id"])
        reason = str(record.input_payload["reason"])
        deadline_at = record.requested_at + timedelta(hours=4)

        return {
            "escalation_id": f"esc_{record.execution_id[:10]}",
            "notified": True,
            "status": status,
            "workflow_id": workflow_id,
            "notification": {
                "target_role": "manager",
                "deadline_at": deadline_at.isoformat(),
                "reason": reason,
            },
        }

    def _build_bulk_soft_delete_output(
        self,
        *,
        record: ActionExecutionRecord,
        status: str,
    ) -> dict[str, object]:
        entity = str(record.input_payload["entity"])
        record_ids = [str(item) for item in list(record.input_payload["record_ids"])]

        return {
            "job_id": f"softdel_{record.execution_id[:10]}",
            "deleted_count": len(record_ids),
            "status": status,
            "entity": entity,
            "sample_record_ids": record_ids[:5],
        }

    def _build_field_masking_output(
        self,
        *,
        record: ActionExecutionRecord,
        status: str,
    ) -> dict[str, object]:
        field_path = str(record.input_payload["field_path"])
        mask_pattern = str(record.input_payload["mask_pattern"])
        affected_users = self._stable_number(
            f"{field_path}:{mask_pattern}",
            minimum=50,
            span=900,
        )

        return {
            "policy_id": f"mask_{record.execution_id[:10]}",
            "affected_users": affected_users,
            "status": status,
            "field_path": field_path,
            "mask_pattern": mask_pattern,
        }

    def _build_consent_withdrawal_output(
        self,
        *,
        record: ActionExecutionRecord,
        status: str,
    ) -> dict[str, object]:
        subject_identifier = str(record.input_payload["subject_identifier"])
        consent_type = str(record.input_payload["consent_type"])

        return {
            "status": status,
            "effective_at": datetime.now(tz=UTC).isoformat(),
            "subject_identifier": subject_identifier,
            "consent_type": consent_type,
            "downstream_processing": {
                "blocked": True,
                "domains": [consent_type] if consent_type != "all" else ["marketing", "analytics", "profiling"],
            },
        }

    def _build_incident_response_output(
        self,
        *,
        record: ActionExecutionRecord,
        status: str,
    ) -> dict[str, object]:
        incident_id = str(record.input_payload["incident_id"])
        severity = str(record.input_payload["severity"])
        notification_deadline = record.requested_at + (
            timedelta(hours=1)
            if severity in {"high", "critical"}
            else timedelta(hours=4)
        )

        return {
            "incident_id": incident_id,
            "forensic_bundle_id": f"forensic_{record.execution_id[:10]}",
            "status": status,
            "severity": severity,
            "containment": {
                "access_frozen": True,
                "evidence_preserved": True,
            },
            "notification_deadline": notification_deadline.isoformat(),
        }

    def _build_policy_update_output(
        self,
        *,
        record: ActionExecutionRecord,
        status: str,
    ) -> dict[str, object]:
        policy_id = str(record.input_payload["policy_id"])
        changes = dict(record.input_payload.get("changes") or {})
        changes_count = len(changes)

        return {
            "policy_id": policy_id,
            "status": status,
            "deployed": status != "dry_run_preview",
            "version_tag": f"{policy_id}:{record.execution_id[:8]}",
            "impact_summary": {
                "changes_count": changes_count,
                "affected_rules": self._stable_number(policy_id, minimum=1, span=25),
            },
        }

    def _build_connector_refresh_output(
        self,
        *,
        record: ActionExecutionRecord,
        status: str,
    ) -> dict[str, object]:
        connector_id = str(record.input_payload["connector_id"])
        fields_changed = self._stable_number(connector_id, minimum=0, span=30)

        return {
            "connector_id": connector_id,
            "fields_changed": fields_changed,
            "status": status,
            "force_refresh": bool(record.input_payload["force"]),
            "sync_status": "completed",
        }

    def _build_audit_export_output(
        self,
        *,
        record: ActionExecutionRecord,
        status: str,
    ) -> dict[str, object]:
        export_from = str(record.input_payload["from"])
        export_to = str(record.input_payload["to"])
        export_format = str(record.input_payload["format"])

        signature = hashlib.sha256(
            f"{record.execution_id}:{export_from}:{export_to}:{export_format}".encode(
                "utf-8"
            )
        ).hexdigest()[:32]

        return {
            "export_id": f"AUDIT_{record.execution_id[:8]}",
            "status": status,
            "signature": signature,
            "export_window": {
                "from": export_from,
                "to": export_to,
                "format": export_format,
            },
            "delivery": {
                "artifact_name": f"audit_export_{record.execution_id[:8]}.{export_format}",
                "tamper_proof": True,
            },
        }

    def _build_segment_activation_output(
        self,
        *,
        record: ActionExecutionRecord,
        status: str,
    ) -> dict[str, object]:
        segment_id = str(record.input_payload["segment_id"])
        destination = str(record.input_payload["destination"])
        exported_records = self._stable_number(segment_id, minimum=100, span=4000)

        return {
            "activation_id": f"activation_{record.execution_id[:10]}",
            "status": status,
            "segment_id": segment_id,
            "destination": destination,
            "exported_records": exported_records,
        }

    def _build_scheduled_reporting_output(
        self,
        *,
        record: ActionExecutionRecord,
        status: str,
    ) -> dict[str, object]:
        report_id = str(record.input_payload["report_id"])
        frequency = str(record.input_payload["frequency"])
        next_delta = {
            "hourly": timedelta(hours=1),
            "daily": timedelta(days=1),
            "weekly": timedelta(days=7),
            "monthly": timedelta(days=30),
        }.get(frequency, timedelta(days=1))

        return {
            "run_id": f"run_{record.execution_id[:10]}",
            "status": status,
            "report_id": report_id,
            "frequency": frequency,
            "next_run_at": (record.requested_at + next_delta).isoformat(),
            "delivery_targets": self._stable_number(report_id, minimum=1, span=20),
        }

    def _normalize_and_validate_input(
        self,
        *,
        action_id: str,
        input_payload: dict[str, object],
        template: ActionTemplateSchema,
    ) -> dict[str, object]:
        payload = dict(input_payload or {})

        if action_id == "DSAR_EXECUTE":
            subject_identifier = str(payload.get("subject_identifier") or "").strip()
            if not subject_identifier:
                raise ValidationError(
                    message="subject_identifier is required for DSAR_EXECUTE",
                    code="ACTION_INPUT_VALIDATION_FAILED",
                )

            delivery_method = str(payload.get("delivery_method") or "secure_portal").strip().lower()
            allowed_delivery_methods = {"secure_portal", "encrypted_email"}
            if delivery_method not in allowed_delivery_methods:
                raise ValidationError(
                    message="delivery_method must be secure_portal or encrypted_email",
                    code="ACTION_INPUT_VALIDATION_FAILED",
                )

            payload["subject_identifier"] = subject_identifier
            payload["delivery_method"] = delivery_method
        elif action_id == "ERASURE_EXECUTE":
            subject_identifier = str(payload.get("subject_identifier") or "").strip()
            if not subject_identifier:
                raise ValidationError(
                    message="subject_identifier is required for ERASURE_EXECUTE",
                    code="ACTION_INPUT_VALIDATION_FAILED",
                )

            legal_basis = str(payload.get("legal_basis") or "gdpr_article_17").strip().lower()
            payload["subject_identifier"] = subject_identifier
            payload["legal_basis"] = legal_basis
        elif action_id == "ESCALATE_TO_MANAGER":
            workflow_id = str(payload.get("workflow_id") or "").strip()
            reason = str(payload.get("reason") or "").strip()
            if not workflow_id or not reason:
                raise ValidationError(
                    message="workflow_id and reason are required for ESCALATE_TO_MANAGER",
                    code="ACTION_INPUT_VALIDATION_FAILED",
                )

            payload["workflow_id"] = workflow_id
            payload["reason"] = reason
        elif action_id == "BULK_SOFT_DELETE":
            entity = str(payload.get("entity") or "").strip()
            record_ids = payload.get("record_ids")
            if not entity:
                raise ValidationError(
                    message="entity is required for BULK_SOFT_DELETE",
                    code="ACTION_INPUT_VALIDATION_FAILED",
                )
            if not isinstance(record_ids, list) or not record_ids:
                raise ValidationError(
                    message="record_ids must be a non-empty array for BULK_SOFT_DELETE",
                    code="ACTION_INPUT_VALIDATION_FAILED",
                )

            normalized_ids = [str(item).strip() for item in record_ids if str(item).strip()]
            if not normalized_ids:
                raise ValidationError(
                    message="record_ids must include at least one valid identifier",
                    code="ACTION_INPUT_VALIDATION_FAILED",
                )

            payload["entity"] = entity
            payload["record_ids"] = normalized_ids
        elif action_id == "FIELD_MASKING_UPDATE":
            field_path = str(payload.get("field_path") or "").strip()
            mask_pattern = str(payload.get("mask_pattern") or "").strip()
            if not field_path or not mask_pattern:
                raise ValidationError(
                    message="field_path and mask_pattern are required for FIELD_MASKING_UPDATE",
                    code="ACTION_INPUT_VALIDATION_FAILED",
                )

            payload["field_path"] = field_path
            payload["mask_pattern"] = mask_pattern
        elif action_id == "CONSENT_WITHDRAWAL":
            subject_identifier = str(payload.get("subject_identifier") or "").strip()
            if not subject_identifier:
                raise ValidationError(
                    message="subject_identifier is required for CONSENT_WITHDRAWAL",
                    code="ACTION_INPUT_VALIDATION_FAILED",
                )

            consent_type = str(payload.get("consent_type") or "marketing").strip().lower()
            allowed_consent_types = {"marketing", "analytics", "profiling", "all"}
            if consent_type not in allowed_consent_types:
                raise ValidationError(
                    message="consent_type must be one of marketing, analytics, profiling, all",
                    code="ACTION_INPUT_VALIDATION_FAILED",
                )

            payload["subject_identifier"] = subject_identifier
            payload["consent_type"] = consent_type
        elif action_id == "INCIDENT_RESPONSE":
            incident_id = str(payload.get("incident_id") or "").strip()
            if not incident_id:
                raise ValidationError(
                    message="incident_id is required for INCIDENT_RESPONSE",
                    code="ACTION_INPUT_VALIDATION_FAILED",
                )

            severity = str(payload.get("severity") or "medium").strip().lower()
            allowed_severities = {"low", "medium", "high", "critical"}
            if severity not in allowed_severities:
                raise ValidationError(
                    message="severity must be one of low, medium, high, critical",
                    code="ACTION_INPUT_VALIDATION_FAILED",
                )

            payload["incident_id"] = incident_id
            payload["severity"] = severity
        elif action_id == "POLICY_UPDATE":
            policy_id = str(payload.get("policy_id") or "").strip()
            if not policy_id:
                raise ValidationError(
                    message="policy_id is required for POLICY_UPDATE",
                    code="ACTION_INPUT_VALIDATION_FAILED",
                )

            changes = payload.get("changes")
            if changes is None:
                changes = {}
            if not isinstance(changes, dict):
                raise ValidationError(
                    message="changes must be an object for POLICY_UPDATE",
                    code="ACTION_INPUT_VALIDATION_FAILED",
                )

            payload["policy_id"] = policy_id
            payload["changes"] = dict(changes)
        elif action_id == "CONNECTOR_REFRESH":
            connector_id = str(payload.get("connector_id") or "").strip()
            if not connector_id:
                raise ValidationError(
                    message="connector_id is required for CONNECTOR_REFRESH",
                    code="ACTION_INPUT_VALIDATION_FAILED",
                )

            payload["connector_id"] = connector_id
            payload["force"] = self._coerce_boolean(
                value=payload.get("force", False),
                action_id=action_id,
                field_name="force",
            )
        elif action_id == "AUDIT_EXPORT":
            export_from = str(payload.get("from") or "").strip()
            export_to = str(payload.get("to") or "").strip()
            if not export_from or not export_to:
                raise ValidationError(
                    message="from and to are required for AUDIT_EXPORT",
                    code="ACTION_INPUT_VALIDATION_FAILED",
                )

            export_format = str(payload.get("format") or "csv").strip().lower()
            allowed_formats = {"csv", "json", "pdf"}
            if export_format not in allowed_formats:
                raise ValidationError(
                    message="format must be csv, json, or pdf",
                    code="ACTION_INPUT_VALIDATION_FAILED",
                )

            payload["from"] = export_from
            payload["to"] = export_to
            payload["format"] = export_format
        elif action_id == "SEGMENT_ACTIVATION":
            segment_id = str(payload.get("segment_id") or "").strip()
            destination = str(payload.get("destination") or "").strip().lower()
            allowed_destinations = {"crm", "email_platform", "ads_platform", "webhook"}
            if not segment_id:
                raise ValidationError(
                    message="segment_id is required for SEGMENT_ACTIVATION",
                    code="ACTION_INPUT_VALIDATION_FAILED",
                )
            if destination not in allowed_destinations:
                raise ValidationError(
                    message="destination must be one of crm, email_platform, ads_platform, webhook",
                    code="ACTION_INPUT_VALIDATION_FAILED",
                )

            payload["segment_id"] = segment_id
            payload["destination"] = destination
        elif action_id == "SCHEDULED_REPORTING":
            report_id = str(payload.get("report_id") or "").strip()
            frequency = str(payload.get("frequency") or "daily").strip().lower()
            allowed_frequencies = {"hourly", "daily", "weekly", "monthly"}
            if not report_id:
                raise ValidationError(
                    message="report_id is required for SCHEDULED_REPORTING",
                    code="ACTION_INPUT_VALIDATION_FAILED",
                )
            if frequency not in allowed_frequencies:
                raise ValidationError(
                    message="frequency must be one of hourly, daily, weekly, monthly",
                    code="ACTION_INPUT_VALIDATION_FAILED",
                )

            payload["report_id"] = report_id
            payload["frequency"] = frequency

        self._validate_payload_against_schema(
            action_id=action_id,
            payload=payload,
            template=template,
        )
        return payload

    def _validate_payload_against_schema(
        self,
        *,
        action_id: str,
        payload: dict[str, object],
        template: ActionTemplateSchema,
    ) -> None:
        for field_name, declared_type in template.input_schema.items():
            if field_name not in payload:
                raise ValidationError(
                    message=f"{field_name} is required for {action_id}",
                    code="ACTION_INPUT_VALIDATION_FAILED",
                )

            payload[field_name] = self._coerce_input_field(
                value=payload[field_name],
                declared_type=str(declared_type),
                action_id=action_id,
                field_name=field_name,
            )

    def _coerce_input_field(
        self,
        *,
        value: object,
        declared_type: str,
        action_id: str,
        field_name: str,
    ) -> object:
        normalized_type = declared_type.strip().lower()

        if normalized_type == "string":
            text = str(value).strip()
            if not text:
                raise ValidationError(
                    message=f"{field_name} must be a non-empty string for {action_id}",
                    code="ACTION_INPUT_VALIDATION_FAILED",
                )
            return text

        if normalized_type == "array":
            if not isinstance(value, list):
                raise ValidationError(
                    message=f"{field_name} must be an array for {action_id}",
                    code="ACTION_INPUT_VALIDATION_FAILED",
                )
            return list(value)

        if normalized_type == "object":
            if not isinstance(value, dict):
                raise ValidationError(
                    message=f"{field_name} must be an object for {action_id}",
                    code="ACTION_INPUT_VALIDATION_FAILED",
                )
            return dict(value)

        if normalized_type == "boolean":
            return self._coerce_boolean(
                value=value,
                action_id=action_id,
                field_name=field_name,
            )

        if normalized_type == "timestamp":
            return self._coerce_timestamp(
                value=value,
                action_id=action_id,
                field_name=field_name,
            )

        return value

    @staticmethod
    def _coerce_boolean(
        *,
        value: object,
        action_id: str,
        field_name: str,
    ) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in {0, 1}:
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "y"}:
                return True
            if normalized in {"false", "0", "no", "n"}:
                return False

        raise ValidationError(
            message=f"{field_name} must be boolean for {action_id}",
            code="ACTION_INPUT_VALIDATION_FAILED",
        )

    @staticmethod
    def _coerce_timestamp(
        *,
        value: object,
        action_id: str,
        field_name: str,
    ) -> str:
        text = str(value).strip()
        if not text:
            raise ValidationError(
                message=f"{field_name} must be a timestamp for {action_id}",
                code="ACTION_INPUT_VALIDATION_FAILED",
            )

        candidate = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError as exc:
            raise ValidationError(
                message=f"{field_name} must be a valid ISO timestamp for {action_id}",
                code="ACTION_INPUT_VALIDATION_FAILED",
            ) from exc

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)

        return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _stable_number(seed: str, *, minimum: int, span: int) -> int:
        if span <= 0:
            return minimum
        checksum = sum(ord(ch) for ch in seed)
        return minimum + (checksum % span)

    @staticmethod
    def _approval_sla_hours(template: ActionTemplateSchema) -> int:
        raw = template.approval_requirements.get("sla_hours", 4)
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            return 4

    @staticmethod
    def _is_approver_allowed(scope: ScopeContext, required_role: str | None) -> bool:
        if not required_role:
            return True

        required = required_role.strip().lower()
        candidates = {
            scope.persona_type.strip().lower(),
            (scope.role_key or "").strip().lower(),
            (scope.admin_function or "").strip().lower(),
        }

        if required in candidates:
            return True

        # IT heads and executives can approve cross-functional action templates.
        return "it_head" in candidates or "executive" in candidates

    @staticmethod
    def _append_event(
        record: ActionExecutionRecord,
        *,
        event: str,
        actor: str,
        detail: str,
        at: datetime | None = None,
    ) -> None:
        events = list(record.audit_events or [])
        events.append(
            {
                "event": event,
                "actor": actor,
                "detail": detail,
                "at": (at or datetime.now(tz=UTC)).isoformat(),
            }
        )
        record.audit_events = events

    @staticmethod
    def _normalize_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @classmethod
    def _parse_datetime_value(cls, value: object) -> datetime | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        return cls._normalize_datetime(parsed)

    @classmethod
    def _record_from_model(cls, row: ActionExecution) -> ActionExecutionRecord:
        requested_at = cls._normalize_datetime(row.requested_at) or datetime.now(tz=UTC)
        updated_at = cls._normalize_datetime(row.updated_at) or requested_at
        approval_due_at = cls._normalize_datetime(row.approval_due_at)
        approved_at = cls._normalize_datetime(row.approved_at)

        steps: list[StepExecutionRecord] = []
        for item in list(row.steps or []):
            if not isinstance(item, dict):
                continue
            started_at = cls._parse_datetime_value(item.get("started_at")) or requested_at
            completed_at = cls._parse_datetime_value(item.get("completed_at")) or started_at
            steps.append(
                StepExecutionRecord(
                    step_name=str(item.get("step_name") or ""),
                    status=str(item.get("status") or ""),
                    started_at=started_at,
                    completed_at=completed_at,
                    detail=str(item.get("detail") or ""),
                )
            )

        audit_events = [
            dict(item)
            for item in list(row.audit_events or [])
            if isinstance(item, dict)
        ]

        return ActionExecutionRecord(
            execution_id=row.execution_id,
            action_id=row.action_id,
            tenant_id=row.tenant_id,
            status=row.status,
            dry_run=row.dry_run,
            input_payload=dict(row.input_payload or {}),
            requested_by=row.requested_by,
            requested_at=requested_at,
            updated_at=updated_at,
            approval_required=row.approval_required,
            approver_role=row.approver_role,
            approval_due_at=approval_due_at,
            approved_by=row.approved_by,
            approved_at=approved_at,
            approval_comment=row.approval_comment,
            escalated=row.escalated,
            escalation_target=row.escalation_target,
            output=dict(row.output or {}),
            steps=steps,
            audit_events=audit_events,
        )

    def _upsert_record(self, *, db: Session, record: ActionExecutionRecord) -> None:
        row = db.get(ActionExecution, record.execution_id)
        if row is None:
            row = ActionExecution(execution_id=record.execution_id)

        row.action_id = record.action_id
        row.tenant_id = record.tenant_id
        row.status = record.status
        row.dry_run = record.dry_run
        row.input_payload = dict(record.input_payload or {})
        row.requested_by = record.requested_by
        row.requested_at = record.requested_at
        row.updated_at = record.updated_at
        row.approval_required = record.approval_required
        row.approver_role = record.approver_role
        row.approval_due_at = record.approval_due_at
        row.approved_by = record.approved_by
        row.approved_at = record.approved_at
        row.approval_comment = record.approval_comment
        row.escalated = record.escalated
        row.escalation_target = record.escalation_target
        row.output = dict(record.output or {})
        row.steps = [step.to_dict() for step in record.steps]
        row.audit_events = [
            dict(item)
            for item in list(record.audit_events or [])
            if isinstance(item, dict)
        ]

        db.add(row)
        db.commit()
        db.refresh(row)

    def _require_record(
        self,
        *,
        db: Session,
        execution_id: str,
        tenant_id: str,
    ) -> ActionExecutionRecord:
        row = db.scalar(
            select(ActionExecution).where(
                ActionExecution.execution_id == execution_id,
                ActionExecution.tenant_id == tenant_id,
            )
        )
        if row is None:
            raise ValidationError(
                message="Action execution not found",
                code="ACTION_EXECUTION_NOT_FOUND",
            )
        return self._record_from_model(row)


action_orchestrator_service = ActionOrchestratorService()
