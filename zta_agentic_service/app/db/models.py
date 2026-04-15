import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    ARRAY,
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.enums import (
    AgentDefinitionStatus,
    ExecutionState,
    ExecutionStatus,
    PluginStatus,
    PublishAction,
    PublishStatus,
    StepAttemptStatus,
    TriggerType,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class AgentDefinition(Base, TimestampMixin):
    __tablename__ = "agent_definitions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    domain: Mapped[str] = mapped_column(String(80), nullable=False)
    trigger_type: Mapped[TriggerType] = mapped_column(Enum(TriggerType), nullable=False)
    trigger_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    input_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    output_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    action_steps: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    rbac_permissions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    constraints: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmation_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    chain_to: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    allowed_output_channels: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    is_sensitive_monitor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[AgentDefinitionStatus] = mapped_column(
        Enum(AgentDefinitionStatus), nullable=False, default=AgentDefinitionStatus.BETA
    )
    risk_rank: Mapped[int] = mapped_column(Integer, nullable=False, default=50)

    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_agent_name_version"),
        CheckConstraint("risk_rank >= 0 AND risk_rank <= 100", name="ck_agent_risk_rank_range"),
    )


class TenantAgentConfig(Base, TimestampMixin):
    __tablename__ = "tenant_agent_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    agent_definition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_definitions.id", ondelete="RESTRICT"), nullable=False
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    custom_templates: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    custom_constraints: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    approval_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    notification_channels: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    active_definition_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_definition_versions.id", ondelete="SET NULL")
    )
    active_config_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant_agent_config_versions.id", ondelete="SET NULL")
    )
    edit_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("tenant_id", "agent_definition_id", name="uq_tenant_agent_config"),
        Index("ix_tenant_agent_enabled", "tenant_id", "is_enabled"),
    )


class AgentExecution(Base):
    __tablename__ = "agent_executions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_definition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_definitions.id", ondelete="RESTRICT"), nullable=False
    )
    definition_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_definition_versions.id", ondelete="SET NULL")
    )
    config_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant_agent_config_versions.id", ondelete="SET NULL")
    )
    trigger_type: Mapped[TriggerType] = mapped_column(Enum(TriggerType), nullable=False)
    trigger_source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_executions.id", ondelete="SET NULL")
    )
    input_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    intent_matched: Mapped[str | None] = mapped_column(String(120), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    steps_executed: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    confirmation_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmation_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmation_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    output_summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ExecutionStatus] = mapped_column(Enum(ExecutionStatus), nullable=False)
    current_state: Mapped[ExecutionState] = mapped_column(
        Enum(ExecutionState), nullable=False, default=ExecutionState.INIT
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    trace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    chain_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chain_path: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    current_step_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    resume_token: Mapped[str | None] = mapped_column(String(120))
    resume_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_execution_tenant_status_created", "tenant_id", "status", "created_at"),
        Index("ix_execution_waiting_state", "tenant_id", "current_state"),
        CheckConstraint("chain_depth >= 0 AND chain_depth <= 3", name="ck_chain_depth_max3"),
    )


class AgentTriggerRule(Base):
    __tablename__ = "agent_trigger_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    agent_definition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_definitions.id", ondelete="RESTRICT"), nullable=False
    )
    trigger_type: Mapped[TriggerType] = mapped_column(Enum(TriggerType), nullable=False)
    schedule_cron: Mapped[str | None] = mapped_column(String(100))
    event_source: Mapped[str | None] = mapped_column(String(120))
    event_condition: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    target_persona_filter: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    max_notifications_per_user_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        Index(
            "ix_trigger_tenant_type_enabled_lastfired",
            "tenant_id",
            "trigger_type",
            "is_enabled",
            "last_fired_at",
        ),
    )


class AgentTemplate(Base, TimestampMixin):
    __tablename__ = "agent_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    agent_definition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_definitions.id", ondelete="RESTRICT"), nullable=False
    )
    template_type: Mapped[str] = mapped_column(String(80), nullable=False)
    subject_template: Mapped[str | None] = mapped_column(Text)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)
    available_variables: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "agent_definition_id",
            "template_type",
            "language",
            "version",
            name="uq_tenant_agent_template_version",
        ),
    )


class AgentDefinitionVersion(Base):
    __tablename__ = "agent_definition_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_definition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_definitions.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    schema_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[PublishStatus] = mapped_column(
        Enum(PublishStatus), nullable=False, default=PublishStatus.DRAFT
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "agent_definition_id", "version_number", name="uq_agent_definition_version_number"
        ),
    )


class TenantAgentConfigVersion(Base):
    __tablename__ = "tenant_agent_config_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_agent_config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant_agent_configs.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    schema_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[PublishStatus] = mapped_column(
        Enum(PublishStatus), nullable=False, default=PublishStatus.DRAFT
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "tenant_agent_config_id",
            "version_number",
            name="uq_tenant_agent_config_version_number",
        ),
    )


class RegistryPublishEvent(Base):
    __tablename__ = "registry_publish_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    agent_definition_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_definitions.id", ondelete="SET NULL")
    )
    definition_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_definition_versions.id", ondelete="SET NULL")
    )
    config_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant_agent_config_versions.id", ondelete="SET NULL")
    )
    action: Mapped[PublishAction] = mapped_column(Enum(PublishAction), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    notes: Mapped[str | None] = mapped_column(Text)
    event_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class ExecutionStateTransition(Base):
    __tablename__ = "execution_state_transitions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_executions.id", ondelete="CASCADE"), nullable=False
    )
    from_state: Mapped[ExecutionState] = mapped_column(Enum(ExecutionState), nullable=False)
    to_state: Mapped[ExecutionState] = mapped_column(Enum(ExecutionState), nullable=False)
    reason: Mapped[str] = mapped_column(String(120), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class StepAttempt(Base):
    __tablename__ = "step_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_executions.id", ondelete="CASCADE"), nullable=False
    )
    step_id: Mapped[str] = mapped_column(String(120), nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[StepAttemptStatus] = mapped_column(Enum(StepAttemptStatus), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    error_class: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    result_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "execution_id", "step_id", "attempt_no", name="uq_execution_step_attempt_no"
        ),
    )


class DeadLetterEvent(Base):
    __tablename__ = "dead_letter_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_executions.id", ondelete="CASCADE"), nullable=False
    )
    step_id: Mapped[str | None] = mapped_column(String(120))
    error_class: Mapped[str] = mapped_column(String(100), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    replayable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class PluginRegistration(Base, TimestampMixin):
    __tablename__ = "plugin_registrations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plugin_id: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    capabilities: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    supported_step_types: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    min_engine_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[PluginStatus] = mapped_column(Enum(PluginStatus), nullable=False)
    health_last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("plugin_id", "version", name="uq_plugin_id_version"),
    )
