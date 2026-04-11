from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.compiler.query_builder import QueryBuilder
from app.core.exceptions import ValidationError
from app.interpreter.intent_extractor import IntentRule, extract_intent
from app.interpreter.registry import derive_domain_keywords_from_intent_rules
from app.interpreter.service import InterpreterService
from app.schemas.pipeline import InterpretedIntent, ScopeContext


def _scope(*, tenant_id: str, allowed_domains: list[str]) -> ScopeContext:
    return ScopeContext(
        tenant_id=tenant_id,
        user_id="user-1",
        email="user@example.com",
        name="User",
        persona_type="student",
        external_id="STU-0001",
        session_id="session-1",
        allowed_domains=allowed_domains,
        row_scope_filters={},
    )


def test_detection_keywords_drive_intent_selection() -> None:
    rules = (
        IntentRule(
            name="attendance_intent",
            domain="academic",
            entity_type="attendance_summary",
            slot_keys=("attendance_percentage",),
            keywords=("subject", "summary"),
            persona_types=("student",),
            priority=20,
        ),
        IntentRule(
            name="grade_intent",
            domain="academic",
            entity_type="grade_summary",
            slot_keys=("gpa",),
            keywords=("subject", "summary"),
            persona_types=("student",),
            priority=20,
        ),
    )

    detection_keywords = {
        "grade_intent": {
            "grade_marker": ["gpa", "grade", "marks"],
        }
    }

    intent = extract_intent(
        raw_prompt="Show my grade summary and GPA",
        sanitized_prompt="Show my grade summary and GPA",
        aliased_prompt="Show my grade summary and GPA",
        detected_domains=["academic"],
        persona_type="student",
        intent_rules=rules,
        detection_keywords=detection_keywords,
    )

    assert intent.name == "grade_intent"
    assert intent.entity_type == "grade_summary"


def test_summary_fallback_uses_allowed_domains_not_persona_defaults() -> None:
    service = InterpreterService()
    scope = _scope(tenant_id="tenant-a", allowed_domains=["finance", "notices"])

    fallback = service._fallback_domain_for_undetermined(
        "Give me a summary",
        scope,
    )

    assert fallback == "finance"


def test_query_builder_uses_configured_default_source(monkeypatch: pytest.MonkeyPatch) -> None:
    builder = QueryBuilder()
    monkeypatch.setattr(
        "app.compiler.query_builder._get_settings",
        lambda: SimpleNamespace(default_local_source_type="mock_claims"),
    )

    scope_a = _scope(tenant_id="tenant-a", allowed_domains=["academic"])
    scope_b = _scope(tenant_id="tenant-b", allowed_domains=["academic"])
    intent = InterpretedIntent(
        name="student_attendance",
        domain="academic",
        entity_type="attendance_summary",
        raw_prompt="attendance",
        sanitized_prompt="attendance",
        aliased_prompt="attendance",
        slot_keys=["attendance_percentage"],
    )

    plan_a = builder.build(scope_a, intent, db=None)
    plan_b = builder.build(scope_b, intent, db=None)

    assert plan_a.source_type == "mock_claims"
    assert plan_b.source_type == "mock_claims"


def test_query_builder_rejects_invalid_default_source(monkeypatch: pytest.MonkeyPatch) -> None:
    builder = QueryBuilder()
    monkeypatch.setattr(
        "app.compiler.query_builder._get_settings",
        lambda: SimpleNamespace(default_local_source_type="unsupported"),
    )

    scope = _scope(tenant_id="tenant-a", allowed_domains=["academic"])
    intent = InterpretedIntent(
        name="student_attendance",
        domain="academic",
        entity_type="attendance_summary",
        raw_prompt="attendance",
        sanitized_prompt="attendance",
        aliased_prompt="attendance",
        slot_keys=["attendance_percentage"],
    )

    with pytest.raises(ValidationError) as exc:
        builder.build(scope, intent, db=None)

    assert exc.value.code == "DEFAULT_SOURCE_TYPE_INVALID"


def test_derive_domain_keywords_from_intent_rules_builds_domain_tokens() -> None:
    rules = (
        IntentRule(
            name="finance_invoice_summary",
            domain="finance",
            entity_type="invoice_status",
            slot_keys=("invoice_count",),
            keywords=("invoice", "payable"),
        ),
        IntentRule(
            name="hr_leave_balance",
            domain="hr",
            entity_type="leave_status",
            slot_keys=("leave_days",),
            keywords=("leave", "payroll"),
        ),
    )

    derived = derive_domain_keywords_from_intent_rules(rules)

    assert "finance" in derived
    assert "invoice" in derived["finance"]
    assert "payable" in derived["finance"]
    assert "hr" in derived
    assert "leave" in derived["hr"]
    assert "payroll" in derived["hr"]


def test_interpreter_uses_derived_domain_keywords_when_config_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = InterpreterService()
    scope = _scope(tenant_id="tenant-a", allowed_domains=["finance"])
    rules = (
        IntentRule(
            name="finance_invoice_summary",
            domain="finance",
            entity_type="invoice_summary",
            slot_keys=("invoice_count",),
            keywords=("invoice", "payable"),
            persona_types=("student",),
            is_default=True,
        ),
    )

    def _missing_domain_keywords(_db, _tenant_id):
        raise ValidationError(
            message="No active domain keyword configuration is available for this tenant",
            code="DOMAIN_KEYWORDS_NOT_CONFIGURED",
        )

    monkeypatch.setattr("app.interpreter.service.load_intent_rules", lambda _db, _tenant_id: rules)
    monkeypatch.setattr("app.interpreter.service.load_intent_detection_keywords", lambda _db, _tenant_id: {})
    monkeypatch.setattr("app.interpreter.service.load_domain_keywords", _missing_domain_keywords)
    monkeypatch.setattr("app.interpreter.service.apply_schema_aliasing", lambda _db, _tenant_id, prompt: (prompt, []))
    monkeypatch.setattr("app.interpreter.service.intent_cache_service.get", lambda _db, _tenant_id, _intent_hash: None)

    output = service.run(db=None, scope=scope, prompt="show invoice payable aging")

    assert output.intent.domain == "finance"
    assert output.intent.name == "finance_invoice_summary"
