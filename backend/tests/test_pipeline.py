import pytest

from app.compiler.service import compiler_service
from app.core.exceptions import AuthorizationError, UnsafeOutputError
from app.identity.service import identity_service
from app.interpreter.service import interpreter_service
from app.schemas.pipeline import ScopeContext
from app.services.pipeline import pipeline_service
from app.slm.output_guard import output_guard
from app.slm.simulator import slm_simulator


def _scope_for(db_session, email: str) -> ScopeContext:
    token, _user, scope = identity_service.authenticate_google(db_session, f"mock:{email}")
    assert token
    return scope


def test_executive_enrollment_pipeline(db_session):
    """Test executive user querying IPEDS enrollment data."""
    scope = _scope_for(db_session, "executive@ipeds.local")
    result = pipeline_service.process_query(
        db=db_session, scope=scope, query_text="What is the total enrollment?"
    )

    assert result.was_blocked is False
    assert result.source == "ipeds_claims"
    # IPEDS has 5826 institutions with ~2.7M total enrollment
    assert "5,826" in result.response_text or "5826" in result.response_text


def test_executive_demographics_pipeline(db_session):
    """Test executive user querying IPEDS institution demographics."""
    scope = _scope_for(db_session, "executive@ipeds.local")
    result = pipeline_service.process_query(
        db=db_session, scope=scope, query_text="How many HBCU institutions are there?"
    )

    assert result.was_blocked is False
    assert result.source == "ipeds_claims"
    # IPEDS has 101 HBCU institutions
    assert "101" in result.response_text


def test_it_head_chat_blocked(db_session):
    """Test IT head is blocked from using chat (admin dashboard only)."""
    scope = _scope_for(db_session, "ithead@ipeds.local")

    with pytest.raises(AuthorizationError) as exc:
        pipeline_service.process_query(
            db=db_session, scope=scope, query_text="Show enrollment data"
        )

    assert exc.value.code == "IT_HEAD_CHAT_BLOCKED"


def test_intent_cache_skips_second_slm_call(db_session, monkeypatch):
    """Test that cached intents don't call SLM again."""
    scope = _scope_for(db_session, "executive@ipeds.local")

    called = {"count": 0}
    original = slm_simulator.render_template

    def counted_render(intent, local_scope):
        called["count"] += 1
        return original(intent, local_scope)

    monkeypatch.setattr(slm_simulator, "render_template", counted_render)

    pipeline_service.process_query(
        db=db_session, scope=scope, query_text="Show institution size distribution"
    )
    pipeline_service.process_query(
        db=db_session, scope=scope, query_text="Show institution size distribution"
    )

    assert called["count"] == 1


def test_output_guard_blocks_raw_value_leak():
    """Test output guard blocks templates with raw numeric values."""
    with pytest.raises(UnsafeOutputError) as exc:
        output_guard.validate("Total enrollment is 2740898.", real_identifiers=[])

    assert exc.value.code == "RAW_VALUE_LEAK"


def test_admissions_staff_query(db_session):
    """Test admissions staff querying admissions data."""
    scope = _scope_for(db_session, "admissions@ipeds.local")
    result = pipeline_service.process_query(
        db=db_session, scope=scope, query_text="Show admissions statistics"
    )

    assert result.was_blocked is False
    assert result.source == "ipeds_claims"


def test_compiler_injects_aggregate_scope(db_session):
    """Test compiler enforces aggregate-only for executive users."""
    scope = _scope_for(db_session, "executive@ipeds.local")
    interpreted = interpreter_service.run(db_session, scope, "Show total enrollment")
    plan = compiler_service.compile_intent(scope, interpreted.intent)

    assert plan.requires_aggregate is True
    assert plan.filters.get("aggregate_only") is True


def test_executive_finance_query_blocked(db_session):
    """Test executive is blocked from accessing transactional finance data."""
    scope = _scope_for(db_session, "executive@ipeds.local")

    with pytest.raises(AuthorizationError) as exc:
        pipeline_service.process_query(
            db=db_session, scope=scope, query_text="Show finance records summary."
        )

    assert exc.value.code == "DOMAIN_FORBIDDEN"
    assert "finance" in exc.value.message.lower()


def test_admissions_cross_domain_blocked(db_session):
    """Test admissions staff is blocked from accessing campus aggregate data."""
    scope = _scope_for(db_session, "admissions@ipeds.local")

    with pytest.raises(AuthorizationError) as exc:
        pipeline_service.process_query(
            db=db_session, scope=scope, query_text="Give me campus aggregate KPI summary."
        )

    assert exc.value.code == "DOMAIN_FORBIDDEN"
    assert "campus" in exc.value.message.lower()
