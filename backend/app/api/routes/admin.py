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
from app.db.models import AuditLog, DataSource, DataSourceStatus, DataSourceType, IntentCacheEntry, PersonaType, SchemaField, User, UserStatus
from app.db.session import get_db
from app.schemas.admin import DataSourceCreateRequest, KillSwitchRequest, UserUpdateRequest
from app.schemas.pipeline import ScopeContext

router = APIRouter(prefix="/admin", tags=["admin"])


def require_it_head(scope: ScopeContext = Depends(get_current_scope)) -> ScopeContext:
    if scope.persona_type != "it_head":
        raise AuthorizationError(message="Only IT Head can access admin endpoints", code="ADMIN_ONLY")
    return scope


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

            existing = db.scalar(select(User).where(User.tenant_id == scope.tenant_id, User.email == email))
            if existing:
                continue

            persona = (row.get("persona_type") or "student").strip().lower()
            department = (row.get("department") or None)
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
                course_ids=[c.strip() for c in (row.get("course_ids") or "").split(";") if c.strip()],
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
    user = db.scalar(select(User).where(User.id == user_id, User.tenant_id == scope.tenant_id))
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


@router.get("/data-sources")
def list_data_sources(scope: ScopeContext = Depends(require_it_head), db: Session = Depends(get_db)):
    rows = db.scalars(select(DataSource).where(DataSource.tenant_id == scope.tenant_id)).all()
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
    encoded_config = base64.b64encode(json.dumps(payload.config, ensure_ascii=True, sort_keys=True).encode("utf-8")).decode("utf-8")
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
def data_source_schema(source_id: str, scope: ScopeContext = Depends(require_it_head), db: Session = Depends(get_db)):
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
    rows = db.scalars(stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)).all()

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
            raise ValidationError(message="target_id is required for department scope", code="TARGET_REQUIRED")
        redis_client.client.setex(f"kill:tenant:{scope.tenant_id}:department:{payload.target_id}", ttl_seconds, "1")
        return {"scope": "department", "target_id": payload.target_id, "sessions_revoked": "department-wide"}

    if payload.scope == "user":
        if not payload.target_id:
            raise ValidationError(message="target_id is required for user scope", code="TARGET_REQUIRED")
        redis_client.client.setex(f"kill:user:{payload.target_id}", ttl_seconds, "1")
        return {"scope": "user", "target_id": payload.target_id, "sessions_revoked": 1}

    raise ValidationError(message="scope must be one of: all, department, user", code="INVALID_SCOPE")


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
    deleted_db = db.query(IntentCacheEntry).filter(
        IntentCacheEntry.tenant_id == scope.tenant_id
    ).delete()
    db.commit()

    return {
        "cleared_redis": deleted_redis,
        "cleared_db": deleted_db,
        "message": "Intent cache cleared successfully. New queries will use fresh templates.",
    }

