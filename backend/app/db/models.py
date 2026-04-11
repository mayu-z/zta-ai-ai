from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


class PlanTier(str, enum.Enum):
    starter = "starter"
    growth = "growth"
    enterprise = "enterprise"


class TenantStatus(str, enum.Enum):
    active = "active"
    paused = "paused"
    suspended = "suspended"


class PersonaType(str, enum.Enum):
    student = "student"
    faculty = "faculty"
    dept_head = "dept_head"
    admin_staff = "admin_staff"
    executive = "executive"
    it_head = "it_head"


class UserStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"


class DataSourceType(str, enum.Enum):
    erpnext = "erpnext"
    google_sheets = "google_sheets"
    google_drive = "google_drive"
    mysql = "mysql"
    postgresql = "postgresql"
    ipeds_claims = "ipeds_claims"
    mock_claims = "mock_claims"


class DataSourceStatus(str, enum.Enum):
    connected = "connected"
    disconnected = "disconnected"
    error = "error"
    paused = "paused"


class FieldVisibility(str, enum.Enum):
    visible = "visible"
    masked = "masked"
    hidden = "hidden"


class ClaimSensitivity(str, enum.Enum):
    low = "low"
    internal = "internal"
    confidential = "confidential"
    restricted = "restricted"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    subdomain: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    plan_tier: Mapped[PlanTier] = mapped_column(
        Enum(PlanTier), nullable=False, default=PlanTier.starter
    )
    status: Mapped[TenantStatus] = mapped_column(
        Enum(TenantStatus), nullable=False, default=TenantStatus.active
    )
    google_workspace_domain: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )

    users: Mapped[list["User"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    intent_detection_keywords: Mapped[list["IntentDetectionKeyword"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    persona_type: Mapped[PersonaType] = mapped_column(Enum(PersonaType), nullable=False)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    admin_function: Mapped[str | None] = mapped_column(String(100), nullable=True)
    course_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    masked_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mfa_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    mfa_totp_secret: Mapped[str | None] = mapped_column(String(128), nullable=True)
    mfa_enrolled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus), nullable=False, default=UserStatus.active
    )
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )

    tenant: Mapped[Tenant] = relationship(back_populates="users")


Index("ix_users_tenant_email", User.tenant_id, User.email, unique=False)


class RolePolicy(Base):
    __tablename__ = "role_policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False
    )
    role_key: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    allowed_domains: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    masked_fields: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    aggregate_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    chat_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    row_scope_mode: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sensitive_domains: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=lambda: ["finance", "hr"]
    )
    require_business_hours_for_sensitive: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    business_hours_start: Mapped[int] = mapped_column(Integer, nullable=False, default=9)
    business_hours_end: Mapped[int] = mapped_column(Integer, nullable=False, default=19)
    require_trusted_device_for_sensitive: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    require_mfa_for_sensitive: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )


Index(
    "ix_role_policies_tenant_role",
    RolePolicy.tenant_id,
    RolePolicy.role_key,
    unique=True,
)


class DomainKeyword(Base):
    __tablename__ = "domain_keywords"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False
    )
    domain: Mapped[str] = mapped_column(String(50), nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )


Index(
    "ix_domain_keywords_tenant_domain",
    DomainKeyword.tenant_id,
    DomainKeyword.domain,
    unique=True,
)


class IntentDefinition(Base):
    __tablename__ = "intent_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False
    )
    intent_name: Mapped[str] = mapped_column(String(120), nullable=False)
    domain: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    slot_keys: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    persona_types: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    requires_aggregation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )


Index(
    "ix_intent_definitions_tenant_intent",
    IntentDefinition.tenant_id,
    IntentDefinition.intent_name,
    unique=True,
)
Index(
    "ix_intent_definitions_tenant_domain",
    IntentDefinition.tenant_id,
    IntentDefinition.domain,
    unique=False,
)


class DomainSourceBinding(Base):
    __tablename__ = "domain_source_bindings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False
    )
    domain: Mapped[str] = mapped_column(String(50), nullable=False)
    source_type: Mapped[DataSourceType] = mapped_column(
        Enum(DataSourceType), nullable=False
    )
    data_source_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("data_sources.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )


Index(
    "ix_domain_source_bindings_tenant_domain",
    DomainSourceBinding.tenant_id,
    DomainSourceBinding.domain,
    unique=True,
)


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[DataSourceType] = mapped_column(
        Enum(DataSourceType), nullable=False
    )
    config_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    department_scope: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    status: Mapped[DataSourceStatus] = mapped_column(
        Enum(DataSourceStatus), nullable=False, default=DataSourceStatus.connected
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sync_error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )


class SchemaField(Base):
    __tablename__ = "schema_fields"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    data_source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("data_sources.id"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False
    )
    real_table: Mapped[str] = mapped_column(String(255), nullable=False)
    real_column: Mapped[str] = mapped_column(String(255), nullable=False)
    alias_token: Mapped[str] = mapped_column(String(50), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    data_type: Mapped[str] = mapped_column(String(50), nullable=False)
    visibility: Mapped[FieldVisibility] = mapped_column(
        Enum(FieldVisibility), nullable=False, default=FieldVisibility.visible
    )
    pii_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    masked_for_personas: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )


Index(
    "ix_schema_fields_tenant_alias",
    SchemaField.tenant_id,
    SchemaField.alias_token,
    unique=False,
)


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False
    )
    domain: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    course_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    admin_function: Mapped[str | None] = mapped_column(String(100), nullable=True)
    claim_key: Mapped[str] = mapped_column(String(100), nullable=False)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_number: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    provenance: Mapped[str] = mapped_column(
        String(255), nullable=False, default="mock-source"
    )
    sensitivity: Mapped[ClaimSensitivity] = mapped_column(
        Enum(ClaimSensitivity), nullable=False, default=ClaimSensitivity.internal
    )
    compliance_tags: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )


Index(
    "ix_claims_tenant_domain_entity",
    Claim.tenant_id,
    Claim.domain,
    Claim.entity_type,
    unique=False,
)
Index("ix_claims_owner_course", Claim.owner_id, Claim.course_id, unique=False)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    intent_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    domains_accessed: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    was_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    block_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    response_summary: Mapped[str] = mapped_column(Text, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_flag: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )


class ControlGraphNode(Base):
    __tablename__ = "control_graph_nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False
    )
    node_type: Mapped[str] = mapped_column(String(80), nullable=False)
    node_key: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    attributes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )


Index(
    "ix_control_graph_nodes_tenant_type_key",
    ControlGraphNode.tenant_id,
    ControlGraphNode.node_type,
    ControlGraphNode.node_key,
    unique=True,
)
Index(
    "ix_control_graph_nodes_tenant_type",
    ControlGraphNode.tenant_id,
    ControlGraphNode.node_type,
    unique=False,
)


class ControlGraphEdge(Base):
    __tablename__ = "control_graph_edges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False
    )
    edge_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("control_graph_nodes.id"), nullable=False
    )
    target_node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("control_graph_nodes.id"), nullable=False
    )
    attributes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )


Index(
    "ix_control_graph_edges_tenant_type_pair",
    ControlGraphEdge.tenant_id,
    ControlGraphEdge.edge_type,
    ControlGraphEdge.source_node_id,
    ControlGraphEdge.target_node_id,
    unique=True,
)
Index(
    "ix_control_graph_edges_tenant_source",
    ControlGraphEdge.tenant_id,
    ControlGraphEdge.source_node_id,
    unique=False,
)
Index(
    "ix_control_graph_edges_tenant_target",
    ControlGraphEdge.tenant_id,
    ControlGraphEdge.target_node_id,
    unique=False,
)


class PolicyProofArtifact(Base):
    __tablename__ = "policy_proofs"

    proof_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    proof_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    pipeline_id: Mapped[str] = mapped_column(String(36), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    intent_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    domain: Mapped[str] = mapped_column(String(50), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_binding_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    data_source_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    compiled_signature: Mapped[str] = mapped_column(Text, nullable=False)
    scope_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    policy_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    masked_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    reasoning: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )


Index(
    "ix_policy_proofs_tenant_created",
    PolicyProofArtifact.tenant_id,
    PolicyProofArtifact.created_at,
    unique=False,
)
Index(
    "ix_policy_proofs_tenant_session",
    PolicyProofArtifact.tenant_id,
    PolicyProofArtifact.session_id,
    unique=False,
)
Index(
    "ix_policy_proofs_tenant_intent",
    PolicyProofArtifact.tenant_id,
    PolicyProofArtifact.intent_hash,
    unique=False,
)


class ActionExecution(Base):
    __tablename__ = "action_executions"

    execution_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    action_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    input_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    requested_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )
    approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approver_role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approval_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    escalation_target: Mapped[str | None] = mapped_column(String(100), nullable=True)
    output: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    steps: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    audit_events: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )


Index(
    "ix_action_executions_tenant_requested_at",
    ActionExecution.tenant_id,
    ActionExecution.requested_at,
    unique=False,
)
Index(
    "ix_action_executions_tenant_status",
    ActionExecution.tenant_id,
    ActionExecution.status,
    unique=False,
)
Index(
    "ix_action_executions_tenant_action",
    ActionExecution.tenant_id,
    ActionExecution.action_id,
    unique=False,
)


class ActionTemplateOverride(Base):
    __tablename__ = "action_template_overrides"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False
    )
    action_id: Mapped[str] = mapped_column(String(64), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    trigger_override: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approval_required_override: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )
    approver_role_override: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sla_hours_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    execution_steps_override: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True
    )
    updated_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )


Index(
    "ix_action_template_overrides_tenant_action",
    ActionTemplateOverride.tenant_id,
    ActionTemplateOverride.action_id,
    unique=True,
)


class ComplianceCase(Base):
    __tablename__ = "compliance_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False
    )
    case_type: Mapped[str] = mapped_column(String(40), nullable=False)
    subject_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    action_execution_id: Mapped[str] = mapped_column(String(36), nullable=False)
    requested_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    sla_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )
    delivery_method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    legal_basis: Mapped[str | None] = mapped_column(String(120), nullable=True)
    legal_hold_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    legal_hold_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_action_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    output: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    case_events: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )


Index(
    "ix_compliance_cases_tenant_requested_at",
    ComplianceCase.tenant_id,
    ComplianceCase.requested_at,
    unique=False,
)
Index(
    "ix_compliance_cases_tenant_case_type_status",
    ComplianceCase.tenant_id,
    ComplianceCase.case_type,
    ComplianceCase.status,
    unique=False,
)
Index(
    "ix_compliance_cases_tenant_execution",
    ComplianceCase.tenant_id,
    ComplianceCase.action_execution_id,
    unique=True,
)


class ComplianceAttestation(Base):
    __tablename__ = "compliance_attestations"

    attestation_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False
    )
    framework: Mapped[str] = mapped_column(String(40), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    requested_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_algorithm: Mapped[str] = mapped_column(
        String(32), nullable=False, default="HMAC-SHA256"
    )
    signature: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )


Index(
    "ix_compliance_attestations_tenant_framework_created_at",
    ComplianceAttestation.tenant_id,
    ComplianceAttestation.framework,
    ComplianceAttestation.created_at,
    unique=False,
)
Index(
    "ix_compliance_attestations_tenant_period",
    ComplianceAttestation.tenant_id,
    ComplianceAttestation.period_start,
    ComplianceAttestation.period_end,
    unique=False,
)


class IntentDetectionKeyword(Base):
    __tablename__ = "intent_detection_keywords"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    intent_name: Mapped[str] = mapped_column(String(120), nullable=False)
    keyword_type: Mapped[str] = mapped_column(String(50), nullable=False)
    keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )

    tenant: Mapped[Tenant] = relationship(back_populates="intent_detection_keywords")


Index(
    "ix_intent_detection_keywords_tenant_intent_type",
    IntentDetectionKeyword.tenant_id,
    IntentDetectionKeyword.intent_name,
    IntentDetectionKeyword.keyword_type,
    unique=False,
)
Index(
    "ix_intent_detection_keywords_tenant_keyword",
    IntentDetectionKeyword.tenant_id,
    IntentDetectionKeyword.intent_name,
    IntentDetectionKeyword.keyword,
    IntentDetectionKeyword.keyword_type,
    unique=True,
)


class IntentCacheEntry(Base):
    __tablename__ = "intent_cache"

    intent_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False
    )
    normalized_intent: Mapped[dict] = mapped_column(JSON, nullable=False)
    response_template: Mapped[str] = mapped_column(Text, nullable=False)
    compiled_query: Mapped[dict] = mapped_column(JSON, nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )


Index(
    "ix_intent_cache_tenant_hash",
    IntentCacheEntry.tenant_id,
    IntentCacheEntry.intent_hash,
    unique=False,
)


def _raise_append_only(*_: object, **__: object) -> None:
    raise ValueError("audit_log is append-only and cannot be modified")


event.listen(AuditLog, "before_update", _raise_append_only)
event.listen(AuditLog, "before_delete", _raise_append_only)
