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


def test_student_attendance_pipeline(db_session):
    scope = _scope_for(db_session, "student@campusa.edu")
    result = pipeline_service.process_query(db=db_session, scope=scope, query_text="What is my attendance percentage this semester?")

    assert result.was_blocked is False
    assert "attendance" in result.response_text.lower()
    assert "78.4" in result.response_text


def test_student_cross_user_block(db_session):
    scope = _scope_for(db_session, "student@campusa.edu")

    with pytest.raises(AuthorizationError) as exc:
        pipeline_service.process_query(db=db_session, scope=scope, query_text="Show attendance for STU-9001")

    assert exc.value.code == "STUDENT_SCOPE_BLOCKED"


def test_it_head_chat_blocked(db_session):
    scope = _scope_for(db_session, "it.head@campusa.edu")

    with pytest.raises(AuthorizationError) as exc:
        pipeline_service.process_query(db=db_session, scope=scope, query_text="Show student attendance")

    assert exc.value.code == "IT_HEAD_CHAT_BLOCKED"


def test_intent_cache_skips_second_slm_call(db_session, monkeypatch):
    scope = _scope_for(db_session, "student@campusa.edu")

    called = {"count": 0}
    original = slm_simulator.render_template

    def counted_render(intent, local_scope):
        called["count"] += 1
        return original(intent, local_scope)

    monkeypatch.setattr(slm_simulator, "render_template", counted_render)

    pipeline_service.process_query(db=db_session, scope=scope, query_text="Show my current GPA")
    pipeline_service.process_query(db=db_session, scope=scope, query_text="Show my current GPA")

    assert called["count"] == 1


def test_output_guard_blocks_raw_value_leak():
    with pytest.raises(UnsafeOutputError) as exc:
        output_guard.validate("Your attendance is 78.4%.", real_identifiers=[])

    assert exc.value.code == "RAW_VALUE_LEAK"


def test_compiler_injects_faculty_course_scope(db_session):
    scope = _scope_for(db_session, "faculty@campusa.edu")
    interpreted = interpreter_service.run(db_session, scope, "Show attendance for my courses")
    plan = compiler_service.compile_intent(scope, interpreted.intent)

    assert "course_ids" in plan.filters
    assert plan.filters["course_ids"] == ["CSE101", "CSE102"]
