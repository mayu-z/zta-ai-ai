from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import select

from app.agentic.db_models import AgenticActionConfigModel
from app.agentic.models.action_config import ActionConfig
from app.core.redis_client import redis_client
from app.db.session import SessionLocal


def _cache_key(tenant_id: UUID, action_id: str) -> str:
    return f"agentic:action:{tenant_id}:{action_id}"


def _default_actions(tenant_id: UUID) -> list[ActionConfig]:
    return [
        ActionConfig(
            action_id="result_notification_v1",
            tenant_id=tenant_id,
            display_name="Result Notification Agent",
            description="Event-driven result summary notifications",
            trigger_type="event",
            required_data_scope=["results.own", "attendance.own"],
            output_type="notification",
            requires_confirmation=False,
            allowed_personas=["student"],
            cache_results=False,
            extra_config={"kind": "result_notification"},
        ),
        ActionConfig(
            action_id="fee_reminder_v1",
            tenant_id=tenant_id,
            display_name="Fee Reminder Agent",
            description="Scheduled fee reminders",
            trigger_type="scheduled",
            required_data_scope=["fees.own"],
            output_type="notification",
            requires_confirmation=False,
            allowed_personas=["student", "staff"],
            extra_config={"kind": "fee_reminder"},
        ),
        ActionConfig(
            action_id="upi_payment_link_v1",
            tenant_id=tenant_id,
            display_name="UPI Payment Agent",
            description="Generate payment link only",
            trigger_type="user_query",
            required_data_scope=["fees.own"],
            output_type="link",
            requires_confirmation=False,
            allowed_personas=["student", "staff", "faculty"],
            financial_transaction=False,
            cache_results=False,
            extra_config={"kind": "upi_payment"},
        ),
        ActionConfig(
            action_id="refund_request_v1",
            tenant_id=tenant_id,
            display_name="Refund Agent",
            description="Refund request workflow",
            trigger_type="user_query",
            required_data_scope=["fees.own", "refund_policy.read"],
            output_type="workflow",
            write_target="refund_requests:INSERT",
            requires_confirmation=True,
            human_approval_required=True,
            approval_level="finance_officer",
            allowed_personas=["student", "staff", "faculty"],
            extra_config={"kind": "refund"},
        ),
        ActionConfig(
            action_id="email_draft_v1",
            tenant_id=tenant_id,
            display_name="Email Draft Agent",
            description="Draft email without sending",
            trigger_type="user_query",
            required_data_scope=["user_profile.own"],
            output_type="response",
            requires_confirmation=False,
            allowed_personas=["student", "staff", "faculty"],
            extra_config={"kind": "email_draft"},
        ),
        ActionConfig(
            action_id="email_send_v1",
            tenant_id=tenant_id,
            display_name="Email Send Agent",
            description="Draft and send email with confirmation",
            trigger_type="user_query",
            required_data_scope=["user_profile.own"],
            output_type="email",
            requires_confirmation=True,
            allowed_personas=["student", "staff", "faculty"],
            extra_config={"kind": "email_send"},
        ),
        ActionConfig(
            action_id="bulk_notification_v1",
            tenant_id=tenant_id,
            display_name="Bulk Notification Agent",
            description="Admin bulk notifications",
            trigger_type="admin_initiated",
            required_data_scope=["user_directory.department_scope"],
            output_type="bulk_notification",
            requires_confirmation=True,
            allowed_personas=["registrar", "dept_head", "admin", "finance_officer"],
            extra_config={"kind": "bulk_notification"},
        ),
        ActionConfig(
            action_id="leave_approval_v1",
            tenant_id=tenant_id,
            display_name="Leave Approval Agent",
            description="Leave approval workflow",
            trigger_type="user_query",
            required_data_scope=["hr.own", "timetable.own", "org_hierarchy.read"],
            output_type="workflow",
            write_target="leave_records:INSERT,leave_balance:UPDATE",
            requires_confirmation=True,
            human_approval_required=True,
            approval_level="org_hierarchy_configured",
            allowed_personas=["student", "faculty", "staff"],
            extra_config={"kind": "leave_approval"},
        ),
        ActionConfig(
            action_id="meeting_scheduler_v1",
            tenant_id=tenant_id,
            display_name="Meeting Scheduler Agent",
            description="Find free/busy slots and schedule meetings",
            trigger_type="user_query",
            required_data_scope=["calendar.own.free_busy", "calendar.participants.free_busy"],
            output_type="calendar_invite",
            requires_confirmation=True,
            allowed_personas=["faculty", "staff", "dept_head", "admin"],
            extra_config={"kind": "meeting_scheduler"},
        ),
        ActionConfig(
            action_id="payroll_query_v1",
            tenant_id=tenant_id,
            display_name="Payroll Query Agent",
            description="Read-only payroll explanation",
            trigger_type="user_query",
            required_data_scope=["payroll.own"],
            output_type="response",
            has_sensitive_fields=True,
            cache_results=False,
            requires_confirmation=False,
            allowed_personas=["faculty", "staff"],
            extra_config={"kind": "payroll_query"},
        ),
        ActionConfig(
            action_id="leave_balance_check_v1",
            tenant_id=tenant_id,
            display_name="Leave Balance Check",
            description="Read-only leave balance",
            trigger_type="user_query",
            required_data_scope=["hr.own"],
            output_type="response",
            requires_confirmation=False,
            allowed_personas=["student", "faculty", "staff"],
            extra_config={"kind": "leave_balance_check"},
        ),
        ActionConfig(
            action_id="leave_balance_apply_v1",
            tenant_id=tenant_id,
            display_name="Leave Balance Apply",
            description="Self-apply leave for allowed types",
            trigger_type="user_query",
            required_data_scope=["hr.own", "timetable.own"],
            output_type="workflow",
            write_target="leave_records:INSERT,leave_balance:UPDATE",
            requires_confirmation=True,
            allowed_personas=["faculty", "staff"],
            extra_config={"kind": "leave_balance_apply"},
        ),
    ]


class ActionRegistry:
    def __init__(self, cache_ttl_seconds: int = 120) -> None:
        self._cache_ttl_seconds = cache_ttl_seconds

    async def seed_defaults(self, tenant_id: UUID) -> None:
        for cfg in _default_actions(tenant_id):
            await self.upsert(cfg)

    async def get(self, action_id: str | None, tenant_id: UUID) -> ActionConfig | None:
        if not action_id:
            return None

        key = _cache_key(tenant_id, action_id)
        cached = redis_client.client.get(key)
        if cached:
            return ActionConfig.model_validate_json(cached)

        db = SessionLocal()
        try:
            row = db.scalar(
                select(AgenticActionConfigModel)
                .where(AgenticActionConfigModel.tenant_id == str(tenant_id))
                .where(AgenticActionConfigModel.action_id == action_id)
                .where(AgenticActionConfigModel.is_enabled.is_(True))
            )
            if row is None:
                return None

            payload = {
                "action_id": row.action_id,
                "tenant_id": row.tenant_id,
                "display_name": row.display_name,
                "description": row.description,
                "trigger_type": row.trigger_type,
                "required_data_scope": row.required_data_scope,
                "output_type": row.output_type,
                "write_target": row.write_target,
                "requires_confirmation": row.requires_confirmation,
                "human_approval_required": row.human_approval_required,
                "approval_level": row.approval_level,
                "allowed_personas": row.allowed_personas,
                "financial_transaction": row.financial_transaction,
                "has_sensitive_fields": row.has_sensitive_fields,
                "cache_results": row.cache_results,
                "rate_limit": row.rate_limit,
                "notification_config": row.notification_config,
                "extra_config": row.extra_config,
                "is_enabled": row.is_enabled,
                "version": row.version,
            }
            config = ActionConfig.model_validate(payload)
            redis_client.client.setex(key, self._cache_ttl_seconds, config.model_dump_json())
            return config
        finally:
            db.close()

    async def list_actions(self, tenant_id: UUID) -> list[ActionConfig]:
        db = SessionLocal()
        try:
            rows = db.scalars(
                select(AgenticActionConfigModel)
                .where(AgenticActionConfigModel.tenant_id == str(tenant_id))
                .order_by(AgenticActionConfigModel.action_id.asc())
            ).all()
            items: list[ActionConfig] = []
            for row in rows:
                items.append(
                    ActionConfig.model_validate(
                        {
                            "action_id": row.action_id,
                            "tenant_id": row.tenant_id,
                            "display_name": row.display_name,
                            "description": row.description,
                            "trigger_type": row.trigger_type,
                            "required_data_scope": row.required_data_scope,
                            "output_type": row.output_type,
                            "write_target": row.write_target,
                            "requires_confirmation": row.requires_confirmation,
                            "human_approval_required": row.human_approval_required,
                            "approval_level": row.approval_level,
                            "allowed_personas": row.allowed_personas,
                            "financial_transaction": row.financial_transaction,
                            "has_sensitive_fields": row.has_sensitive_fields,
                            "cache_results": row.cache_results,
                            "rate_limit": row.rate_limit,
                            "notification_config": row.notification_config,
                            "extra_config": row.extra_config,
                            "is_enabled": row.is_enabled,
                            "version": row.version,
                        }
                    )
                )
            return items
        finally:
            db.close()

    async def upsert(self, config: ActionConfig) -> ActionConfig:
        db = SessionLocal()
        try:
            row = db.scalar(
                select(AgenticActionConfigModel)
                .where(AgenticActionConfigModel.tenant_id == str(config.tenant_id))
                .where(AgenticActionConfigModel.action_id == config.action_id)
            )
            if row is None:
                row = AgenticActionConfigModel(
                    action_id=config.action_id,
                    tenant_id=str(config.tenant_id),
                    display_name=config.display_name,
                    description=config.description,
                    trigger_type=config.trigger_type,
                    required_data_scope=list(config.required_data_scope),
                    output_type=config.output_type,
                    write_target=config.write_target,
                    requires_confirmation=config.requires_confirmation,
                    human_approval_required=config.human_approval_required,
                    approval_level=config.approval_level,
                    allowed_personas=list(config.allowed_personas),
                    financial_transaction=config.financial_transaction,
                    has_sensitive_fields=config.has_sensitive_fields,
                    cache_results=config.cache_results,
                    rate_limit=(config.rate_limit.model_dump() if config.rate_limit else None),
                    notification_config=(
                        config.notification_config.model_dump() if config.notification_config else None
                    ),
                    extra_config=dict(config.extra_config),
                    is_enabled=config.is_enabled,
                    version=config.version,
                )
                db.add(row)
            else:
                row.display_name = config.display_name
                row.description = config.description
                row.trigger_type = config.trigger_type
                row.required_data_scope = list(config.required_data_scope)
                row.output_type = config.output_type
                row.write_target = config.write_target
                row.requires_confirmation = config.requires_confirmation
                row.human_approval_required = config.human_approval_required
                row.approval_level = config.approval_level
                row.allowed_personas = list(config.allowed_personas)
                row.financial_transaction = config.financial_transaction
                row.has_sensitive_fields = config.has_sensitive_fields
                row.cache_results = config.cache_results
                row.rate_limit = config.rate_limit.model_dump() if config.rate_limit else None
                row.notification_config = (
                    config.notification_config.model_dump() if config.notification_config else None
                )
                row.extra_config = dict(config.extra_config)
                row.is_enabled = config.is_enabled
                row.version = config.version

            db.commit()
            redis_client.client.setex(
                _cache_key(config.tenant_id, config.action_id),
                self._cache_ttl_seconds,
                config.model_dump_json(),
            )
            return config
        finally:
            db.close()
