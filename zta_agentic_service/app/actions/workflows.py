from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.actions.base import BaseAction, ExecutionResult, PreviewResult, RollbackResult
from app.core.config import get_settings
from app.db.models import ActionAuditLog, ActionExecution, ActionRegistry
from app.integrations.ticketing import TicketingClient


class DSARRequest(BaseAction):
    name = "dsar_request"

    def __init__(self, db: Session, ticketing: TicketingClient, actor: str = "system") -> None:
        super().__init__(db=db, actor=actor)
        self.ticketing = ticketing

    def dry_run(self, context: dict[str, Any]) -> PreviewResult:
        deadline_hours = int(context.get("deadline_hours", 720))
        deadline = datetime.now(UTC) + timedelta(hours=deadline_hours)
        details = {
            "subject_id": context.get("subject_id"),
            "deadline_at": deadline.isoformat(),
            "status": "pending",
        }
        return PreviewResult(preview_only=True, summary="DSAR deadline would be scheduled", details=details)

    def execute(self, context: dict[str, Any]) -> ExecutionResult:
        execution = self.get_execution(context["execution_id"])
        deadline_hours = int(context.get("deadline_hours", 720))
        deadline = datetime.now(UTC) + timedelta(hours=deadline_hours)
        ticket_id = self.ticketing.create_ticket(
            title="DSAR Request",
            description="Data subject access request initiated",
            metadata={"execution_id": str(execution.id), "subject_id": context.get("subject_id")},
        )
        result = {
            "dsar_status": "in_progress",
            "subject_id": context.get("subject_id"),
            "deadline_at": deadline.isoformat(),
            "ticket_id": ticket_id,
        }
        self.append_execution_result(execution, {"dsar_previous_status": execution.result.get("dsar_status")})
        self.append_execution_result(execution, result)
        self.audit_log(
            execution_id=str(execution.id),
            step="set_deadline",
            outcome="success",
            payload_in=context,
            payload_out=result,
        )
        return ExecutionResult(status="completed", summary="DSAR request scheduled", details=result)

    def rollback(self, execution_id: str) -> RollbackResult:
        execution = self.get_execution(execution_id)
        previous_status = execution.result.get("dsar_previous_status") or "rolled_back"
        ticket_id = execution.result.get("ticket_id")
        if ticket_id:
            self.ticketing.update_ticket(ticket_id=ticket_id, status="cancelled", comment="DSAR rollback")
        result = dict(execution.result)
        result["dsar_status"] = previous_status
        result["rollback_at"] = datetime.now(UTC).isoformat()
        execution.result = result
        self.db.add(execution)
        self.db.commit()
        self.audit_log(
            execution_id=execution_id,
            step="rollback_dsar",
            outcome="rolled_back",
            payload_in={"execution_id": execution_id},
            payload_out={"dsar_status": previous_status},
        )
        return RollbackResult(status="rolled_back", summary="DSAR status restored", details=result)


class ErasureRequest(BaseAction):
    name = "erasure_request"

    def dry_run(self, context: dict[str, Any]) -> PreviewResult:
        targets = list(context.get("record_names", []))
        return PreviewResult(
            preview_only=True,
            summary="Erasure request would soft-delete target registry rows",
            details={"target_records": targets, "strategy": "soft_delete"},
        )

    def execute(self, context: dict[str, Any]) -> ExecutionResult:
        execution = self.get_execution(context["execution_id"])
        targets = list(context.get("record_names", []))
        stmt = select(ActionRegistry)
        if targets:
            stmt = stmt.where(ActionRegistry.name.in_(targets))
        rows = self.db.scalars(stmt).all()

        before = {row.name: row.is_active for row in rows}
        for row in rows:
            row.is_active = False
            self.db.add(row)
        self.db.commit()

        proof_source = {
            "execution_id": str(execution.id),
            "records": [row.name for row in rows],
            "timestamp": datetime.now(UTC).isoformat(),
        }
        proof_hash = self.sign_payload(proof_source, secret="erasure-proof")
        result = {
            "erased_records": [row.name for row in rows],
            "previous_active_flags": before,
            "proof_hash": proof_hash,
        }
        self.append_execution_result(execution, result)
        self.audit_log(
            execution_id=str(execution.id),
            step="soft_delete_records",
            outcome="success",
            payload_in={"record_names": targets},
            payload_out={"erased_count": len(rows), "proof_hash": proof_hash},
        )
        return ExecutionResult(status="completed", summary="Erasure soft-delete applied", details=result)

    def rollback(self, execution_id: str) -> RollbackResult:
        execution = self.get_execution(execution_id)
        previous = dict(execution.result.get("previous_active_flags", {}))
        if previous:
            rows = self.db.scalars(select(ActionRegistry).where(ActionRegistry.name.in_(list(previous)))).all()
            for row in rows:
                row.is_active = bool(previous.get(row.name, row.is_active))
                self.db.add(row)
            self.db.commit()

        result = dict(execution.result)
        result["rollback_at"] = datetime.now(UTC).isoformat()
        execution.result = result
        self.db.add(execution)
        self.db.commit()
        self.audit_log(
            execution_id=execution_id,
            step="rollback_erasure",
            outcome="rolled_back",
            payload_in={"execution_id": execution_id},
            payload_out={"restored_records": list(previous)},
        )
        return RollbackResult(status="rolled_back", summary="Erasure rollback completed", details=result)


class EscalateToManager(BaseAction):
    name = "escalate_to_manager"

    def __init__(self, db: Session, ticketing: TicketingClient, actor: str = "system") -> None:
        super().__init__(db=db, actor=actor)
        self.ticketing = ticketing

    def dry_run(self, context: dict[str, Any]) -> PreviewResult:
        details = {
            "manager": context.get("manager", "manager-on-call"),
            "reason": context.get("reason", "policy escalation"),
            "notification_task": "actions.manager_notification",
        }
        return PreviewResult(preview_only=True, summary="Escalation would notify manager", details=details)

    def execute(self, context: dict[str, Any]) -> ExecutionResult:
        from app.workers.tasks import manager_notification_task

        execution = self.get_execution(context["execution_id"])
        manager = context.get("manager", "manager-on-call")
        reason = context.get("reason", "policy escalation")
        ticket_id = self.ticketing.create_ticket(
            title="Manager Escalation",
            description=reason,
            metadata={"execution_id": str(execution.id), "manager": manager},
        )
        manager_notification_task.delay(str(execution.id), manager, reason)

        escalation = {
            "manager": manager,
            "reason": reason,
            "ticket_id": ticket_id,
            "escalated_at": datetime.now(UTC).isoformat(),
        }
        self.append_execution_result(execution, {"escalation": escalation})
        self.audit_log(
            execution_id=str(execution.id),
            step="create_escalation",
            outcome="success",
            payload_in=context,
            payload_out=escalation,
        )
        return ExecutionResult(status="completed", summary="Escalation submitted", details=escalation)

    def rollback(self, execution_id: str) -> RollbackResult:
        execution = self.get_execution(execution_id)
        escalation = dict(execution.result.get("escalation", {}))
        ticket_id = escalation.get("ticket_id")
        if ticket_id:
            self.ticketing.update_ticket(ticket_id=ticket_id, status="cancelled", comment="Escalation rollback")
        escalation["rolled_back_at"] = datetime.now(UTC).isoformat()
        self.append_execution_result(execution, {"escalation": escalation})
        self.audit_log(
            execution_id=execution_id,
            step="rollback_escalation",
            outcome="rolled_back",
            payload_in={"execution_id": execution_id},
            payload_out=escalation,
        )
        return RollbackResult(status="rolled_back", summary="Escalation rollback completed", details=escalation)


class BulkSoftDelete(BaseAction):
    name = "bulk_soft_delete"

    def dry_run(self, context: dict[str, Any]) -> PreviewResult:
        targets = list(context.get("execution_ids", []))
        return PreviewResult(
            preview_only=True,
            summary="Bulk soft delete would stamp deleted_at on action_executions.result",
            details={"target_execution_ids": targets},
        )

    def execute(self, context: dict[str, Any]) -> ExecutionResult:
        execution = self.get_execution(context["execution_id"])
        target_ids = [str(item) for item in context.get("execution_ids", [])]
        rows = self.db.scalars(select(ActionExecution).where(ActionExecution.id.in_(target_ids))).all()

        deleted_at = datetime.now(UTC).isoformat()
        previous_results = {str(row.id): dict(row.result or {}) for row in rows}
        for row in rows:
            updated = dict(row.result or {})
            updated["deleted_at"] = deleted_at
            updated["soft_deleted_by"] = str(execution.id)
            row.result = updated
            self.db.add(row)
        self.db.commit()

        result = {
            "deleted_at": deleted_at,
            "affected_execution_ids": [str(row.id) for row in rows],
            "previous_results": previous_results,
        }
        self.append_execution_result(execution, result)
        self.audit_log(
            execution_id=str(execution.id),
            step="bulk_soft_delete",
            outcome="success",
            payload_in={"execution_ids": target_ids},
            payload_out={"affected": len(rows), "deleted_at": deleted_at},
        )
        return ExecutionResult(status="completed", summary="Bulk soft delete applied", details=result)

    def rollback(self, execution_id: str) -> RollbackResult:
        execution = self.get_execution(execution_id)
        previous_results = dict(execution.result.get("previous_results", {}))
        rows = self.db.scalars(select(ActionExecution).where(ActionExecution.id.in_(list(previous_results)))).all()
        for row in rows:
            row.result = previous_results.get(str(row.id), row.result)
            self.db.add(row)
        self.db.commit()

        rollback_details = {
            "restored_execution_ids": list(previous_results),
            "rolled_back_at": datetime.now(UTC).isoformat(),
        }
        self.append_execution_result(execution, rollback_details)
        self.audit_log(
            execution_id=execution_id,
            step="rollback_bulk_soft_delete",
            outcome="rolled_back",
            payload_in={"execution_id": execution_id},
            payload_out=rollback_details,
        )
        return RollbackResult(status="rolled_back", summary="Bulk soft delete rollback complete", details=rollback_details)


class FieldMaskingUpdate(BaseAction):
    name = "field_masking_update"

    def dry_run(self, context: dict[str, Any]) -> PreviewResult:
        rules = dict(context.get("masking_rules", {}))
        return PreviewResult(
            preview_only=True,
            summary="Field masking rules would be applied to required_permissions",
            details={"masking_rules": rules},
        )

    def execute(self, context: dict[str, Any]) -> ExecutionResult:
        execution = self.get_execution(context["execution_id"])
        masking_rules = dict(context.get("masking_rules", {}))
        target_actions = list(context.get("target_actions", []))

        stmt = select(ActionRegistry)
        if target_actions:
            stmt = stmt.where(ActionRegistry.name.in_(target_actions))
        rows = self.db.scalars(stmt).all()

        previous_permissions = {}
        for row in rows:
            previous_permissions[row.name] = list(row.required_permissions or [])
            updated = list(row.required_permissions or [])
            for field_name, classification in masking_rules.items():
                marker = f"mask:{field_name}:{classification}"
                if marker not in updated:
                    updated.append(marker)
            row.required_permissions = updated
            self.db.add(row)
        self.db.commit()

        result = {
            "updated_actions": [row.name for row in rows],
            "masking_rules": masking_rules,
            "previous_permissions": previous_permissions,
        }
        self.append_execution_result(execution, result)
        self.audit_log(
            execution_id=str(execution.id),
            step="field_masking_update",
            outcome="success",
            payload_in=context,
            payload_out={"updated_count": len(rows)},
        )
        return ExecutionResult(status="completed", summary="Field masking updated", details=result)

    def rollback(self, execution_id: str) -> RollbackResult:
        execution = self.get_execution(execution_id)
        previous_permissions = dict(execution.result.get("previous_permissions", {}))
        rows = self.db.scalars(select(ActionRegistry).where(ActionRegistry.name.in_(list(previous_permissions)))).all()
        for row in rows:
            row.required_permissions = previous_permissions.get(row.name, row.required_permissions)
            self.db.add(row)
        self.db.commit()

        details = {"restored_actions": list(previous_permissions), "rolled_back_at": datetime.now(UTC).isoformat()}
        self.append_execution_result(execution, details)
        self.audit_log(
            execution_id=execution_id,
            step="rollback_field_masking",
            outcome="rolled_back",
            payload_in={"execution_id": execution_id},
            payload_out=details,
        )
        return RollbackResult(status="rolled_back", summary="Field masking rollback complete", details=details)


class ConsentWithdrawal(BaseAction):
    name = "consent_withdrawal"

    def dry_run(self, context: dict[str, Any]) -> PreviewResult:
        return PreviewResult(
            preview_only=True,
            summary="Consent withdrawal would revoke access and remove marketing records",
            details={
                "subject_id": context.get("subject_id"),
                "marketing_records": list(context.get("marketing_records", [])),
                "target_actions": list(context.get("target_actions", [])),
            },
        )

    def execute(self, context: dict[str, Any]) -> ExecutionResult:
        execution = self.get_execution(context["execution_id"])
        targets = list(context.get("target_actions", []))
        rows = self.db.scalars(select(ActionRegistry).where(ActionRegistry.name.in_(targets))).all() if targets else []

        previous_flags = {}
        for row in rows:
            previous_flags[row.name] = row.is_active
            row.is_active = False
            self.db.add(row)
        self.db.commit()

        details = {
            "subject_id": context.get("subject_id"),
            "access_revoked": [row.name for row in rows],
            "deleted_marketing_records": list(context.get("marketing_records", [])),
            "previous_flags": previous_flags,
        }
        self.append_execution_result(execution, details)
        self.audit_log(
            execution_id=str(execution.id),
            step="consent_withdrawal",
            outcome="success",
            payload_in=context,
            payload_out=details,
        )
        return ExecutionResult(status="completed", summary="Consent withdrawal completed", details=details)

    def rollback(self, execution_id: str) -> RollbackResult:
        execution = self.get_execution(execution_id)
        previous_flags = dict(execution.result.get("previous_flags", {}))
        if previous_flags:
            rows = self.db.scalars(select(ActionRegistry).where(ActionRegistry.name.in_(list(previous_flags)))).all()
            for row in rows:
                row.is_active = bool(previous_flags.get(row.name, row.is_active))
                self.db.add(row)
            self.db.commit()

        details = {
            "consent_restored": True,
            "restored_actions": list(previous_flags),
            "rolled_back_at": datetime.now(UTC).isoformat(),
        }
        self.append_execution_result(execution, details)
        self.audit_log(
            execution_id=execution_id,
            step="rollback_consent_withdrawal",
            outcome="rolled_back",
            payload_in={"execution_id": execution_id},
            payload_out=details,
        )
        return RollbackResult(status="rolled_back", summary="Consent rollback completed", details=details)


class IncidentResponse(BaseAction):
    name = "incident_response"

    def __init__(self, db: Session, ticketing: TicketingClient, actor: str = "system") -> None:
        super().__init__(db=db, actor=actor)
        self.ticketing = ticketing

    def dry_run(self, context: dict[str, Any]) -> PreviewResult:
        return PreviewResult(
            preview_only=True,
            summary="Incident response would freeze access and notify stakeholders",
            details={"incident_id": context.get("incident_id"), "scope": context.get("scope", "all")},
        )

    def execute(self, context: dict[str, Any]) -> ExecutionResult:
        from app.workers.tasks import manager_notification_task

        execution = self.get_execution(context["execution_id"])
        scope = context.get("scope", "all")
        if scope == "all":
            rows = self.db.scalars(select(ActionRegistry)).all()
        else:
            target_actions = list(context.get("target_actions", []))
            rows = self.db.scalars(select(ActionRegistry).where(ActionRegistry.name.in_(target_actions))).all()

        previous_flags = {row.name: row.is_active for row in rows}
        for row in rows:
            row.is_active = False
            self.db.add(row)
        self.db.commit()

        report = {
            "incident_id": context.get("incident_id", str(execution.id)),
            "frozen_actions": [row.name for row in rows],
            "frozen_count": len(rows),
            "generated_at": datetime.now(UTC).isoformat(),
        }
        ticket_id = self.ticketing.create_ticket(
            title=f"Incident Response {report['incident_id']}",
            description="Access frozen and response initiated",
            metadata={"execution_id": str(execution.id), "frozen_count": len(rows)},
        )
        manager_notification_task.delay(str(execution.id), "security-manager", "Incident response initiated")

        details = {
            "access_frozen": True,
            "report": report,
            "ticket_id": ticket_id,
            "previous_flags": previous_flags,
        }
        self.append_execution_result(execution, details)
        self.audit_log(
            execution_id=str(execution.id),
            step="incident_response",
            outcome="success",
            payload_in=context,
            payload_out=details,
        )
        return ExecutionResult(status="completed", summary="Incident response executed", details=details)

    def rollback(self, execution_id: str) -> RollbackResult:
        execution = self.get_execution(execution_id)
        previous_flags = dict(execution.result.get("previous_flags", {}))
        rows = self.db.scalars(select(ActionRegistry).where(ActionRegistry.name.in_(list(previous_flags)))).all()
        for row in rows:
            row.is_active = bool(previous_flags.get(row.name, row.is_active))
            self.db.add(row)
        self.db.commit()

        ticket_id = execution.result.get("ticket_id")
        if ticket_id:
            self.ticketing.update_ticket(ticket_id=ticket_id, status="resolved", comment="Incident rollback")

        details = {
            "access_frozen": False,
            "restored_actions": list(previous_flags),
            "rolled_back_at": datetime.now(UTC).isoformat(),
        }
        self.append_execution_result(execution, details)
        self.audit_log(
            execution_id=execution_id,
            step="rollback_incident_response",
            outcome="rolled_back",
            payload_in={"execution_id": execution_id},
            payload_out=details,
        )
        return RollbackResult(status="rolled_back", summary="Incident rollback completed", details=details)


class PolicyUpdate(BaseAction):
    name = "policy_update"

    def dry_run(self, context: dict[str, Any]) -> PreviewResult:
        version = context.get("policy_version", "v1")
        rules = dict(context.get("rules", {}))
        return PreviewResult(
            preview_only=True,
            summary="Policy update would validate and apply policy metadata",
            details={"policy_version": version, "rule_count": len(rules)},
        )

    def execute(self, context: dict[str, Any]) -> ExecutionResult:
        execution = self.get_execution(context["execution_id"])
        policy_version = str(context.get("policy_version", "v1"))
        rules = dict(context.get("rules", {}))
        existing_data = list(context.get("existing_data", []))

        required_keys = ["scope", "retention_days"]
        missing = [key for key in required_keys if key not in rules]
        if missing:
            raise ValueError(f"Policy rules missing required keys: {', '.join(missing)}")

        validation = {
            "records_checked": len(existing_data),
            "violations": [item for item in existing_data if item.get("retention_days", 0) > rules["retention_days"]],
        }

        rows = self.db.scalars(select(ActionRegistry)).all()
        previous_permissions = {row.name: list(row.required_permissions or []) for row in rows}
        for row in rows:
            marker = f"policy:{policy_version}"
            perms = list(row.required_permissions or [])
            if marker not in perms:
                perms.append(marker)
            row.required_permissions = perms
            self.db.add(row)
        self.db.commit()

        details = {
            "policy_version": policy_version,
            "rules": rules,
            "validation": validation,
            "previous_permissions": previous_permissions,
        }
        self.append_execution_result(execution, details)
        self.audit_log(
            execution_id=str(execution.id),
            step="policy_update",
            outcome="success",
            payload_in=context,
            payload_out=details,
        )
        return ExecutionResult(status="completed", summary="Policy update applied", details=details)

    def rollback(self, execution_id: str) -> RollbackResult:
        execution = self.get_execution(execution_id)
        previous_permissions = dict(execution.result.get("previous_permissions", {}))
        rows = self.db.scalars(select(ActionRegistry).where(ActionRegistry.name.in_(list(previous_permissions)))).all()
        for row in rows:
            row.required_permissions = previous_permissions.get(row.name, row.required_permissions)
            self.db.add(row)
        self.db.commit()

        details = {
            "restored_actions": list(previous_permissions),
            "rolled_back_at": datetime.now(UTC).isoformat(),
        }
        self.append_execution_result(execution, details)
        self.audit_log(
            execution_id=execution_id,
            step="rollback_policy_update",
            outcome="rolled_back",
            payload_in={"execution_id": execution_id},
            payload_out=details,
        )
        return RollbackResult(status="rolled_back", summary="Policy rollback completed", details=details)


class ConnectorRefresh(BaseAction):
    name = "connector_refresh"

    def __init__(self, db: Session, ticketing: TicketingClient, actor: str = "system") -> None:
        super().__init__(db=db, actor=actor)
        self.ticketing = ticketing

    def dry_run(self, context: dict[str, Any]) -> PreviewResult:
        stored = dict(context.get("stored_schema", {}))
        fetched = dict(context.get("fetched_schema", {}))
        return PreviewResult(
            preview_only=True,
            summary="Connector refresh would diff schemas and alert on changes",
            details={"stored_keys": sorted(stored.keys()), "fetched_keys": sorted(fetched.keys())},
        )

    def execute(self, context: dict[str, Any]) -> ExecutionResult:
        execution = self.get_execution(context["execution_id"])
        stored = dict(context.get("stored_schema", {}))
        fetched = dict(context.get("fetched_schema", {}))

        added = sorted([key for key in fetched if key not in stored])
        removed = sorted([key for key in stored if key not in fetched])
        changed = sorted([key for key in fetched if key in stored and fetched[key] != stored[key]])

        diff = {"added": added, "removed": removed, "changed": changed}
        ticket_id = None
        if added or removed or changed:
            ticket_id = self.ticketing.create_ticket(
                title="Connector Schema Drift",
                description="Schema diff detected during refresh",
                metadata={"execution_id": str(execution.id), "diff": diff},
            )

        details = {
            "connector": context.get("connector", "default"),
            "schema_diff": diff,
            "ticket_id": ticket_id,
            "refreshed_at": datetime.now(UTC).isoformat(),
        }
        self.append_execution_result(execution, details)
        self.audit_log(
            execution_id=str(execution.id),
            step="connector_refresh",
            outcome="success",
            payload_in=context,
            payload_out=details,
        )
        return ExecutionResult(status="completed", summary="Connector refresh completed", details=details)

    def rollback(self, execution_id: str) -> RollbackResult:
        execution = self.get_execution(execution_id)
        details = {
            "connector": execution.result.get("connector"),
            "rollback": "connector refresh is metadata-only; no data mutation to revert",
            "rolled_back_at": datetime.now(UTC).isoformat(),
        }
        self.append_execution_result(execution, details)
        self.audit_log(
            execution_id=execution_id,
            step="rollback_connector_refresh",
            outcome="rolled_back",
            payload_in={"execution_id": execution_id},
            payload_out=details,
        )
        return RollbackResult(status="rolled_back", summary="Connector rollback recorded", details=details)


class AuditExport(BaseAction):
    name = "audit_export"

    def dry_run(self, context: dict[str, Any]) -> PreviewResult:
        limit = int(context.get("limit", 100))
        return PreviewResult(
            preview_only=True,
            summary="Audit export would serialize and sign audit log records",
            details={"limit": limit},
        )

    def execute(self, context: dict[str, Any]) -> ExecutionResult:
        from app.workers.tasks import audit_export_delivery_task

        execution = self.get_execution(context["execution_id"])
        limit = int(context.get("limit", 100))
        rows = self.db.scalars(
            select(ActionAuditLog).order_by(ActionAuditLog.timestamp.desc()).limit(limit)
        ).all()
        serialized = [
            {
                "id": str(row.id),
                "execution_id": str(row.execution_id),
                "step_name": row.step_name,
                "actor": row.actor,
                "outcome": row.outcome,
                "payload_hash": row.payload_hash,
                "timestamp": row.timestamp.isoformat(),
            }
            for row in rows
        ]
        secret = get_settings().tokenization_secret_key
        signature = self.sign_payload({"audit": serialized}, secret=secret)
        audit_export_delivery_task.delay(str(execution.id))

        details = {
            "exported_records": len(serialized),
            "signature": signature,
            "delivery": "queued",
            "artifact": serialized,
        }
        self.append_execution_result(execution, details)
        self.audit_log(
            execution_id=str(execution.id),
            step="audit_export",
            outcome="success",
            payload_in={"limit": limit},
            payload_out={"exported_records": len(serialized), "signature": signature},
        )
        return ExecutionResult(status="completed", summary="Audit export completed", details=details)

    def rollback(self, execution_id: str) -> RollbackResult:
        execution = self.get_execution(execution_id)
        details = {
            "delivery": "revoked",
            "rolled_back_at": datetime.now(UTC).isoformat(),
        }
        self.append_execution_result(execution, details)
        self.audit_log(
            execution_id=execution_id,
            step="rollback_audit_export",
            outcome="rolled_back",
            payload_in={"execution_id": execution_id},
            payload_out=details,
        )
        return RollbackResult(status="rolled_back", summary="Audit export rollback completed", details=details)


class SegmentActivation(BaseAction):
    name = "segment_activation"

    def dry_run(self, context: dict[str, Any]) -> PreviewResult:
        audience = list(context.get("audience", []))
        return PreviewResult(
            preview_only=True,
            summary="Segment activation would filter audience by rules and export",
            details={"audience_count": len(audience), "rules": context.get("rules", {})},
        )

    def execute(self, context: dict[str, Any]) -> ExecutionResult:
        execution = self.get_execution(context["execution_id"])
        audience = list(context.get("audience", []))
        rules = dict(context.get("rules", {}))
        target = context.get("target", "default-connector")

        def matches(item: dict[str, Any]) -> bool:
            for field, expected in rules.items():
                value = item.get(field)
                if isinstance(expected, list):
                    if value not in expected:
                        return False
                elif value != expected:
                    return False
            return True

        filtered = [item for item in audience if matches(item)]
        details = {
            "target": target,
            "selected_count": len(filtered),
            "selected_ids": [item.get("id") for item in filtered],
            "rules": rules,
        }
        self.append_execution_result(execution, details)
        self.audit_log(
            execution_id=str(execution.id),
            step="segment_activation",
            outcome="success",
            payload_in={"audience_count": len(audience), "rules": rules},
            payload_out=details,
        )
        return ExecutionResult(status="completed", summary="Segment activated", details=details)

    def rollback(self, execution_id: str) -> RollbackResult:
        execution = self.get_execution(execution_id)
        selected_ids = list(execution.result.get("selected_ids", []))
        details = {
            "deactivated_ids": selected_ids,
            "rolled_back_at": datetime.now(UTC).isoformat(),
        }
        self.append_execution_result(execution, details)
        self.audit_log(
            execution_id=execution_id,
            step="rollback_segment_activation",
            outcome="rolled_back",
            payload_in={"execution_id": execution_id},
            payload_out=details,
        )
        return RollbackResult(status="rolled_back", summary="Segment activation rollback completed", details=details)


class ScheduledReporting(BaseAction):
    name = "scheduled_reporting"

    def dry_run(self, context: dict[str, Any]) -> PreviewResult:
        return PreviewResult(
            preview_only=True,
            summary="Scheduled report would aggregate compliance execution metrics",
            details={"recipient": context.get("recipient", "compliance@example.com")},
        )

    def execute(self, context: dict[str, Any]) -> ExecutionResult:
        from app.workers.tasks import scheduled_reporting_task

        execution = self.get_execution(context["execution_id"])
        rows = self.db.scalars(select(ActionExecution)).all()
        counts: dict[str, int] = {}
        for row in rows:
            key = row.status.value
            counts[key] = counts.get(key, 0) + 1

        report = {
            "generated_at": datetime.now(UTC).isoformat(),
            "execution_counts": counts,
            "recipient": context.get("recipient", "compliance@example.com"),
        }
        scheduled_reporting_task.delay()

        self.append_execution_result(execution, {"report": report, "delivery": "queued"})
        self.audit_log(
            execution_id=str(execution.id),
            step="scheduled_reporting",
            outcome="success",
            payload_in=context,
            payload_out=report,
        )
        return ExecutionResult(status="completed", summary="Scheduled reporting completed", details=report)

    def rollback(self, execution_id: str) -> RollbackResult:
        execution = self.get_execution(execution_id)
        details = {
            "report_delivery": "cancelled",
            "rolled_back_at": datetime.now(UTC).isoformat(),
        }
        self.append_execution_result(execution, details)
        self.audit_log(
            execution_id=execution_id,
            step="rollback_scheduled_reporting",
            outcome="rolled_back",
            payload_in={"execution_id": execution_id},
            payload_out=details,
        )
        return RollbackResult(status="rolled_back", summary="Scheduled reporting rollback completed", details=details)


ACTION_REGISTRY: dict[str, type[BaseAction]] = {
    "dsar_request": DSARRequest,
    "erasure_request": ErasureRequest,
    "escalate_to_manager": EscalateToManager,
    "bulk_soft_delete": BulkSoftDelete,
    "field_masking_update": FieldMaskingUpdate,
    "consent_withdrawal": ConsentWithdrawal,
    "incident_response": IncidentResponse,
    "policy_update": PolicyUpdate,
    "connector_refresh": ConnectorRefresh,
    "audit_export": AuditExport,
    "segment_activation": SegmentActivation,
    "scheduled_reporting": ScheduledReporting,
}
