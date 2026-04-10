from __future__ import annotations

import base64
import csv
import io
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_scope
from app.core.exceptions import AuthorizationError, ValidationError
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
    PersonaType,
    RolePolicy,
    SchemaField,
    User,
    UserStatus,
)
from app.db.session import get_db
from app.schemas.admin import (
    DataSourceCreateRequest,
    DomainSourceBindingUpsertRequest,
    DomainKeywordUpsertRequest,
    IntentDefinitionUpsertRequest,
    IntentDetectionKeywordUpsertRequest,
    KillSwitchRequest,
    RolePolicyUpsertRequest,
    UserUpdateRequest,
)
from app.schemas.pipeline import ScopeContext

router = APIRouter(prefix="/admin", tags=["admin"])

VALID_ROW_SCOPE_MODES = {None, "owner_id", "course_ids", "department_id", "admin_function"}


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
        IntentDetectionKeyword.tenant_id == scope.tenant_id
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
        raise ValidationError(
            message="priority must be >= 0",
            code="INVALID_PRIORITY",
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
        raise ValidationError(
            message="Intent detection keyword not found",
            code="KEYWORD_NOT_FOUND",
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
    return [
        {
            "id": row.id,
            "name": row.name,
            "source_type": row.source_type.value,
            "status": row.status.value,
            "last_sync_at": row.last_sync_at,
        }
        for row in rows
    ]


@router.post("/data-sources")
def create_data_source(
    payload: DataSourceCreateRequest,
    scope: ScopeContext = Depends(require_it_head),
    db: Session = Depends(get_db),
):
    encoded_config = base64.b64encode(
        json.dumps(payload.config, ensure_ascii=True, sort_keys=True).encode("utf-8")
    ).decode("utf-8")
    source = DataSource(
        tenant_id=scope.tenant_id,
        name=payload.name,
        source_type=DataSourceType(payload.source_type),
        config_encrypted=encoded_config,
        department_scope=payload.department_scope,
        status=DataSourceStatus.connected,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return {
        "id": source.id,
        "name": source.name,
        "source_type": source.source_type.value,
        "status": source.status.value,
    }


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
