from __future__ import annotations

from dataclasses import asdict, dataclass


ALLOWED_RISK_CLASSIFICATIONS = {"low", "medium", "high", "critical"}


@dataclass(slots=True)
class ActionTemplateSchema:
    action_id: str
    trigger: str
    required_data_scope: list[str]
    required_permissions: list[str]
    approval_requirements: dict[str, object]
    input_schema: dict[str, object]
    execution_steps: list[str]
    output_schema: dict[str, object]
    risk_classification: str
    audit_implications: list[str]
    allowed_personas: list[str]
    prohibited_actions: list[str]
    reversible: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


ACTION_TEMPLATE_REGISTRY: dict[str, ActionTemplateSchema] = {
    "DSAR_EXECUTE": ActionTemplateSchema(
        action_id="DSAR_EXECUTE",
        trigger="dsar_request_received",
        required_data_scope=["identity", "records", "audit"],
        required_permissions=["compliance.execute", "subject.verify"],
        approval_requirements={"required": True, "approver_role": "compliance_officer"},
        input_schema={"subject_identifier": "string", "delivery_method": "string"},
        execution_steps=["identify", "aggregate", "redact", "deliver", "attest"],
        output_schema={"request_id": "string", "status": "string", "proof_id": "string"},
        risk_classification="high",
        audit_implications=["legal_evidence", "timeline_proof"],
        allowed_personas=["it_head", "executive", "admin_staff"],
        prohibited_actions=["silent_skip_redaction"],
        reversible=False,
    ),
    "ERASURE_EXECUTE": ActionTemplateSchema(
        action_id="ERASURE_EXECUTE",
        trigger="erasure_request_approved",
        required_data_scope=["identity", "records", "retention"],
        required_permissions=["compliance.execute", "deletion.execute"],
        approval_requirements={"required": True, "approver_role": "compliance_officer"},
        input_schema={"subject_identifier": "string", "legal_basis": "string"},
        execution_steps=["identify", "delete_or_pseudonymize", "verify", "attest"],
        output_schema={"request_id": "string", "deletion_certificate": "string"},
        risk_classification="critical",
        audit_implications=["deletion_proof", "regulatory_attestation"],
        allowed_personas=["it_head", "executive"],
        prohibited_actions=["delete_legal_hold_records"],
        reversible=False,
    ),
    "ESCALATE_TO_MANAGER": ActionTemplateSchema(
        action_id="ESCALATE_TO_MANAGER",
        trigger="approval_sla_breached",
        required_data_scope=["workflow", "identity"],
        required_permissions=["workflow.escalate"],
        approval_requirements={"required": False},
        input_schema={"workflow_id": "string", "reason": "string"},
        execution_steps=["attach_evidence", "notify_manager", "set_deadline"],
        output_schema={"escalation_id": "string", "notified": "boolean"},
        risk_classification="medium",
        audit_implications=["manager_notification_log"],
        allowed_personas=["it_head", "admin_staff", "executive"],
        prohibited_actions=["escalate_without_evidence"],
        reversible=True,
    ),
    "BULK_SOFT_DELETE": ActionTemplateSchema(
        action_id="BULK_SOFT_DELETE",
        trigger="bulk_delete_request_approved",
        required_data_scope=["records", "audit"],
        required_permissions=["records.soft_delete"],
        approval_requirements={"required": True, "approver_role": "it_head"},
        input_schema={"entity": "string", "record_ids": "array"},
        execution_steps=["validate_scope", "soft_delete", "verify"],
        output_schema={"job_id": "string", "deleted_count": "integer"},
        risk_classification="high",
        audit_implications=["record_state_change_log"],
        allowed_personas=["it_head", "admin_staff"],
        prohibited_actions=["hard_delete_without_erasure_flow"],
        reversible=True,
    ),
    "FIELD_MASKING_UPDATE": ActionTemplateSchema(
        action_id="FIELD_MASKING_UPDATE",
        trigger="masking_change_submitted",
        required_data_scope=["schema", "policy"],
        required_permissions=["policy.update", "masking.update"],
        approval_requirements={"required": True, "approver_role": "compliance_officer"},
        input_schema={"field_path": "string", "mask_pattern": "string"},
        execution_steps=["validate_field", "apply_policy", "run_canary_validation"],
        output_schema={"policy_id": "string", "affected_users": "integer"},
        risk_classification="high",
        audit_implications=["policy_change_log", "impact_report"],
        allowed_personas=["it_head", "admin_staff"],
        prohibited_actions=["unmask_restricted_fields_without_approval"],
        reversible=True,
    ),
    "CONSENT_WITHDRAWAL": ActionTemplateSchema(
        action_id="CONSENT_WITHDRAWAL",
        trigger="consent_revoked",
        required_data_scope=["consent", "marketing", "analytics"],
        required_permissions=["consent.manage", "records.update"],
        approval_requirements={"required": False},
        input_schema={"subject_identifier": "string", "consent_type": "string"},
        execution_steps=["record_withdrawal", "disable_downstream_use", "confirm"],
        output_schema={"status": "string", "effective_at": "timestamp"},
        risk_classification="medium",
        audit_implications=["consent_timeline_log"],
        allowed_personas=["it_head", "admin_staff", "executive"],
        prohibited_actions=["retain_marketing_processing_after_withdrawal"],
        reversible=False,
    ),
    "INCIDENT_RESPONSE": ActionTemplateSchema(
        action_id="INCIDENT_RESPONSE",
        trigger="security_incident_detected",
        required_data_scope=["audit", "security", "identity"],
        required_permissions=["incident.execute", "access.freeze"],
        approval_requirements={"required": True, "approver_role": "security_lead"},
        input_schema={"incident_id": "string", "severity": "string"},
        execution_steps=["contain", "collect_evidence", "notify", "track_remediation"],
        output_schema={"incident_id": "string", "forensic_bundle_id": "string"},
        risk_classification="critical",
        audit_implications=["forensic_chain_of_custody", "regulatory_notification_log"],
        allowed_personas=["it_head", "executive"],
        prohibited_actions=["drop_incident_evidence"],
        reversible=False,
    ),
    "POLICY_UPDATE": ActionTemplateSchema(
        action_id="POLICY_UPDATE",
        trigger="policy_change_approved",
        required_data_scope=["policy", "schema", "audit"],
        required_permissions=["policy.update"],
        approval_requirements={"required": True, "approver_role": "it_head"},
        input_schema={"policy_id": "string", "changes": "object"},
        execution_steps=["validate", "deploy", "post_deploy_check"],
        output_schema={"policy_id": "string", "deployed": "boolean"},
        risk_classification="high",
        audit_implications=["policy_version_history"],
        allowed_personas=["it_head", "admin_staff"],
        prohibited_actions=["deploy_unvalidated_policy"],
        reversible=True,
    ),
    "CONNECTOR_REFRESH": ActionTemplateSchema(
        action_id="CONNECTOR_REFRESH",
        trigger="connector_schema_drift_detected",
        required_data_scope=["connector", "schema"],
        required_permissions=["connector.sync"],
        approval_requirements={"required": False},
        input_schema={"connector_id": "string", "force": "boolean"},
        execution_steps=["sync", "diff_schema", "publish_alerts"],
        output_schema={"connector_id": "string", "fields_changed": "integer"},
        risk_classification="medium",
        audit_implications=["connector_sync_log"],
        allowed_personas=["it_head", "admin_staff"],
        prohibited_actions=["skip_drift_alert"],
        reversible=True,
    ),
    "AUDIT_EXPORT": ActionTemplateSchema(
        action_id="AUDIT_EXPORT",
        trigger="audit_export_requested",
        required_data_scope=["audit"],
        required_permissions=["audit.export"],
        approval_requirements={"required": True, "approver_role": "compliance_officer"},
        input_schema={"from": "timestamp", "to": "timestamp", "format": "string"},
        execution_steps=["collect", "sign", "encrypt", "deliver"],
        output_schema={"export_id": "string", "signature": "string"},
        risk_classification="high",
        audit_implications=["evidence_export_log"],
        allowed_personas=["it_head", "executive", "admin_staff"],
        prohibited_actions=["unsigned_export"],
        reversible=False,
    ),
    "SEGMENT_ACTIVATION": ActionTemplateSchema(
        action_id="SEGMENT_ACTIVATION",
        trigger="segment_activation_requested",
        required_data_scope=["consent", "audience", "policy"],
        required_permissions=["segment.activate"],
        approval_requirements={"required": True, "approver_role": "marketing_owner"},
        input_schema={"segment_id": "string", "destination": "string"},
        execution_steps=["validate_consent", "export_segment", "confirm_delivery"],
        output_schema={"activation_id": "string", "status": "string"},
        risk_classification="high",
        audit_implications=["consent_scope_proof", "activation_log"],
        allowed_personas=["it_head", "admin_staff"],
        prohibited_actions=["activate_without_consent"],
        reversible=True,
    ),
    "SCHEDULED_REPORTING": ActionTemplateSchema(
        action_id="SCHEDULED_REPORTING",
        trigger="schedule_tick",
        required_data_scope=["reporting", "audit"],
        required_permissions=["report.run"],
        approval_requirements={"required": False},
        input_schema={"report_id": "string", "frequency": "string"},
        execution_steps=["collect_data", "render", "deliver", "record_status"],
        output_schema={"run_id": "string", "status": "string"},
        risk_classification="low",
        audit_implications=["report_delivery_log"],
        allowed_personas=["it_head", "admin_staff", "executive"],
        prohibited_actions=["deliver_unmasked_report"],
        reversible=True,
    ),
}


def list_action_templates() -> list[dict[str, object]]:
    return [schema.to_dict() for schema in ACTION_TEMPLATE_REGISTRY.values()]


def get_action_template(action_id: str) -> dict[str, object] | None:
    schema = ACTION_TEMPLATE_REGISTRY.get(action_id)
    if schema is None:
        return None
    return schema.to_dict()


def validate_action_registry() -> list[str]:
    errors: list[str] = []
    for action_id, schema in ACTION_TEMPLATE_REGISTRY.items():
        if action_id != schema.action_id:
            errors.append(f"registry key mismatch for {action_id}")
        if schema.risk_classification not in ALLOWED_RISK_CLASSIFICATIONS:
            errors.append(f"invalid risk classification for {action_id}")
        if not schema.execution_steps:
            errors.append(f"missing execution_steps for {action_id}")
        if not schema.required_permissions:
            errors.append(f"missing required_permissions for {action_id}")
        if not schema.allowed_personas:
            errors.append(f"missing allowed_personas for {action_id}")
    return errors


def action_registry_health() -> dict[str, object]:
    errors = validate_action_registry()
    return {
        "healthy": not errors,
        "template_count": len(ACTION_TEMPLATE_REGISTRY),
        "errors": errors,
    }
