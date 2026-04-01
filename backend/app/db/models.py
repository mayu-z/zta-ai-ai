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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
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
