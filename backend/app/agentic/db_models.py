from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


class AgenticActionConfigModel(Base):
    __tablename__ = "agentic_action_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    action_id: Mapped[str] = mapped_column(String(120), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    trigger_type: Mapped[str] = mapped_column(String(30), nullable=False)
    required_data_scope: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    output_type: Mapped[str] = mapped_column(String(50), nullable=False)
    write_target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    human_approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approval_level: Mapped[str] = mapped_column(String(50), nullable=False, default="self")
    allowed_personas: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    financial_transaction: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_sensitive_fields: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cache_results: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    rate_limit: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notification_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    extra_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )


Index(
    "ix_agentic_action_cfg_tenant_action",
    AgenticActionConfigModel.tenant_id,
    AgenticActionConfigModel.action_id,
    unique=True,
)


class AgenticAuditEventModel(Base):
    __tablename__ = "agentic_audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_alias: Mapped[str] = mapped_column(String(120), nullable=False)
    action_id: Mapped[str] = mapped_column(String(120), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    payload_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    data_accessed: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    event_metadata: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)


Index("ix_agentic_audit_tenant_created", AgenticAuditEventModel.tenant_id, AgenticAuditEventModel.created_at)


class AgenticWorkflowStateModel(Base):
    __tablename__ = "agentic_workflow_states"

    workflow_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_type: Mapped[str] = mapped_column(String(80), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    initiator_alias: Mapped[str] = mapped_column(String(120), nullable=False)
    current_step: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    steps: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    workflow_metadata: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )


Index("ix_agentic_workflows_tenant", AgenticWorkflowStateModel.tenant_id, AgenticWorkflowStateModel.status)


class AgenticSensitiveAlertModel(Base):
    __tablename__ = "agentic_sensitive_alerts"

    alert_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_alias: Mapped[str] = mapped_column(String(120), nullable=False)
    session_id: Mapped[str] = mapped_column(String(120), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    patterns: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")
    alert_metadata: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)


Index("ix_agentic_alerts_tenant_created", AgenticSensitiveAlertModel.tenant_id, AgenticSensitiveAlertModel.created_at)
