from __future__ import annotations

import argparse
import uuid
from typing import Any

from sqlalchemy import select

from app.agents.handlers import HANDLER_REGISTRY
from app.db.enums import AgentDefinitionStatus, TriggerType
from app.db.models import AgentDefinition, TenantAgentConfig
from app.db.session import SessionLocal

AGENT_SEED_DEFINITIONS: list[dict[str, Any]] = [
    {
        "agent_key": "result_notification_v1",
        "name": "Result Notification",
        "description": "Send result publication notifications with improvement suggestions",
        "version": "1.0.0",
        "domain": "academics",
        "trigger_type": TriggerType.EVENT,
        "trigger_config": {
            "event_type": "result_published",
            "keywords": ["result", "marks", "grade", "score"],
        },
        "trigger_config_schema": {"type": "object", "required": ["event_type"]},
        "required_data_scope": ["student_alias", "overall_result", "attendance_pct", "subjects"],
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "rbac_permissions": {"allowed_personas": ["student", "faculty", "admin"]},
        "constraints": {},
        "output_type": "write",
        "requires_confirmation": False,
        "approval_level": "system",
        "allowed_personas": ["student", "faculty", "admin"],
        "confirmation_prompt": None,
        "chain_to": [],
        "allowed_output_channels": ["in_app", "email"],
        "handler_class": "ResultNotificationHandler",
        "is_side_effect": True,
        "risk_level": "medium",
        "is_sensitive_monitor": False,
        "is_active": True,
        "status": AgentDefinitionStatus.ACTIVE,
        "risk_rank": 35,
        "tenant_config": {
            "notification_channel": "in_app",
            "semester_filter": "current",
            "improvement_rules": [
                {
                    "rule_id": "attendance_alert",
                    "condition": "attendance_pct < 75",
                    "suggestion_text": "Meet your faculty advisor for attendance recovery planning.",
                }
            ],
            "message_template": (
                "Your result update is now available. Attendance: {attendance_pct}%.\n\n"
                "Suggested actions:\n{suggestions}"
            ),
        },
    },
    {
        "agent_key": "fee_reminder_v1",
        "name": "Fee Reminder",
        "description": "Send scheduled reminders for pending fee dues",
        "version": "1.0.0",
        "domain": "finance",
        "trigger_type": TriggerType.SCHEDULED,
        "trigger_config": {
            "schedule": "0 10 * * *",
            "keywords": ["fee", "dues", "payment", "reminder"],
        },
        "trigger_config_schema": {"type": "object"},
        "required_data_scope": ["student_alias", "outstanding_amount", "due_date", "payment_link"],
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "rbac_permissions": {"allowed_personas": ["student", "finance", "admin"]},
        "constraints": {},
        "output_type": "write",
        "requires_confirmation": False,
        "approval_level": "system",
        "allowed_personas": ["student", "finance", "admin"],
        "confirmation_prompt": None,
        "chain_to": [],
        "allowed_output_channels": ["in_app", "sms", "email"],
        "handler_class": "FeeReminderHandler",
        "is_side_effect": True,
        "risk_level": "low",
        "is_sensitive_monitor": False,
        "is_active": True,
        "status": AgentDefinitionStatus.ACTIVE,
        "risk_rank": 20,
        "tenant_config": {
            "channel": "in_app",
            "message_template": (
                "Reminder: You have an outstanding fee amount of Rs. {outstanding_amount} due on {due_date}. "
                "Pay securely via {payment_link}."
            ),
            "days_before_due": 7,
            "dedup_window_hours": 24,
        },
    },
    {
        "agent_key": "upi_payment_v1",
        "name": "UPI Payment",
        "description": "Generate secure UPI payment links for fee payments",
        "version": "1.0.0",
        "domain": "finance",
        "trigger_type": TriggerType.USER_QUERY,
        "trigger_config": {
            "keywords": ["pay fee", "upi", "payment link", "pay now"],
        },
        "trigger_config_schema": {"type": "object"},
        "required_data_scope": ["student_alias", "outstanding_amount", "due_date", "fee_record_alias"],
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "rbac_permissions": {"allowed_personas": ["student"]},
        "constraints": {},
        "output_type": "write",
        "requires_confirmation": True,
        "approval_level": "user",
        "allowed_personas": ["student"],
        "confirmation_prompt": "Generate payment link for your pending fee amount?",
        "chain_to": [],
        "allowed_output_channels": ["in_app"],
        "handler_class": "UpiPaymentHandler",
        "is_side_effect": True,
        "risk_level": "medium",
        "is_sensitive_monitor": False,
        "is_active": True,
        "status": AgentDefinitionStatus.ACTIVE,
        "risk_rank": 45,
        "tenant_config": {
            "payment_gateway": {
                "type": "razorpay",
                "api_key": "replace-me",
                "merchant_upi_id": "college@upi",
            }
        },
    },
    {
        "agent_key": "refund_processing_v1",
        "name": "Refund Processing",
        "description": "Submit refund workflow requests for eligible cases",
        "version": "1.0.0",
        "domain": "finance",
        "trigger_type": TriggerType.USER_QUERY,
        "trigger_config": {
            "keywords": ["refund", "fee refund", "money back"],
        },
        "trigger_config_schema": {"type": "object"},
        "required_data_scope": ["student_alias", "refund_amount", "reason", "payment_alias"],
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "rbac_permissions": {"allowed_personas": ["student", "finance"]},
        "constraints": {},
        "output_type": "write",
        "requires_confirmation": True,
        "approval_level": "finance",
        "allowed_personas": ["student", "finance"],
        "confirmation_prompt": "Submit this refund request to finance?",
        "chain_to": [],
        "allowed_output_channels": ["in_app"],
        "handler_class": "RefundProcessingHandler",
        "is_side_effect": True,
        "risk_level": "high",
        "is_sensitive_monitor": False,
        "is_active": True,
        "status": AgentDefinitionStatus.BETA,
        "risk_rank": 60,
        "tenant_config": {
            "workflow_system": "internal_finance",
            "finance_team_queue": "refunds",
            "finance_team_alias": "finance-team",
            "eligibility_rules": [
                {
                    "field": "days_since_payment",
                    "operator": "lte",
                    "value": 30,
                    "reason": "Refunds are allowed only within 30 days.",
                }
            ],
            "processing_days": 7,
        },
    },
    {
        "agent_key": "email_draft_send_v1",
        "name": "Email Draft and Send",
        "description": "Create drafts or send templated emails through approved aliases",
        "version": "1.0.0",
        "domain": "communications",
        "trigger_type": TriggerType.USER_QUERY,
        "trigger_config": {
            "keywords": ["draft email", "send email", "mail"],
        },
        "trigger_config_schema": {"type": "object"},
        "required_data_scope": ["subject", "body", "recipient_alias"],
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "rbac_permissions": {"allowed_personas": ["faculty", "admin", "staff"]},
        "constraints": {},
        "output_type": "write",
        "requires_confirmation": True,
        "approval_level": "user",
        "allowed_personas": ["faculty", "admin", "staff"],
        "confirmation_prompt": "Send this email now?",
        "chain_to": [],
        "allowed_output_channels": ["in_app"],
        "handler_class": "EmailDraftSendHandler",
        "is_side_effect": True,
        "risk_level": "medium",
        "is_sensitive_monitor": False,
        "is_active": True,
        "status": AgentDefinitionStatus.BETA,
        "risk_rank": 50,
        "tenant_config": {
            "draft_only": True,
            "email_templates": {
                "general": {
                    "to_alias": "recipient",
                    "template": "Subject: {subject}\n\n{body}",
                }
            },
        },
    },
    {
        "agent_key": "bulk_notification_v1",
        "name": "Bulk Notification",
        "description": "Send controlled bulk alerts to selected groups",
        "version": "1.0.0",
        "domain": "communications",
        "trigger_type": TriggerType.USER_QUERY,
        "trigger_config": {
            "keywords": ["bulk message", "announce", "notify all"],
        },
        "trigger_config_schema": {"type": "object"},
        "required_data_scope": ["recipient_aliases", "message", "subject"],
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "rbac_permissions": {"allowed_personas": ["admin", "faculty"]},
        "constraints": {},
        "output_type": "write",
        "requires_confirmation": True,
        "approval_level": "admin",
        "allowed_personas": ["admin", "faculty"],
        "confirmation_prompt": "Send this bulk notification to selected recipients?",
        "chain_to": [],
        "allowed_output_channels": ["in_app", "email"],
        "handler_class": "BulkNotificationHandler",
        "is_side_effect": True,
        "risk_level": "high",
        "is_sensitive_monitor": False,
        "is_active": True,
        "status": AgentDefinitionStatus.BETA,
        "risk_rank": 65,
        "tenant_config": {
            "channel": "in_app",
            "daily_user_notification_limit": 3,
        },
    },
    {
        "agent_key": "leave_approval_v1",
        "name": "Leave Approval",
        "description": "Submit leave requests with policy and balance checks",
        "version": "1.0.0",
        "domain": "hr",
        "trigger_type": TriggerType.USER_QUERY,
        "trigger_config": {
            "keywords": ["apply leave", "leave request", "vacation"],
        },
        "trigger_config_schema": {"type": "object"},
        "required_data_scope": ["leave_type", "leave_balance", "days_requested", "requested_dates"],
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "rbac_permissions": {"allowed_personas": ["staff", "faculty", "admin"]},
        "constraints": {},
        "output_type": "write",
        "requires_confirmation": True,
        "approval_level": "manager",
        "allowed_personas": ["staff", "faculty", "admin"],
        "confirmation_prompt": "Submit leave application for manager approval?",
        "chain_to": [],
        "allowed_output_channels": ["in_app"],
        "handler_class": "LeaveApprovalHandler",
        "is_side_effect": True,
        "risk_level": "medium",
        "is_sensitive_monitor": False,
        "is_active": True,
        "status": AgentDefinitionStatus.ACTIVE,
        "risk_rank": 40,
        "tenant_config": {
            "hr_system": {"provider": "internal_hr"},
        },
    },
    {
        "agent_key": "meeting_scheduler_v1",
        "name": "Meeting Scheduler",
        "description": "Schedule meetings and send invites after confirmation",
        "version": "1.0.0",
        "domain": "productivity",
        "trigger_type": TriggerType.USER_QUERY,
        "trigger_config": {
            "keywords": ["schedule meeting", "book meeting", "invite"],
        },
        "trigger_config_schema": {"type": "object"},
        "required_data_scope": ["meeting_title", "invitee_aliases", "best_slot"],
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "rbac_permissions": {"allowed_personas": ["staff", "faculty", "admin"]},
        "constraints": {},
        "output_type": "write",
        "requires_confirmation": True,
        "approval_level": "user",
        "allowed_personas": ["staff", "faculty", "admin"],
        "confirmation_prompt": "Confirm this meeting slot and send invites?",
        "chain_to": [],
        "allowed_output_channels": ["in_app"],
        "handler_class": "MeetingSchedulerHandler",
        "is_side_effect": True,
        "risk_level": "medium",
        "is_sensitive_monitor": False,
        "is_active": True,
        "status": AgentDefinitionStatus.ACTIVE,
        "risk_rank": 35,
        "tenant_config": {
            "calendar_system": {"provider": "google"},
        },
    },
    {
        "agent_key": "payroll_query_v1",
        "name": "Payroll Query",
        "description": "Read-only payroll response generation with monitor dependency",
        "version": "1.0.0",
        "domain": "hr",
        "trigger_type": TriggerType.USER_QUERY,
        "trigger_config": {
            "keywords": ["salary", "payroll", "payslip"],
            "depends_on": ["sensitive_field_monitor_v1"],
        },
        "trigger_config_schema": {"type": "object"},
        "required_data_scope": ["pay_period", "gross_salary", "net_salary", "payslip_available"],
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "rbac_permissions": {"allowed_personas": ["staff", "faculty", "admin"]},
        "constraints": {},
        "output_type": "read",
        "requires_confirmation": False,
        "approval_level": "none",
        "allowed_personas": ["staff", "faculty", "admin"],
        "confirmation_prompt": None,
        "chain_to": [],
        "allowed_output_channels": ["in_app"],
        "handler_class": "PayrollQueryHandler",
        "is_side_effect": False,
        "risk_level": "high",
        "is_sensitive_monitor": False,
        "is_active": True,
        "status": AgentDefinitionStatus.BETA,
        "risk_rank": 70,
        "tenant_config": {
            "response_template": "payroll_summary",
        },
    },
    {
        "agent_key": "leave_balance_v1",
        "name": "Leave Balance",
        "description": "Show leave balance and pending requests",
        "version": "1.0.0",
        "domain": "hr",
        "trigger_type": TriggerType.USER_QUERY,
        "trigger_config": {
            "keywords": ["leave balance", "remaining leave", "leave status"],
        },
        "trigger_config_schema": {"type": "object"},
        "required_data_scope": ["leave_balance", "pending_requests"],
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "rbac_permissions": {"allowed_personas": ["staff", "faculty", "admin"]},
        "constraints": {},
        "output_type": "read",
        "requires_confirmation": False,
        "approval_level": "none",
        "allowed_personas": ["staff", "faculty", "admin"],
        "confirmation_prompt": None,
        "chain_to": ["leave_approval_v1"],
        "allowed_output_channels": ["in_app"],
        "handler_class": "LeaveBalanceHandler",
        "is_side_effect": False,
        "risk_level": "low",
        "is_sensitive_monitor": False,
        "is_active": True,
        "status": AgentDefinitionStatus.ACTIVE,
        "risk_rank": 15,
        "tenant_config": {
            "check_only": True,
        },
    },
    {
        "agent_key": "sensitive_field_monitor_v1",
        "name": "Sensitive Field Monitor",
        "description": "Detect anomalous sensitive data access patterns",
        "version": "1.0.0",
        "domain": "security",
        "trigger_type": TriggerType.CONTINUOUS,
        "trigger_config": {
            "keywords": ["monitor", "sensitive", "security"],
        },
        "trigger_config_schema": {"type": "object"},
        "required_data_scope": ["sensitive_accesses_this_hour", "recent_field_combinations"],
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "rbac_permissions": {"allowed_personas": ["system", "admin", "compliance"]},
        "constraints": {},
        "output_type": "write",
        "requires_confirmation": False,
        "approval_level": "system",
        "allowed_personas": ["system", "admin", "compliance"],
        "confirmation_prompt": None,
        "chain_to": [],
        "allowed_output_channels": ["in_app", "email"],
        "handler_class": "SensitiveFieldMonitorHandler",
        "is_side_effect": True,
        "risk_level": "critical",
        "is_sensitive_monitor": True,
        "is_active": True,
        "status": AgentDefinitionStatus.ACTIVE,
        "risk_rank": 85,
        "tenant_config": {
            "it_head_email": "it-head@example.edu",
            "auto_suspend_on_critical": True,
            "thresholds": {
                "volume_per_hour": 10,
                "bulk_result_rows": 20,
                "probing_queries": 5,
                "probing_window_minutes": 10,
                "after_hours_start": 20,
                "after_hours_end": 8,
            },
        },
    },
]


def validate_seed_payload(template_payload: dict[str, Any], tenant_config: dict[str, Any]) -> None:
    handler_name = str(template_payload["handler_class"])
    handler_type = HANDLER_REGISTRY.get(handler_name)
    if handler_type is None:
        raise ValueError(f"Unknown handler class in seed payload: {handler_name}")

    handler = handler_type()
    validation_errors = handler.validate_config(tenant_config)
    if validation_errors:
        raise ValueError(
            f"Invalid config for {template_payload['agent_key']}: " + "; ".join(validation_errors)
        )


def upsert_template_and_instance(tenant_id: uuid.UUID) -> tuple[int, int]:
    created_or_updated_templates = 0
    created_or_updated_instances = 0

    with SessionLocal() as session:
        for definition in AGENT_SEED_DEFINITIONS:
            template_payload = {k: v for k, v in definition.items() if k != "tenant_config"}
            tenant_config = dict(definition.get("tenant_config", {}))

            validate_seed_payload(template_payload, tenant_config)

            existing_template = session.scalar(
                select(AgentDefinition).where(AgentDefinition.agent_key == template_payload["agent_key"])
            )
            if existing_template is None:
                existing_template = AgentDefinition(**template_payload)
                session.add(existing_template)
            else:
                for field, value in template_payload.items():
                    setattr(existing_template, field, value)
            session.flush()
            created_or_updated_templates += 1

            existing_instance = session.scalar(
                select(TenantAgentConfig).where(
                    TenantAgentConfig.tenant_id == tenant_id,
                    TenantAgentConfig.agent_definition_id == existing_template.id,
                )
            )
            if existing_instance is None:
                existing_instance = TenantAgentConfig(
                    tenant_id=tenant_id,
                    agent_definition_id=existing_template.id,
                    is_enabled=True,
                    config=tenant_config,
                    custom_templates={},
                    custom_constraints={},
                    approval_config={},
                    notification_channels={},
                    created_by="seed_agent_templates",
                )
                session.add(existing_instance)
            else:
                existing_instance.config = tenant_config
                existing_instance.is_enabled = True
                existing_instance.created_by = "seed_agent_templates"
            created_or_updated_instances += 1

        session.commit()

    return created_or_updated_templates, created_or_updated_instances


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed default registry-driven agent templates.")
    parser.add_argument(
        "--tenant-id",
        required=True,
        help="Target tenant UUID for upserting tenant agent instances.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tenant_id = uuid.UUID(str(args.tenant_id))
    templates, instances = upsert_template_and_instance(tenant_id)
    print(
        f"Seed complete for tenant {tenant_id}: "
        f"{templates} templates upserted, {instances} tenant instances upserted."
    )


if __name__ == "__main__":
    main()
