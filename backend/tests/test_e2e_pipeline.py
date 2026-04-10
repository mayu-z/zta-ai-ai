from __future__ import annotations

import uuid

import pytest
from sqlalchemy import desc, select

from app.core.exceptions import AuthorizationError
from app.db.models import AuditLog, PersonaType, User, UserStatus
from app.schemas.pipeline import ScopeContext
from app.services.pipeline import pipeline_service
from scripts.ipeds_import import IPEDS_TENANT_ID


def _scope_for(db_session, email: str) -> ScopeContext:
    from app.identity.service import identity_service

    token, _user, scope = identity_service.authenticate_google(db_session, f"mock:{email}")
    assert token
    return scope


def _latest_audit_for_query(db_session, query_text: str) -> AuditLog | None:
    stmt = (
        select(AuditLog)
        .where(AuditLog.query_text == query_text)
        .order_by(desc(AuditLog.created_at))
    )
    return db_session.scalar(stmt)


def _ensure_student_scope(db_session, email: str) -> ScopeContext:
    user = db_session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            id=str(uuid.uuid4()),
            tenant_id=IPEDS_TENANT_ID,
            email=email,
            name="Student Test",
            persona_type=PersonaType.student,
            department="Academic",
            external_id="STU-001",
            admin_function=None,
            course_ids=[],
            masked_fields=[],
            status=UserStatus.active,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

    return ScopeContext(
        tenant_id=user.tenant_id,
        user_id=user.id,
        email=user.email,
        name=user.name,
        persona_type=user.persona_type.value,
        department=user.department,
        external_id=user.external_id,
        admin_function=user.admin_function,
        course_ids=user.course_ids,
        allowed_domains=["academic"],
        denied_domains=[],
        masked_fields=user.masked_fields,
        aggregate_only=False,
        own_id=user.external_id,
        chat_enabled=True,
        session_id=f"sid-{user.id[:8]}",
        session_ip="127.0.0.1",
        device_trusted=True,
        mfa_verified=True,
    )


def test_e2e_pipeline_latency_flag_and_audit(db_session):
    """Verify successful pipeline run writes audit with latency_flag."""
    scope = _scope_for(db_session, "executive@ipeds.local")
    query_text = "give me enrollment overview"

    result = pipeline_service.process_query(db=db_session, scope=scope, query_text=query_text)

    assert result.was_blocked is False
    assert result.response_text

    audit_row = _latest_audit_for_query(db_session, query_text)
    assert audit_row is not None
    assert audit_row.latency_flag is not None
    assert audit_row.latency_flag in {"high", "suspicious", "normal"}
    print(f"Latency: {audit_row.latency_ms}ms - Flag: {audit_row.latency_flag}")


def test_conversational_query_is_audited(db_session):
    scope = _scope_for(db_session, "admissions@ipeds.local")
    query_text = "hello"

    result = pipeline_service.process_query(db=db_session, scope=scope, query_text=query_text)

    assert result.source == "conversational"
    assert result.response_text
    assert result.was_blocked is False

    audit_row = _latest_audit_for_query(db_session, query_text)
    assert audit_row is not None
    assert audit_row.was_blocked is False
    assert audit_row.latency_flag in {"high", "suspicious", "normal"}


def test_blocked_query_is_audited(db_session):
    scope = _ensure_student_scope(db_session, "student@ipeds.local")
    query_text = "show me salary records"

    with pytest.raises(AuthorizationError) as exc:
        pipeline_service.process_query(db=db_session, scope=scope, query_text=query_text)

    assert exc.value.code == "DOMAIN_FORBIDDEN"

    audit_row = _latest_audit_for_query(db_session, query_text)
    assert audit_row is not None
    assert audit_row.was_blocked is True
    assert audit_row.block_reason == "DOMAIN_FORBIDDEN"
    assert audit_row.latency_flag in {"high", "suspicious", "normal"}
