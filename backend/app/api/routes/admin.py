from __future__ import annotations

import base64
import csv
import io
import json
import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_scope
from app.connectors.registry import connector_registry
from app.core.exceptions import AuthorizationError, ValidationError, ZTAError
from app.core.redis_client import redis_client
from app.db.models import (
    AuditLog,
    DataSource,
    DomainSourceBinding,
    DataSourceStatus,
    DataSourceType,
    DomainKeyword,
    IntentDefinition,
    IntentDetectionKeyword,
    IntentCacheEntry,
    FieldVisibility,
    PersonaType,
    RolePolicy,
    SchemaField,
    User,
    UserStatus,
)
from app.interpreter.onboarding_validator import validate_interpreter_onboarding
from app.db.session import get_db
from app.schemas.admin import (
    ActionApprovalRequest,
    ActionExecuteRequest,
    ActionRollbackRequest,
    ActionTemplateOverrideUpsertRequest,
    ComplianceAttestationCreateRequest,
    ComplianceCaseCreateRequest,
    ComplianceCaseLegalHoldRequest,
    ComplianceForensicExportRequest,
    ComplianceRetentionRunRequest,
    DataSourceCreateRequest,
    DataSourceUpdateRequest,
    FieldMaskingPolicyUpdateRequest,
    DomainSourceBindingUpsertRequest,
    DomainKeywordUpsertRequest,
    IntentDefinitionUpsertRequest,
    IntentDetectionKeywordUpsertRequest,
    KillSwitchRequest,
    RowLevelPolicyUpdateRequest,
    RolePolicyUpsertRequest,
    UserUpdateRequest,
)
from app.schemas.pipeline import CompiledQueryPlan, ScopeContext
from app.services.action_orchestrator import action_orchestrator_service
from app.services.action_registry import action_registry_health
from app.services.action_template_override_service import (
    action_template_override_service,
)
from app.services.audit_dashboard_service import audit_dashboard_service
from app.services.compliance_case_service import compliance_case_service
from app.services.compliance_attestation_service import compliance_attestation_service
from app.services.compliance_operations import compliance_operations_service
from app.services.compliance_retention_service import compliance_retention_service
from app.services.system_admin_service import system_admin_service

router = APIRouter(prefix="/admin", tags=["admin"])

VALID_ROW_SCOPE_MODES = {None, "owner_id", "course_ids", "department_id", "admin_function"}
PERSONA_ROLE_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "dept_head": ("hod",),
    "it_head": ("it_admin",),
}


def require_it_head(scope: ScopeContext = Depends(get_current_scope)) -> ScopeContext:
    if scope.persona_type != "it_head":
        raise AuthorizationError(
            message="Only IT Head can access admin endpoints", code="ADMIN_ONLY"
        )
    return scope


def _serialize_role_policy(policy: RolePolicy) -> dict[str, object]:
    return {
        "id": policy.id,
        "role_key": policy.role_key,
        "display_name": policy.display_name,
        "description": policy.description,
        "allowed_domains": list(policy.allowed_domains or []),
        "masked_fields": list(policy.masked_fields or []),
        "aggregate_only": policy.aggregate_only,
        "chat_enabled": policy.chat_enabled,
        "row_scope_mode": policy.row_scope_mode,
        "sensitive_domains": list(policy.sensitive_domains or []),
        "require_business_hours_for_sensitive": policy.require_business_hours_for_sensitive,
        "business_hours_start": policy.business_hours_start,
        "business_hours_end": policy.business_hours_end,
        "require_trusted_device_for_sensitive": policy.require_trusted_device_for_sensitive,
        "require_mfa_for_sensitive": policy.require_mfa_for_sensitive,
        "is_active": policy.is_active,
        "created_at": policy.created_at,
        "updated_at": policy.updated_at,
    }


def _normalize_text_list(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for item in values:
        value = str(item).strip().lower()
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def _normalize_persona_values(values: list[str]) -> list[str]:
    normalized = _normalize_text_list(values)
    allowed = {persona.value for persona in PersonaType}
    invalid = [value for value in normalized if value not in allowed]
    if invalid:
        raise ValidationError(
            message=f"Unsupported persona values: {', '.join(invalid)}",
            code="INVALID_PERSONA_TYPE",
        )
    return normalized


def _find_role_policies_for_persona(
    *,
    db: Session,
    tenant_id: str,
    persona: str,
) -> list[RolePolicy]:
    conditions = [RolePolicy.role_key == persona]
    if persona == "admin_staff":
        conditions.append(RolePolicy.role_key.like("admin_staff:%"))

    for alias in PERSONA_ROLE_KEY_ALIASES.get(persona, tuple()):
        conditions.append(RolePolicy.role_key == alias)

    return db.scalars(
        select(RolePolicy).where(
            RolePolicy.tenant_id == tenant_id,
            or_(*conditions),
        )
    ).all()


def _sync_role_policy_masked_fields_for_schema_field(
    *,
    db: Session,
    tenant_id: str,
    alias_token: str,
    previous_personas: set[str],
    current_personas: set[str],
) -> dict[str, list[str]]:
    added_roles: set[str] = set()
    removed_roles: set[str] = set()

    personas_to_add = sorted(current_personas - previous_personas)
    personas_to_remove = sorted(previous_personas - current_personas)

    for persona in personas_to_add:
        for role_policy in _find_role_policies_for_persona(
            db=db,
            tenant_id=tenant_id,
            persona=persona,
        ):
            masked_fields = set(role_policy.masked_fields or [])
            if alias_token in masked_fields:
                continue
            masked_fields.add(alias_token)
            role_policy.masked_fields = sorted(masked_fields)
            db.add(role_policy)
            added_roles.add(role_policy.role_key)

    for persona in personas_to_remove:
        for role_policy in _find_role_policies_for_persona(
            db=db,
            tenant_id=tenant_id,
            persona=persona,
        ):
            masked_fields = set(role_policy.masked_fields or [])
            if alias_token not in masked_fields:
                continue
            masked_fields.remove(alias_token)
            role_policy.masked_fields = sorted(masked_fields)
            db.add(role_policy)
            removed_roles.add(role_policy.role_key)

    return {
        "added_to_role_policies": sorted(added_roles),
        "removed_from_role_policies": sorted(removed_roles),
    }


def _serialize_domain_keyword(row: DomainKeyword) -> dict[str, object]:
    return {
        "id": row.id,
        "domain": row.domain,
        "keywords": list(row.keywords or []),
        "is_active": row.is_active,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _serialize_intent_definition(row: IntentDefinition) -> dict[str, object]:
    return {
        "id": row.id,
        "intent_name": row.intent_name,
        "domain": row.domain,
        "entity_type": row.entity_type,
        "slot_keys": list(row.slot_keys or []),
        "keywords": list(row.keywords or []),
        "persona_types": list(row.persona_types or []),
        "requires_aggregation": row.requires_aggregation,
        "is_default": row.is_default,
        "priority": row.priority,
        "is_active": row.is_active,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _serialize_domain_source_binding(
    row: DomainSourceBinding,
    source: DataSource | None = None,
) -> dict[str, object]:
    return {
        "id": row.id,
        "domain": row.domain,
        "source_type": row.source_type.value,
        "data_source_id": row.data_source_id,
        "data_source_name": source.name if source else None,
        "data_source_status": source.status.value if source else None,
        "is_active": row.is_active,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _serialize_data_source(row: DataSource) -> dict[str, object]:
    return {
        "id": row.id,
        "name": row.name,
        "source_type": row.source_type.value,
        "status": row.status.value,
        "department_scope": list(row.department_scope or []),
        "last_sync_at": row.last_sync_at,
        "sync_error_msg": row.sync_error_msg,
        "created_at": row.created_at,
    }


def _require_data_source(
    *,
    db: Session,
    tenant_id: str,
    source_id: str,
) -> DataSource:
    source = db.scalar(
        select(DataSource).where(
            DataSource.id == source_id,
            DataSource.tenant_id == tenant_id,
        )
    )
    if source is None:
        raise ValidationError(
            message="Data source not found",
            code="DATA_SOURCE_NOT_FOUND",
        )
    return source


def _build_connector_for_data_source(source: DataSource):
    probe_plan = CompiledQueryPlan(
        tenant_id=source.tenant_id,
        source_type=source.source_type.value,
        data_source_id=source.id,
        domain="admin",
        entity_type="connector_probe",
        parameterized_signature=f"connector_probe:{source.id}",
    )
    return connector_registry.get(probe_plan, source)


def _encode_data_source_config(config: dict[str, object]) -> str:
    return base64.b64encode(
        json.dumps(config, ensure_ascii=True, sort_keys=True).encode("utf-8")
    ).decode("utf-8")


def _normalize_department_scope(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw in values:
        value = str(raw).strip()
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def _extract_discovered_schema_rows(
    raw_schema: list[dict[str, object]],
) -> list[dict[str, str]]:
    rows_by_key: dict[tuple[str, str], dict[str, str]] = {}

    for item in raw_schema:
        if not isinstance(item, dict):
            continue

        table_name = str(
            item.get("table_name")
            or item.get("entity")
            or item.get("table")
            or "records"
        ).strip()
        if not table_name:
            table_name = "records"

        fields = item.get("fields")
        if isinstance(fields, list):
            for field in fields:
                if isinstance(field, dict):
                    column_name = str(
                        field.get("name")
                        or field.get("column_name")
                        or field.get("field")
                        or ""
                    ).strip()
                    data_type = str(
                        field.get("type")
                        or field.get("data_type")
                        or "text"
                    ).strip()
                else:
                    column_name = str(field).strip()
                    data_type = "text"

                if not column_name:
                    continue

                key = (table_name.lower(), column_name.lower())
                rows_by_key[key] = {
                    "real_table": table_name,
                    "real_column": column_name,
                    "data_type": data_type.lower() or "text",
                }
            continue

        column_name = str(item.get("column_name") or item.get("name") or "").strip()
        if not column_name:
            continue

        data_type = str(item.get("data_type") or item.get("type") or "text").strip()
        key = (table_name.lower(), column_name.lower())
        rows_by_key[key] = {
            "real_table": table_name,
            "real_column": column_name,
            "data_type": data_type.lower() or "text",
        }

    return list(rows_by_key.values())


def _looks_like_pii_column(column_name: str) -> bool:
    normalized = column_name.strip().lower()
    markers = (
        "email",
        "phone",
        "mobile",
        "ssn",
        "aadhaar",
        "pan",
        "dob",
        "birth",
        "address",
        "first_name",
        "last_name",
        "full_name",
        "account_number",
        "patient_id",
        "medical_record",
    )
    return any(marker in normalized for marker in markers)


def _sanitize_alias_token(value: str) -> str:
    collapsed = re.sub(r"[^a-z0-9_]+", "_", value.lower())
    collapsed = re.sub(r"_+", "_", collapsed).strip("_")
    token = collapsed[:50]
    return token or "field"


def _build_alias_token(
    *,
    source: DataSource,
    table_name: str,
    column_name: str,
    used_tokens: set[str],
) -> str:
    base = _sanitize_alias_token(
        f"{source.source_type.value}_{table_name}_{column_name}"
    )
    if base not in used_tokens:
        used_tokens.add(base)
        return base

    suffix = 2
    while True:
        suffix_text = f"_{suffix}"
        candidate = f"{base[: 50 - len(suffix_text)]}{suffix_text}"
        if candidate not in used_tokens:
            used_tokens.add(candidate)
            return candidate
        suffix += 1


def _refresh_schema_fields(
    *,
    db: Session,
    source: DataSource,
    raw_schema: list[dict[str, object]],
    prune_removed_fields: bool,
) -> dict[str, object]:
    discovered_rows = _extract_discovered_schema_rows(raw_schema)

    existing_rows = db.scalars(
        select(SchemaField).where(
            SchemaField.tenant_id == source.tenant_id,
            SchemaField.data_source_id == source.id,
        )
    ).all()
    existing_by_key = {
        (row.real_table.lower(), row.real_column.lower()): row for row in existing_rows
    }

    used_tokens = {
        token
        for token in db.scalars(
            select(SchemaField.alias_token).where(SchemaField.tenant_id == source.tenant_id)
        ).all()
        if token
    }

    added = 0
    updated = 0
    removed = 0

    for field in discovered_rows:
        table_name = field["real_table"]
        column_name = field["real_column"]
        data_type = field["data_type"]
        key = (table_name.lower(), column_name.lower())

        existing = existing_by_key.pop(key, None)
        if existing is None:
            alias_token = _build_alias_token(
                source=source,
                table_name=table_name,
                column_name=column_name,
                used_tokens=used_tokens,
            )
            db.add(
                SchemaField(
                    tenant_id=source.tenant_id,
                    data_source_id=source.id,
                    real_table=table_name,
                    real_column=column_name,
                    alias_token=alias_token,
                    display_name=column_name.replace("_", " ").strip().title()
                    or column_name,
                    data_type=data_type,
                    visibility=FieldVisibility.visible,
                    pii_flag=_looks_like_pii_column(column_name),
                    masked_for_personas=[],
                )
            )
            added += 1
            continue

        changed = False
        display_name = column_name.replace("_", " ").strip().title() or column_name

        if existing.real_table != table_name:
            existing.real_table = table_name
            changed = True
        if existing.real_column != column_name:
            existing.real_column = column_name
            changed = True
        if existing.data_type != data_type:
            existing.data_type = data_type
            changed = True
        if existing.display_name != display_name:
            existing.display_name = display_name
            changed = True
        if not existing.alias_token:
            existing.alias_token = _build_alias_token(
                source=source,
                table_name=table_name,
                column_name=column_name,
                used_tokens=used_tokens,
            )
            changed = True

        if changed:
            db.add(existing)
            updated += 1

    if prune_removed_fields:
        for stale in existing_by_key.values():
            db.delete(stale)
            removed += 1

    db.flush()

    total_fields = int(
        db.scalar(
            select(func.count())
            .select_from(SchemaField)
            .where(
                SchemaField.tenant_id == source.tenant_id,
                SchemaField.data_source_id == source.id,
            )
        )
        or 0
    )
    table_count = int(
        db.scalar(
            select(func.count(func.distinct(SchemaField.real_table))).where(
                SchemaField.tenant_id == source.tenant_id,
                SchemaField.data_source_id == source.id,
            )
        )
        or 0
    )
    pii_fields = int(
        db.scalar(
            select(func.count())
            .select_from(SchemaField)
            .where(
                SchemaField.tenant_id == source.tenant_id,
                SchemaField.data_source_id == source.id,
                SchemaField.pii_flag.is_(True),
            )
        )
        or 0
    )

    return {
        "discovered_rows": len(discovered_rows),
        "added": added,
        "updated": updated,
        "removed": removed,
        "total_fields": total_fields,
        "table_count": table_count,
        "pii_fields": pii_fields,
        "prune_removed_fields": prune_removed_fields,
    }


@router.get("/users")
def get_users(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=500),
    search: str | None = None,
    persona: str | None = None,
    department: str | None = None,
    status: str | None = None,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    stmt = select(User).where(User.tenant_id == scope.tenant_id)

    if search:
        like = f"%{search.lower()}%"
        stmt = stmt.where((User.email.ilike(like)) | (User.name.ilike(like)))
    if persona:
        stmt = stmt.where(User.persona_type == persona)
    if department:
        stmt = stmt.where(User.department == department)
    if status:
        stmt = stmt.where(User.status == status)

    offset = (page - 1) * limit
    users = db.scalars(stmt.offset(offset).limit(limit)).all()

    return {
        "page": page,
        "limit": limit,
        "items": [
            {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "persona_type": user.persona_type.value,
                "department": user.department,
                "status": user.status.value,
                "last_login": user.last_login,
            }
            for user in users
        ],
    }


@router.post("/users/import")
async def import_users(
    file: UploadFile = File(...),
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    payload = await file.read()
    csv_text = payload.decode("utf-8")
    reader = csv.DictReader(io.StringIO(csv_text))

    imported = 0
    failed = 0
    errors: list[dict] = []

    seen_emails: set[str] = set()
    for idx, row in enumerate(reader, start=2):
        try:
            email = (row.get("email") or "").strip().lower()
            if not email or "@" not in email:
                raise ValueError("Invalid email")
            if email in seen_emails:
                raise ValueError("Duplicate email in upload")
            seen_emails.add(email)

            existing = db.scalar(
                select(User).where(
                    User.tenant_id == scope.tenant_id, User.email == email
                )
            )
            if existing:
                continue

            persona = (row.get("persona_type") or "student").strip().lower()
            department = row.get("department") or None
            external_id = (row.get("external_id") or "").strip()
            if not external_id:
                raise ValueError("external_id is required")

            user = User(
                tenant_id=scope.tenant_id,
                email=email,
                name=(row.get("name") or email.split("@")[0]).strip(),
                persona_type=PersonaType(persona),
                department=department,
                external_id=external_id,
                admin_function=(row.get("admin_function") or None),
                course_ids=[
                    c.strip()
                    for c in (row.get("course_ids") or "").split(";")
                    if c.strip()
                ],
                masked_fields=[],
                status=UserStatus.active,
            )
            db.add(user)
            imported += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            errors.append({"row": idx, "reason": str(exc)})

    db.commit()
    return {"imported": imported, "failed": failed, "errors": errors}


@router.put("/users/{user_id}")
def update_user(
    user_id: str,
    payload: UserUpdateRequest,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    user = db.scalar(
        select(User).where(User.id == user_id, User.tenant_id == scope.tenant_id)
    )
    if not user:
        raise ValidationError(message="User not found", code="USER_NOT_FOUND")

    if payload.persona_type is not None:
        user.persona_type = PersonaType(payload.persona_type)
    if payload.department is not None:
        user.department = payload.department
    if payload.status is not None:
        user.status = UserStatus(payload.status)

    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "id": user.id,
        "email": user.email,
        "persona_type": user.persona_type.value,
        "department": user.department,
        "status": user.status.value,
    }


@router.get("/role-policies")
def list_role_policies(
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(RolePolicy)
        .where(RolePolicy.tenant_id == scope.tenant_id)
        .order_by(RolePolicy.role_key.asc())
    ).all()
    return [_serialize_role_policy(row) for row in rows]


@router.post("/role-policies")
def upsert_role_policy(
    payload: RolePolicyUpsertRequest,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    role_key = payload.role_key.strip().lower()
    if not role_key:
        raise ValidationError(message="role_key is required", code="ROLE_KEY_REQUIRED")

    if payload.row_scope_mode not in VALID_ROW_SCOPE_MODES:
        raise ValidationError(
            message="row_scope_mode must be one of owner_id, course_ids, department_id, admin_function",
            code="INVALID_ROW_SCOPE_MODE",
        )

    if payload.business_hours_start < 0 or payload.business_hours_start > 23:
        raise ValidationError(
            message="business_hours_start must be between 0 and 23",
            code="INVALID_BUSINESS_HOURS",
        )
    if payload.business_hours_end < 0 or payload.business_hours_end > 23:
        raise ValidationError(
            message="business_hours_end must be between 0 and 23",
            code="INVALID_BUSINESS_HOURS",
        )
    if payload.business_hours_end < payload.business_hours_start:
        raise ValidationError(
            message="business_hours_end must be greater than or equal to business_hours_start",
            code="INVALID_BUSINESS_HOURS",
        )

    existing = db.scalar(
        select(RolePolicy).where(
            RolePolicy.tenant_id == scope.tenant_id,
            RolePolicy.role_key == role_key,
        )
    )

    role_policy = existing or RolePolicy(
        tenant_id=scope.tenant_id,
        role_key=role_key,
        display_name=payload.display_name,
    )
    role_policy.display_name = payload.display_name
    role_policy.description = payload.description
    role_policy.allowed_domains = payload.allowed_domains
    role_policy.masked_fields = payload.masked_fields
    role_policy.aggregate_only = payload.aggregate_only
    role_policy.chat_enabled = payload.chat_enabled
    role_policy.row_scope_mode = payload.row_scope_mode
    role_policy.sensitive_domains = payload.sensitive_domains
    role_policy.require_business_hours_for_sensitive = (
        payload.require_business_hours_for_sensitive
    )
    role_policy.business_hours_start = payload.business_hours_start
    role_policy.business_hours_end = payload.business_hours_end
    role_policy.require_trusted_device_for_sensitive = (
        payload.require_trusted_device_for_sensitive
    )
    role_policy.require_mfa_for_sensitive = payload.require_mfa_for_sensitive
    role_policy.is_active = payload.is_active

    db.add(role_policy)
    db.commit()
    db.refresh(role_policy)
    return _serialize_role_policy(role_policy)


@router.delete("/role-policies/{role_key}")
def deactivate_role_policy(
    role_key: str,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    normalized_key = role_key.strip().lower()
    row = db.scalar(
        select(RolePolicy).where(
            RolePolicy.tenant_id == scope.tenant_id,
            RolePolicy.role_key == normalized_key,
        )
    )
    if not row:
        raise ValidationError(
            message="Role policy not found",
            code="ROLE_POLICY_NOT_FOUND",
        )

    row.is_active = False
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_role_policy(row)


@router.get("/policies/field-level-masking")
def list_field_level_masking_rules(
    data_source_id: str | None = Query(default=None),
    visibility: str | None = Query(default=None),
    pii_only: bool = False,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    stmt = select(SchemaField).where(SchemaField.tenant_id == scope.tenant_id)

    if data_source_id:
        stmt = stmt.where(SchemaField.data_source_id == data_source_id)

    if visibility is not None:
        normalized_visibility = visibility.strip().lower()
        try:
            requested_visibility = FieldVisibility(normalized_visibility)
        except ValueError as exc:
            raise ValidationError(
                message="visibility must be one of visible, masked, hidden",
                code="INVALID_FIELD_VISIBILITY",
            ) from exc
        stmt = stmt.where(SchemaField.visibility == requested_visibility)

    if pii_only:
        stmt = stmt.where(SchemaField.pii_flag.is_(True))

    rows = db.scalars(
        stmt.order_by(
            SchemaField.real_table.asc(),
            SchemaField.real_column.asc(),
        )
    ).all()

    source_ids = sorted({row.data_source_id for row in rows})
    sources_by_id: dict[str, DataSource] = {}
    if source_ids:
        sources = db.scalars(
            select(DataSource).where(
                DataSource.tenant_id == scope.tenant_id,
                DataSource.id.in_(source_ids),
            )
        ).all()
        sources_by_id = {source.id: source for source in sources}

    role_policies = db.scalars(
        select(RolePolicy).where(
            RolePolicy.tenant_id == scope.tenant_id,
            RolePolicy.is_active.is_(True),
        )
    ).all()
    masked_by_alias: dict[str, set[str]] = {}
    for role_policy in role_policies:
        for alias_token in role_policy.masked_fields or []:
            token = str(alias_token).strip()
            if not token:
                continue
            masked_by_alias.setdefault(token, set()).add(role_policy.role_key)

    items: list[dict[str, object]] = []
    for row in rows:
        source = sources_by_id.get(row.data_source_id)
        role_keys = sorted(masked_by_alias.get(row.alias_token, set()))
        items.append(
            {
                "schema_field_id": row.id,
                "data_source_id": row.data_source_id,
                "data_source_name": source.name if source else None,
                "real_table": row.real_table,
                "real_column": row.real_column,
                "alias_token": row.alias_token,
                "display_name": row.display_name,
                "data_type": row.data_type,
                "visibility": row.visibility.value,
                "pii_flag": row.pii_flag,
                "masked_for_personas": list(row.masked_for_personas or []),
                "role_keys_masked": role_keys,
                "updated_via_role_policy": bool(role_keys),
            }
        )

    return {
        "items": items,
        "summary": {
            "total_fields": len(items),
            "masked_fields": sum(
                1 for item in items if item["visibility"] == FieldVisibility.masked.value
            ),
            "hidden_fields": sum(
                1 for item in items if item["visibility"] == FieldVisibility.hidden.value
            ),
            "pii_fields": sum(1 for item in items if item["pii_flag"]),
        },
    }


@router.put("/policies/field-level-masking")
def update_field_level_masking_rule(
    payload: FieldMaskingPolicyUpdateRequest,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    row = db.scalar(
        select(SchemaField).where(
            SchemaField.id == payload.schema_field_id,
            SchemaField.tenant_id == scope.tenant_id,
        )
    )
    if row is None:
        raise ValidationError(
            message="Schema field not found",
            code="SCHEMA_FIELD_NOT_FOUND",
        )

    previous_personas = set(_normalize_text_list(list(row.masked_for_personas or [])))
    current_personas = previous_personas

    if payload.visibility is not None:
        row.visibility = FieldVisibility(payload.visibility)

    if payload.pii_flag is not None:
        row.pii_flag = payload.pii_flag

    if payload.display_name is not None:
        normalized_display_name = payload.display_name.strip()
        if not normalized_display_name:
            raise ValidationError(
                message="display_name cannot be empty",
                code="DISPLAY_NAME_REQUIRED",
            )
        row.display_name = normalized_display_name

    if payload.masked_for_personas is not None:
        normalized_personas = _normalize_persona_values(payload.masked_for_personas)
        row.masked_for_personas = normalized_personas
        current_personas = set(normalized_personas)
        if normalized_personas and row.visibility == FieldVisibility.visible:
            row.visibility = FieldVisibility.masked

    sync_summary = {
        "added_to_role_policies": [],
        "removed_from_role_policies": [],
    }
    if payload.sync_role_policies and payload.masked_for_personas is not None:
        sync_summary = _sync_role_policy_masked_fields_for_schema_field(
            db=db,
            tenant_id=scope.tenant_id,
            alias_token=row.alias_token,
            previous_personas=previous_personas,
            current_personas=current_personas,
        )

    db.add(row)
    db.commit()
    db.refresh(row)

    source = db.scalar(
        select(DataSource).where(
            DataSource.id == row.data_source_id,
            DataSource.tenant_id == scope.tenant_id,
        )
    )

    return {
        "item": {
            "schema_field_id": row.id,
            "data_source_id": row.data_source_id,
            "data_source_name": source.name if source else None,
            "real_table": row.real_table,
            "real_column": row.real_column,
            "alias_token": row.alias_token,
            "display_name": row.display_name,
            "data_type": row.data_type,
            "visibility": row.visibility.value,
            "pii_flag": row.pii_flag,
            "masked_for_personas": list(row.masked_for_personas or []),
        },
        "sync": sync_summary,
    }


@router.get("/policies/row-level")
def list_row_level_policy_rules(
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(RolePolicy)
        .where(RolePolicy.tenant_id == scope.tenant_id)
        .order_by(RolePolicy.role_key.asc())
    ).all()

    return {
        "items": [
            {
                "role_key": row.role_key,
                "display_name": row.display_name,
                "row_scope_mode": row.row_scope_mode,
                "sensitive_domains": list(row.sensitive_domains or []),
                "require_business_hours_for_sensitive": row.require_business_hours_for_sensitive,
                "business_hours_start": row.business_hours_start,
                "business_hours_end": row.business_hours_end,
                "require_trusted_device_for_sensitive": row.require_trusted_device_for_sensitive,
                "require_mfa_for_sensitive": row.require_mfa_for_sensitive,
                "is_active": row.is_active,
            }
            for row in rows
        ]
    }


@router.put("/policies/row-level/{role_key}")
def update_row_level_policy_rule(
    role_key: str,
    payload: RowLevelPolicyUpdateRequest,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    normalized_role_key = role_key.strip().lower()
    role_policy = db.scalar(
        select(RolePolicy).where(
            RolePolicy.tenant_id == scope.tenant_id,
            RolePolicy.role_key == normalized_role_key,
        )
    )
    if role_policy is None:
        raise ValidationError(
            message="Role policy not found",
            code="ROLE_POLICY_NOT_FOUND",
        )

    if payload.row_scope_mode is not None:
        role_policy.row_scope_mode = payload.row_scope_mode

    if payload.sensitive_domains is not None:
        role_policy.sensitive_domains = _normalize_text_list(payload.sensitive_domains)

    if payload.require_business_hours_for_sensitive is not None:
        role_policy.require_business_hours_for_sensitive = payload.require_business_hours_for_sensitive

    if payload.require_trusted_device_for_sensitive is not None:
        role_policy.require_trusted_device_for_sensitive = payload.require_trusted_device_for_sensitive

    if payload.require_mfa_for_sensitive is not None:
        role_policy.require_mfa_for_sensitive = payload.require_mfa_for_sensitive

    merged_start = (
        payload.business_hours_start
        if payload.business_hours_start is not None
        else role_policy.business_hours_start
    )
    merged_end = (
        payload.business_hours_end
        if payload.business_hours_end is not None
        else role_policy.business_hours_end
    )
    if merged_end < merged_start:
        raise ValidationError(
            message="business_hours_end must be greater than or equal to business_hours_start",
            code="INVALID_BUSINESS_HOURS",
        )

    if payload.business_hours_start is not None:
        role_policy.business_hours_start = payload.business_hours_start
    if payload.business_hours_end is not None:
        role_policy.business_hours_end = payload.business_hours_end

    db.add(role_policy)
    db.commit()
    db.refresh(role_policy)
    return _serialize_role_policy(role_policy)


@router.get("/domain-keywords")
def list_domain_keywords(
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(DomainKeyword)
        .where(DomainKeyword.tenant_id == scope.tenant_id)
        .order_by(DomainKeyword.domain.asc())
    ).all()
    return [_serialize_domain_keyword(row) for row in rows]


@router.get("/interpreter/onboarding-validation")
def validate_interpreter_onboarding_config(
    domain: str | None = Query(default=None),
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    return validate_interpreter_onboarding(
        db=db,
        tenant_id=scope.tenant_id,
        domain=domain,
    )


@router.get("/actions/templates")
def list_action_template_schemas(
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    return {
        "templates": action_template_override_service.list_templates(
            db=db,
            tenant_id=scope.tenant_id,
        ),
        "health": action_registry_health(),
        "requested_by": scope.user_id,
    }


@router.put("/actions/templates/{action_id}")
def upsert_action_template_override(
    action_id: str,
    payload: ActionTemplateOverrideUpsertRequest,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    updates = payload.model_dump(exclude_unset=True)
    return action_template_override_service.upsert_override(
        db=db,
        tenant_id=scope.tenant_id,
        action_id=action_id,
        updated_by=scope.user_id,
        updates=updates,
    )


@router.delete("/actions/templates/{action_id}")
def delete_action_template_override(
    action_id: str,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    return action_template_override_service.delete_override(
        db=db,
        tenant_id=scope.tenant_id,
        action_id=action_id,
    )


@router.post("/actions/execute")
def execute_action_template(
    payload: ActionExecuteRequest,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    action_id = payload.action_id.strip().upper()
    return action_orchestrator_service.execute_action(
        db=db,
        scope=scope,
        action_id=action_id,
        input_payload=payload.input_payload,
        dry_run=payload.dry_run,
    )


@router.get("/actions/executions")
def list_action_executions(
    action_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    return action_orchestrator_service.list_executions(
        db=db,
        scope=scope,
        action_id=action_id,
        status=status,
        limit=limit,
    )


@router.get("/actions/executions/{execution_id}")
def get_action_execution(
    execution_id: str,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    return action_orchestrator_service.get_execution(
        db=db,
        scope=scope,
        execution_id=execution_id,
    )


@router.post("/actions/executions/{execution_id}/approve")
def approve_action_execution(
    execution_id: str,
    payload: ActionApprovalRequest,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    compliance_case_service.assert_execution_approvable(
        db=db,
        tenant_id=scope.tenant_id,
        execution_id=execution_id,
    )
    return action_orchestrator_service.approve_action(
        db=db,
        scope=scope,
        execution_id=execution_id,
        comment=payload.comment,
    )


@router.post("/actions/executions/{execution_id}/rollback")
def rollback_action_execution(
    execution_id: str,
    payload: ActionRollbackRequest,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    return action_orchestrator_service.rollback_action(
        db=db,
        scope=scope,
        execution_id=execution_id,
        reason=payload.reason,
    )


@router.post("/actions/escalations/evaluate")
def evaluate_action_escalations(
    as_of: datetime | None = Query(default=None),
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    normalized = as_of
    if normalized is not None and normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=UTC)

    return action_orchestrator_service.evaluate_pending_escalations(
        db=db,
        tenant_id=scope.tenant_id,
        as_of=normalized,
    )


@router.get("/compliance/summary")
def get_compliance_summary(
    from_at: datetime | None = Query(default=None),
    to_at: datetime | None = Query(default=None),
    limit: int = Query(default=500, ge=50, le=5000),
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    normalized_from = from_at
    if normalized_from is not None and normalized_from.tzinfo is None:
        normalized_from = normalized_from.replace(tzinfo=UTC)

    normalized_to = to_at
    if normalized_to is not None and normalized_to.tzinfo is None:
        normalized_to = normalized_to.replace(tzinfo=UTC)

    return compliance_operations_service.get_summary(
        scope=scope,
        db=db,
        from_at=normalized_from,
        to_at=normalized_to,
        limit=limit,
    )


@router.post("/compliance/forensic-export")
def export_compliance_forensics(
    payload: ComplianceForensicExportRequest,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    normalized_from = payload.from_at
    if normalized_from.tzinfo is None:
        normalized_from = normalized_from.replace(tzinfo=UTC)

    normalized_to = payload.to_at
    if normalized_to.tzinfo is None:
        normalized_to = normalized_to.replace(tzinfo=UTC)

    return compliance_operations_service.generate_forensic_export(
        scope=scope,
        db=db,
        from_at=normalized_from,
        to_at=normalized_to,
        include_action_ids=payload.include_action_ids,
        include_blocked_queries_only=payload.include_blocked_queries_only,
        max_items=payload.max_items,
    )


@router.post("/compliance/retention/run")
def run_compliance_retention(
    payload: ComplianceRetentionRunRequest,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    normalized_as_of = payload.as_of
    if normalized_as_of is not None and normalized_as_of.tzinfo is None:
        normalized_as_of = normalized_as_of.replace(tzinfo=UTC)

    return compliance_retention_service.run_retention(
        db=db,
        scope=scope,
        retention_days=payload.retention_days,
        dry_run=payload.dry_run,
        max_items=payload.max_items,
        as_of=normalized_as_of,
    )


@router.post("/compliance/attestations")
def create_compliance_attestation(
    payload: ComplianceAttestationCreateRequest,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    normalized_from = payload.from_at
    if normalized_from is not None and normalized_from.tzinfo is None:
        normalized_from = normalized_from.replace(tzinfo=UTC)

    normalized_to = payload.to_at
    if normalized_to is not None and normalized_to.tzinfo is None:
        normalized_to = normalized_to.replace(tzinfo=UTC)

    return compliance_attestation_service.create_attestation(
        db=db,
        scope=scope,
        framework=payload.framework,
        from_at=normalized_from,
        to_at=normalized_to,
        max_items=payload.max_items,
        statement=payload.statement,
    )


@router.get("/compliance/attestations")
def list_compliance_attestations(
    framework: str | None = Query(default=None),
    from_at: datetime | None = Query(default=None),
    to_at: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    normalized_from = from_at
    if normalized_from is not None and normalized_from.tzinfo is None:
        normalized_from = normalized_from.replace(tzinfo=UTC)

    normalized_to = to_at
    if normalized_to is not None and normalized_to.tzinfo is None:
        normalized_to = normalized_to.replace(tzinfo=UTC)

    return compliance_attestation_service.list_attestations(
        db=db,
        scope=scope,
        framework=framework,
        from_at=normalized_from,
        to_at=normalized_to,
        limit=limit,
    )


@router.get("/system/fleet-health")
def get_system_fleet_health(
    lookback_hours: int = Query(default=24, ge=1, le=168),
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    return system_admin_service.get_fleet_health(
        db=db,
        scope=scope,
        lookback_hours=lookback_hours,
    )


@router.get("/system/tenant-deep-dive")
def get_system_tenant_deep_dive(
    window_days: int = Query(default=30, ge=7, le=365),
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    return system_admin_service.get_tenant_deep_dive(
        db=db,
        scope=scope,
        window_days=window_days,
    )


@router.get("/system/churn-risk")
def get_system_churn_risk(
    window_days: int = Query(default=14, ge=4, le=120),
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    return system_admin_service.get_churn_risk(
        db=db,
        scope=scope,
        window_days=window_days,
    )


@router.get("/system/llm-costs")
def get_system_llm_cost_analytics(
    window_days: int = Query(default=30, ge=7, le=365),
    estimated_cost_per_query: float = Query(default=0.0132, ge=0.0001, le=1.0),
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    return system_admin_service.get_llm_cost_analytics(
        db=db,
        scope=scope,
        window_days=window_days,
        estimated_cost_per_query=estimated_cost_per_query,
    )


@router.get("/system/slo-compliance")
def get_system_slo_compliance(
    window_days: int = Query(default=30, ge=7, le=365),
    latency_target_ms: int = Query(default=1000, ge=100, le=10000),
    error_budget_percent: float = Query(default=0.1, ge=0.01, le=10.0),
    dsar_slo_days: int = Query(default=10, ge=1, le=90),
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    return system_admin_service.get_slo_compliance(
        db=db,
        scope=scope,
        window_days=window_days,
        latency_target_ms=latency_target_ms,
        error_budget_percent=error_budget_percent,
        dsar_slo_days=dsar_slo_days,
    )


@router.get("/system/capacity-model")
def get_system_capacity_model(
    window_days: int = Query(default=30, ge=7, le=365),
    target_p95_ms: int = Query(default=1000, ge=100, le=10000),
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    return system_admin_service.get_capacity_model(
        db=db,
        scope=scope,
        window_days=window_days,
        target_p95_ms=target_p95_ms,
    )


@router.get("/system/degradation-policy")
def get_system_degradation_policy_status(
    lookback_hours: int = Query(default=24, ge=1, le=168),
    warning_p95_ms: int = Query(default=1000, ge=100, le=10000),
    critical_p95_ms: int = Query(default=1500, ge=100, le=10000),
    warning_error_rate_percent: float = Query(default=0.1, ge=0.01, le=100.0),
    critical_error_rate_percent: float = Query(default=1.0, ge=0.01, le=100.0),
    warning_pending_actions: int = Query(default=20, ge=1, le=10000),
    critical_pending_actions: int = Query(default=50, ge=1, le=10000),
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    return system_admin_service.get_degradation_policy_status(
        db=db,
        scope=scope,
        lookback_hours=lookback_hours,
        warning_p95_ms=warning_p95_ms,
        critical_p95_ms=critical_p95_ms,
        warning_error_rate_percent=warning_error_rate_percent,
        critical_error_rate_percent=critical_error_rate_percent,
        warning_pending_actions=warning_pending_actions,
        critical_pending_actions=critical_pending_actions,
    )


@router.get("/system/performance-regression")
def get_system_performance_regression(
    window_hours: int = Query(default=24, ge=1, le=720),
    max_p95_regression_percent: float = Query(default=15.0, ge=0.0, le=500.0),
    max_p99_regression_percent: float = Query(default=20.0, ge=0.0, le=500.0),
    max_error_rate_percent: float = Query(default=0.1, ge=0.0, le=100.0),
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    return system_admin_service.get_performance_regression(
        db=db,
        scope=scope,
        window_hours=window_hours,
        max_p95_regression_percent=max_p95_regression_percent,
        max_p99_regression_percent=max_p99_regression_percent,
        max_error_rate_percent=max_error_rate_percent,
    )


@router.get("/system/alerts")
def get_system_alerts(
    lookback_hours: int = Query(default=24, ge=1, le=168),
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    return system_admin_service.get_alerts(
        db=db,
        scope=scope,
        lookback_hours=lookback_hours,
    )


@router.post("/compliance/cases")
def create_compliance_case(
    payload: ComplianceCaseCreateRequest,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    return compliance_case_service.create_case(
        db=db,
        scope=scope,
        case_type=payload.case_type,
        subject_identifier=payload.subject_identifier,
        delivery_method=payload.delivery_method,
        legal_basis=payload.legal_basis,
    )


@router.get("/compliance/cases")
def list_compliance_cases(
    case_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    return compliance_case_service.list_cases(
        db=db,
        scope=scope,
        case_type=case_type,
        status=status,
        limit=limit,
    )


@router.get("/compliance/cases/{case_id}")
def get_compliance_case(
    case_id: str,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    return compliance_case_service.get_case(
        db=db,
        scope=scope,
        case_id=case_id,
    )


@router.post("/compliance/cases/{case_id}/legal-hold")
def set_compliance_case_legal_hold(
    case_id: str,
    payload: ComplianceCaseLegalHoldRequest,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    return compliance_case_service.set_legal_hold(
        db=db,
        scope=scope,
        case_id=case_id,
        active=payload.active,
        reason=payload.reason,
    )


@router.post("/compliance/cases/{case_id}/approve")
def approve_compliance_case(
    case_id: str,
    payload: ActionApprovalRequest,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    return compliance_case_service.approve_case(
        db=db,
        scope=scope,
        case_id=case_id,
        comment=payload.comment,
    )


@router.post("/domain-keywords")
def upsert_domain_keywords(
    payload: DomainKeywordUpsertRequest,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    domain = payload.domain.strip().lower()
    if not domain:
        raise ValidationError(message="domain is required", code="DOMAIN_REQUIRED")

    existing = db.scalar(
        select(DomainKeyword).where(
            DomainKeyword.tenant_id == scope.tenant_id,
            DomainKeyword.domain == domain,
        )
    )

    row = existing or DomainKeyword(tenant_id=scope.tenant_id, domain=domain)
    row.keywords = _normalize_text_list(payload.keywords)
    row.is_active = payload.is_active

    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_domain_keyword(row)


@router.delete("/domain-keywords/{domain}")
def deactivate_domain_keywords(
    domain: str,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    normalized = domain.strip().lower()
    row = db.scalar(
        select(DomainKeyword).where(
            DomainKeyword.tenant_id == scope.tenant_id,
            DomainKeyword.domain == normalized,
        )
    )
    if not row:
        raise ValidationError(
            message="Domain keyword config not found",
            code="DOMAIN_KEYWORDS_NOT_FOUND",
        )

    row.is_active = False
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_domain_keyword(row)


@router.get("/intent-definitions")
def list_intent_definitions(
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(IntentDefinition)
        .where(IntentDefinition.tenant_id == scope.tenant_id)
        .order_by(IntentDefinition.priority.asc(), IntentDefinition.intent_name.asc())
    ).all()
    return [_serialize_intent_definition(row) for row in rows]


@router.post("/intent-definitions")
def upsert_intent_definition(
    payload: IntentDefinitionUpsertRequest,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    intent_name = payload.intent_name.strip().lower()
    domain = payload.domain.strip().lower()
    entity_type = payload.entity_type.strip().lower()
    if not intent_name:
        raise ValidationError(
            message="intent_name is required",
            code="INTENT_NAME_REQUIRED",
        )
    if not domain:
        raise ValidationError(message="domain is required", code="DOMAIN_REQUIRED")
    if not entity_type:
        raise ValidationError(
            message="entity_type is required",
            code="ENTITY_TYPE_REQUIRED",
        )
    if payload.priority < 0:
        raise ValidationError(
            message="priority must be >= 0",
            code="INVALID_PRIORITY",
        )

    slot_keys = _normalize_text_list(payload.slot_keys)
    if not slot_keys:
        raise ValidationError(
            message="slot_keys must include at least one key",
            code="SLOT_KEYS_REQUIRED",
        )

    existing = db.scalar(
        select(IntentDefinition).where(
            IntentDefinition.tenant_id == scope.tenant_id,
            IntentDefinition.intent_name == intent_name,
        )
    )

    row = existing or IntentDefinition(
        tenant_id=scope.tenant_id,
        intent_name=intent_name,
        domain=domain,
        entity_type=entity_type,
    )
    row.domain = domain
    row.entity_type = entity_type
    row.slot_keys = slot_keys
    row.keywords = _normalize_text_list(payload.keywords)
    row.persona_types = _normalize_text_list(payload.persona_types)
    row.requires_aggregation = payload.requires_aggregation
    row.is_default = payload.is_default
    row.priority = payload.priority
    row.is_active = payload.is_active

    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_intent_definition(row)


@router.delete("/intent-definitions/{intent_name}")
def deactivate_intent_definition(
    intent_name: str,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    normalized = intent_name.strip().lower()
    row = db.scalar(
        select(IntentDefinition).where(
            IntentDefinition.tenant_id == scope.tenant_id,
            IntentDefinition.intent_name == normalized,
        )
    )
    if not row:
        raise ValidationError(
            message="Intent definition not found",
            code="INTENT_DEFINITION_NOT_FOUND",
        )

    row.is_active = False
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_intent_definition(row)


def _serialize_intent_detection_keyword(
    row: IntentDetectionKeyword,
) -> dict[str, object]:
    return {
        "id": row.id,
        "intent_name": row.intent_name,
        "keyword_type": row.keyword_type,
        "keyword": row.keyword,
        "priority": row.priority,
        "is_active": row.is_active,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


@router.get("/intent-detection-keywords")
def list_intent_detection_keywords(
    intent_name: str | None = Query(None),
    keyword_type: str | None = Query(None),
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    """List intent detection keywords, optionally filtered by intent_name or keyword_type.

    Detection keywords are used to identify and route specific intents.
    Example: grade markers (gpa, grade, grades) route to student_grades intent.
    """
    q = select(IntentDetectionKeyword).where(
        IntentDetectionKeyword.tenant_id == scope.tenant_id,
        IntentDetectionKeyword.is_active.is_(True),
    )

    if intent_name:
        q = q.where(
            IntentDetectionKeyword.intent_name
            == intent_name.strip().lower()
        )
    if keyword_type:
        q = q.where(
            IntentDetectionKeyword.keyword_type
            == keyword_type.strip().lower()
        )

    rows = db.scalars(
        q.order_by(
            IntentDetectionKeyword.intent_name,
            IntentDetectionKeyword.keyword_type,
            IntentDetectionKeyword.keyword,
        )
    ).all()
    return [_serialize_intent_detection_keyword(row) for row in rows]


@router.post("/intent-detection-keywords")
def upsert_intent_detection_keyword(
    payload: IntentDetectionKeywordUpsertRequest,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    """Create or update an intent detection keyword.

    Detection keywords enable database-driven intent routing. For example,
    adding "gpa" as a grade_marker for student_grades allows grade-related
    queries to be routed to the correct intent without code changes.

    The combination of (tenant_id, intent_name, keyword_type, keyword)
    must be unique.
    """
    intent_name = payload.intent_name.strip().lower()
    keyword_type = payload.keyword_type.strip().lower()
    keyword = payload.keyword.strip().lower()

    if not intent_name:
        raise ValidationError(
            message="intent_name is required",
            code="INTENT_NAME_REQUIRED",
        )
    if not keyword_type:
        raise ValidationError(
            message="keyword_type is required",
            code="KEYWORD_TYPE_REQUIRED",
        )
    if not keyword:
        raise ValidationError(
            message="keyword is required",
            code="KEYWORD_REQUIRED",
        )
    if payload.priority < 0:
        raise ZTAError(
            message="priority must be >= 0",
            code="INVALID_PRIORITY",
            status_code=400,
        )

    existing = db.scalar(
        select(IntentDetectionKeyword).where(
            and_(
                IntentDetectionKeyword.tenant_id == scope.tenant_id,
                IntentDetectionKeyword.intent_name == intent_name,
                IntentDetectionKeyword.keyword_type == keyword_type,
                IntentDetectionKeyword.keyword == keyword,
            )
        )
    )

    if existing:
        existing.priority = payload.priority
        existing.is_active = payload.is_active
        row = existing
    else:
        row = IntentDetectionKeyword(
            tenant_id=scope.tenant_id,
            intent_name=intent_name,
            keyword_type=keyword_type,
            keyword=keyword,
            priority=payload.priority,
            is_active=payload.is_active,
        )

    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_intent_detection_keyword(row)


@router.delete("/intent-detection-keywords/{keyword_id}")
def deactivate_intent_detection_keyword(
    keyword_id: str,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    """Deactivate (soft-delete) an intent detection keyword.

    The keyword is marked as inactive but not permanently deleted from the
    database, preserving audit trail.
    """
    row = db.scalar(
        select(IntentDetectionKeyword).where(
            and_(
                IntentDetectionKeyword.tenant_id == scope.tenant_id,
                IntentDetectionKeyword.id == keyword_id,
            )
        )
    )

    if not row:
        raise ZTAError(
            message="Intent detection keyword not found",
            code="KEYWORD_NOT_FOUND",
            status_code=400,
        )

    row.is_active = False
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_intent_detection_keyword(row)


@router.get("/domain-source-bindings")
def list_domain_source_bindings(
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(DomainSourceBinding)
        .where(DomainSourceBinding.tenant_id == scope.tenant_id)
        .order_by(DomainSourceBinding.domain.asc())
    ).all()

    source_ids = [row.data_source_id for row in rows if row.data_source_id]
    sources_by_id: dict[str, DataSource] = {}
    if source_ids:
        sources = db.scalars(
            select(DataSource).where(
                DataSource.tenant_id == scope.tenant_id,
                DataSource.id.in_(source_ids),
            )
        ).all()
        sources_by_id = {source.id: source for source in sources}

    return [
        _serialize_domain_source_binding(
            row,
            sources_by_id.get(row.data_source_id) if row.data_source_id else None,
        )
        for row in rows
    ]


@router.post("/domain-source-bindings")
def upsert_domain_source_binding(
    payload: DomainSourceBindingUpsertRequest,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    domain = payload.domain.strip().lower()
    if not domain:
        raise ValidationError(message="domain is required", code="DOMAIN_REQUIRED")

    source: DataSource | None = None
    resolved_source_type: DataSourceType | None = None
    source_type_from_payload = payload.source_type
    if source_type_from_payload is not None:
        normalized_type = source_type_from_payload.strip().lower()
        try:
            resolved_source_type = DataSourceType(normalized_type)
        except ValueError as exc:
            raise ValidationError(
                message="Invalid source_type",
                code="INVALID_SOURCE_TYPE",
            ) from exc

    if payload.data_source_id:
        source = db.scalar(
            select(DataSource).where(
                DataSource.id == payload.data_source_id,
                DataSource.tenant_id == scope.tenant_id,
            )
        )
        if not source:
            raise ValidationError(
                message="data_source_id not found for tenant",
                code="DATA_SOURCE_NOT_FOUND",
            )
        if source.status != DataSourceStatus.connected:
            raise ValidationError(
                message="Bound data source must be connected",
                code="BOUND_SOURCE_NOT_CONNECTED",
            )
        if (
            resolved_source_type is not None
            and resolved_source_type.value != source.source_type.value
        ):
            raise ValidationError(
                message="source_type must match the selected data_source_id",
                code="SOURCE_TYPE_MISMATCH",
            )
        resolved_source_type = source.source_type

    if resolved_source_type is None:
        raise ValidationError(
            message="Provide source_type or data_source_id",
            code="SOURCE_BINDING_TARGET_REQUIRED",
        )

    row = db.scalar(
        select(DomainSourceBinding).where(
            DomainSourceBinding.tenant_id == scope.tenant_id,
            DomainSourceBinding.domain == domain,
        )
    )
    binding = row or DomainSourceBinding(
        tenant_id=scope.tenant_id,
        domain=domain,
        source_type=resolved_source_type,
    )

    binding.source_type = resolved_source_type
    binding.data_source_id = source.id if source else None
    binding.is_active = payload.is_active

    db.add(binding)
    db.commit()
    db.refresh(binding)
    return _serialize_domain_source_binding(binding, source)


@router.delete("/domain-source-bindings/{domain}")
def deactivate_domain_source_binding(
    domain: str,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    normalized_domain = domain.strip().lower()
    row = db.scalar(
        select(DomainSourceBinding).where(
            DomainSourceBinding.tenant_id == scope.tenant_id,
            DomainSourceBinding.domain == normalized_domain,
        )
    )
    if not row:
        raise ValidationError(
            message="Domain source binding not found",
            code="DOMAIN_SOURCE_BINDING_NOT_FOUND",
        )

    row.is_active = False
    db.add(row)
    db.commit()
    db.refresh(row)

    source = None
    if row.data_source_id:
        source = db.scalar(
            select(DataSource).where(
                DataSource.id == row.data_source_id,
                DataSource.tenant_id == scope.tenant_id,
            )
        )
    return _serialize_domain_source_binding(row, source)


@router.get("/data-sources")
def list_data_sources(
    scope: ScopeContext = Depends(require_it_head), db: Session = Depends(get_db)
):
    rows = db.scalars(
        select(DataSource).where(DataSource.tenant_id == scope.tenant_id)
    ).all()
    return [_serialize_data_source(row) for row in rows]


@router.post("/data-sources")
def create_data_source(
    payload: DataSourceCreateRequest,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    encoded_config = _encode_data_source_config(payload.config)
    source = DataSource(
        tenant_id=scope.tenant_id,
        name=payload.name,
        source_type=DataSourceType(payload.source_type),
        config_encrypted=encoded_config,
        department_scope=_normalize_department_scope(payload.department_scope),
        status=DataSourceStatus.connected,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return _serialize_data_source(source)


@router.put("/data-sources/{source_id}")
def update_data_source(
    source_id: str,
    payload: DataSourceUpdateRequest,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    source = _require_data_source(
        db=db,
        tenant_id=scope.tenant_id,
        source_id=source_id,
    )

    if payload.name is not None:
        normalized_name = payload.name.strip()
        if not normalized_name:
            raise ValidationError(
                message="name cannot be empty",
                code="DATA_SOURCE_NAME_REQUIRED",
            )
        source.name = normalized_name

    if payload.department_scope is not None:
        source.department_scope = _normalize_department_scope(payload.department_scope)

    if payload.config is not None:
        source.config_encrypted = _encode_data_source_config(payload.config)

    if payload.status is not None:
        normalized_status = payload.status.strip().lower()
        if normalized_status not in {
            DataSourceStatus.connected.value,
            DataSourceStatus.disconnected.value,
            DataSourceStatus.paused.value,
        }:
            raise ValidationError(
                message="status must be one of connected, disconnected, paused",
                code="DATA_SOURCE_STATUS_INVALID",
            )
        source.status = DataSourceStatus(normalized_status)
        if source.status == DataSourceStatus.connected:
            source.sync_error_msg = None

    db.add(source)
    db.commit()
    db.refresh(source)
    return _serialize_data_source(source)


@router.post("/data-sources/{source_id}/test-connection")
def test_data_source_connection(
    source_id: str,
    timeout_seconds: int = Query(default=10, ge=1, le=120),
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    source = _require_data_source(
        db=db,
        tenant_id=scope.tenant_id,
        source_id=source_id,
    )

    now = datetime.now(tz=UTC)
    try:
        connector = _build_connector_for_data_source(source)
        result = connector.test_connection(timeout_seconds=timeout_seconds)

        source.last_sync_at = now
        source.status = (
            DataSourceStatus.connected
            if result.status in {"healthy", "degraded"}
            else DataSourceStatus.error
        )
        source.sync_error_msg = result.error
        db.add(source)
        db.commit()
        db.refresh(source)

        return {
            "data_source": _serialize_data_source(source),
            "test_result": {
                "status": result.status,
                "latency_ms": result.latency_ms,
                "error": result.error,
            },
        }
    except ValidationError as exc:
        source.last_sync_at = now
        source.status = DataSourceStatus.error
        source.sync_error_msg = exc.message
        db.add(source)
        db.commit()
        db.refresh(source)
        return {
            "data_source": _serialize_data_source(source),
            "test_result": {
                "status": "error",
                "latency_ms": 0,
                "error": exc.message,
                "error_code": exc.code,
            },
        }


@router.get("/data-sources/{source_id}/health")
def get_data_source_health(
    source_id: str,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    source = _require_data_source(
        db=db,
        tenant_id=scope.tenant_id,
        source_id=source_id,
    )

    try:
        connector = _build_connector_for_data_source(source)
        health = connector.health_check()
        connection_info = connector.get_connection_info()
        return {
            "data_source": _serialize_data_source(source),
            "health": {
                "status": health.status,
                "last_query_latency_ms": health.last_query_latency_ms,
                "consecutive_failures": health.consecutive_failures,
                "last_failure_at": health.last_failure_at,
                "recommendation": health.recommendation,
            },
            "connection_info": {
                "connector_id": connection_info.connector_id,
                "tenant_id": connection_info.tenant_id,
                "source_type": connection_info.source_type,
                "supports_sync": connection_info.supports_sync,
                "supports_live_queries": connection_info.supports_live_queries,
            },
        }
    except ValidationError as exc:
        return {
            "data_source": _serialize_data_source(source),
            "health": {
                "status": "error",
                "last_query_latency_ms": 0,
                "consecutive_failures": 0,
                "last_failure_at": None,
                "recommendation": exc.message,
            },
            "error_code": exc.code,
        }


@router.post("/data-sources/{source_id}/sync")
def sync_data_source(
    source_id: str,
    force_schema_refresh: bool = Query(default=False),
    prune_removed_fields: bool = Query(default=False),
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    source = _require_data_source(
        db=db,
        tenant_id=scope.tenant_id,
        source_id=source_id,
    )

    now = datetime.now(tz=UTC)
    try:
        connector = _build_connector_for_data_source(source)
        sync_result = connector.sync()
        discovered_schema = connector.discover_schema(
            force_refresh=force_schema_refresh
        )
        schema_refresh = _refresh_schema_fields(
            db=db,
            source=source,
            raw_schema=discovered_schema,
            prune_removed_fields=prune_removed_fields,
        )

        source.last_sync_at = now
        if sync_result.status in {"complete", "partial"}:
            if source.status not in {
                DataSourceStatus.paused,
                DataSourceStatus.disconnected,
            }:
                source.status = DataSourceStatus.connected
            source.sync_error_msg = None if not sync_result.errors else "; ".join(sync_result.errors[:3])
        else:
            source.status = DataSourceStatus.error
            source.sync_error_msg = "; ".join(sync_result.errors[:3]) or "Connector sync failed"

        db.add(source)
        db.commit()
        db.refresh(source)

        return {
            "data_source": _serialize_data_source(source),
            "sync_result": {
                "status": sync_result.status,
                "tables_discovered": sync_result.tables_discovered,
                "tables_added": sync_result.tables_added,
                "tables_removed": sync_result.tables_removed,
                "fields_changed": sync_result.fields_changed,
                "duration_ms": sync_result.duration_ms,
                "errors": list(sync_result.errors or []),
            },
            "schema_refresh": schema_refresh,
        }
    except ValidationError as exc:
        source.last_sync_at = now
        source.status = DataSourceStatus.error
        source.sync_error_msg = exc.message
        db.add(source)
        db.commit()
        db.refresh(source)
        return {
            "data_source": _serialize_data_source(source),
            "sync_result": {
                "status": "failed",
                "tables_discovered": 0,
                "tables_added": 0,
                "tables_removed": 0,
                "fields_changed": 0,
                "duration_ms": 0,
                "errors": [exc.message],
            },
            "schema_refresh": {
                "discovered_rows": 0,
                "added": 0,
                "updated": 0,
                "removed": 0,
                "total_fields": 0,
                "table_count": 0,
                "pii_fields": 0,
                "prune_removed_fields": prune_removed_fields,
            },
            "error_code": exc.code,
        }


@router.post("/data-sources/{source_id}/resync-schema")
def refresh_data_source_schema(
    source_id: str,
    force_refresh: bool = Query(default=True),
    prune_removed_fields: bool = Query(default=False),
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    source = _require_data_source(
        db=db,
        tenant_id=scope.tenant_id,
        source_id=source_id,
    )

    now = datetime.now(tz=UTC)
    try:
        connector = _build_connector_for_data_source(source)
        discovered_schema = connector.discover_schema(force_refresh=force_refresh)
        schema_refresh = _refresh_schema_fields(
            db=db,
            source=source,
            raw_schema=discovered_schema,
            prune_removed_fields=prune_removed_fields,
        )

        source.last_sync_at = now
        if source.status == DataSourceStatus.error:
            source.status = DataSourceStatus.connected
        source.sync_error_msg = None
        db.add(source)
        db.commit()
        db.refresh(source)

        return {
            "data_source": _serialize_data_source(source),
            "schema_refresh": schema_refresh,
        }
    except ValidationError as exc:
        source.last_sync_at = now
        source.status = DataSourceStatus.error
        source.sync_error_msg = exc.message
        db.add(source)
        db.commit()
        db.refresh(source)
        return {
            "data_source": _serialize_data_source(source),
            "schema_refresh": {
                "discovered_rows": 0,
                "added": 0,
                "updated": 0,
                "removed": 0,
                "total_fields": 0,
                "table_count": 0,
                "pii_fields": 0,
                "prune_removed_fields": prune_removed_fields,
            },
            "error_code": exc.code,
        }


@router.get("/data-sources/{source_id}/sync-history")
def get_data_source_sync_history(
    source_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    source = _require_data_source(
        db=db,
        tenant_id=scope.tenant_id,
        source_id=source_id,
    )

    schema_rows = db.scalars(
        select(SchemaField).where(
            SchemaField.tenant_id == scope.tenant_id,
            SchemaField.data_source_id == source.id,
        )
    ).all()

    by_table: dict[str, dict[str, object]] = {}
    for row in schema_rows:
        table_entry = by_table.setdefault(
            row.real_table,
            {
                "table": row.real_table,
                "field_count": 0,
                "pii_field_count": 0,
            },
        )
        table_entry["field_count"] = int(table_entry["field_count"]) + 1
        if row.pii_flag:
            table_entry["pii_field_count"] = int(table_entry["pii_field_count"]) + 1

    events: list[dict[str, object]] = [
        {
            "event": "data_source_created",
            "status": "completed",
            "at": source.created_at.isoformat(),
            "detail": "Data source created",
        }
    ]

    if source.last_sync_at is not None:
        events.append(
            {
                "event": "sync_failed"
                if source.status == DataSourceStatus.error
                else "sync_completed",
                "status": "failed" if source.status == DataSourceStatus.error else "completed",
                "at": source.last_sync_at.isoformat(),
                "detail": source.sync_error_msg or "Latest sync/refresh operation completed",
            }
        )

    events = sorted(events, key=lambda item: str(item["at"]), reverse=True)[:limit]

    return {
        "data_source": _serialize_data_source(source),
        "history_mode": "derived",
        "events": events,
        "schema_snapshot": {
            "total_fields": len(schema_rows),
            "table_count": len(by_table),
            "tables": sorted(by_table.values(), key=lambda item: str(item["table"])),
        },
    }


@router.post("/data-sources/{source_id}/disable")
def disable_data_source(
    source_id: str,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    source = _require_data_source(
        db=db,
        tenant_id=scope.tenant_id,
        source_id=source_id,
    )
    source.status = DataSourceStatus.paused
    db.add(source)
    db.commit()
    db.refresh(source)
    return _serialize_data_source(source)


@router.post("/data-sources/{source_id}/enable")
def enable_data_source(
    source_id: str,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    source = _require_data_source(
        db=db,
        tenant_id=scope.tenant_id,
        source_id=source_id,
    )
    source.status = DataSourceStatus.connected
    source.sync_error_msg = None
    db.add(source)
    db.commit()
    db.refresh(source)
    return _serialize_data_source(source)


@router.get("/data-sources/{source_id}/schema")
def data_source_schema(
    source_id: str,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(SchemaField).where(
            SchemaField.tenant_id == scope.tenant_id,
            SchemaField.data_source_id == source_id,
        )
    ).all()
    return [
        {
            "id": row.id,
            "real_table": row.real_table,
            "real_column": row.real_column,
            "alias_token": row.alias_token,
            "visibility": row.visibility.value,
            "pii_flag": row.pii_flag,
            "masked_for_personas": row.masked_for_personas,
        }
        for row in rows
    ]


@router.get("/audit-log")
def get_audit_log(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=500),
    user_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    blocked_only: bool = False,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    stmt = select(AuditLog).where(AuditLog.tenant_id == scope.tenant_id)

    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if blocked_only:
        stmt = stmt.where(AuditLog.was_blocked.is_(True))
    if start_date:
        stmt = stmt.where(AuditLog.created_at >= datetime.fromisoformat(start_date))
    if end_date:
        stmt = stmt.where(AuditLog.created_at <= datetime.fromisoformat(end_date))

    offset = (page - 1) * limit
    rows = db.scalars(
        stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    ).all()

    return {
        "page": page,
        "limit": limit,
        "items": [
            {
                "id": row.id,
                "user_id": row.user_id,
                "query_text": row.query_text,
                "intent_hash": row.intent_hash,
                "domains_accessed": row.domains_accessed,
                "was_blocked": row.was_blocked,
                "block_reason": row.block_reason,
                "response_summary": row.response_summary,
                "latency_ms": row.latency_ms,
                "created_at": row.created_at,
            }
            for row in rows
        ],
    }


@router.get("/audit-dashboard")
def get_audit_dashboard(
    window_hours: int = Query(default=24, ge=1, le=168),
    anomaly_limit: int = Query(default=20, ge=1, le=100),
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    return audit_dashboard_service.get_dashboard(
        db=db,
        scope=scope,
        window_hours=window_hours,
        anomaly_limit=anomaly_limit,
    )


@router.post("/security/kill")
def kill_sessions(
    payload: KillSwitchRequest,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    ttl_seconds = 10 * 60

    if payload.scope == "all":
        redis_client.client.setex(f"kill:tenant:{scope.tenant_id}", ttl_seconds, "1")
        return {"scope": "all", "sessions_revoked": "tenant-wide"}

    if payload.scope == "department":
        if not payload.target_id:
            raise ValidationError(
                message="target_id is required for department scope",
                code="TARGET_REQUIRED",
            )
        redis_client.client.setex(
            f"kill:tenant:{scope.tenant_id}:department:{payload.target_id}",
            ttl_seconds,
            "1",
        )
        return {
            "scope": "department",
            "target_id": payload.target_id,
            "sessions_revoked": "department-wide",
        }

    if payload.scope == "user":
        if not payload.target_id:
            raise ValidationError(
                message="target_id is required for user scope", code="TARGET_REQUIRED"
            )
        redis_client.client.setex(f"kill:user:{payload.target_id}", ttl_seconds, "1")
        return {"scope": "user", "target_id": payload.target_id, "sessions_revoked": 1}

    raise ValidationError(
        message="scope must be one of: all, department, user", code="INVALID_SCOPE"
    )


@router.post("/cache/clear")
def clear_intent_cache(
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    """Clear all cached intent templates for the tenant to force fresh template generation."""
    # Clear from Redis
    pattern = f"intent:{scope.tenant_id}:*"
    cursor = 0
    deleted_redis = 0
    while True:
        cursor, keys = redis_client.client.scan(cursor, match=pattern, count=100)
        if keys:
            redis_client.client.delete(*keys)
            deleted_redis += len(keys)
        if cursor == 0:
            break

    # Clear from database
    deleted_db = (
        db.query(IntentCacheEntry)
        .filter(IntentCacheEntry.tenant_id == scope.tenant_id)
        .delete()
    )
    db.commit()

    return {
        "cleared_redis": deleted_redis,
        "cleared_db": deleted_db,
        "message": "Intent cache cleared successfully. New queries will use fresh templates.",
    }
