import base64
import json
import uuid

import pytest

from app.connectors.sql_connector import SQLConnector
from app.compiler.service import compiler_service
from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    UnsafeOutputError,
    ValidationError,
)
from app.db.models import (
    ControlGraphEdge,
    ControlGraphNode,
    DataSource,
    DataSourceStatus,
    DataSourceType,
    DomainSourceBinding,
    PersonaType,
    PolicyProofArtifact,
    User,
    UserStatus,
)
from app.identity.service import identity_service
from app.interpreter.service import interpreter_service
from app.schemas.pipeline import ScopeContext
from app.services.pipeline import pipeline_service
from app.slm.output_guard import output_guard
from app.slm.simulator import slm_simulator
from app.tool_layer.service import tool_layer_service


def _scope_for(db_session, email: str) -> ScopeContext:
    token, _user, scope = identity_service.authenticate_google(db_session, f"mock:{email}")
    assert token
    return scope


def test_executive_enrollment_pipeline(db_session):
    """Test executive user querying seeded enrollment aggregate data."""
    scope = _scope_for(db_session, "executive@ipeds.local")
    result = pipeline_service.process_query(
        db=db_session, scope=scope, query_text="What is the total enrollment?"
    )

    assert result.was_blocked is False
    assert result.source == "ipeds_claims"
    assert "[SLOT_" not in result.response_text
    assert any(ch.isdigit() for ch in result.response_text)


def test_executive_demographics_pipeline(db_session):
    """Test executive user querying seeded institution demographics."""
    scope = _scope_for(db_session, "executive@ipeds.local")
    result = pipeline_service.process_query(
        db=db_session, scope=scope, query_text="How many HBCU institutions are there?"
    )

    assert result.was_blocked is False
    assert result.source == "ipeds_claims"
    assert "[SLOT_" not in result.response_text
    assert any(ch.isdigit() for ch in result.response_text)


def test_pipeline_persists_policy_proof_artifact(db_session):
    """Every successful query should emit at least one persisted policy proof."""
    scope = _scope_for(db_session, "executive@ipeds.local")
    result = pipeline_service.process_query(
        db=db_session,
        scope=scope,
        query_text="What is the total enrollment?",
    )

    assert result.was_blocked is False
    assert result.policy_proof_ids

    proof = db_session.get(PolicyProofArtifact, result.policy_proof_ids[0])
    assert proof is not None
    assert proof.tenant_id == scope.tenant_id
    assert proof.user_id == scope.user_id
    assert proof.intent_hash == result.intent_hash
    assert proof.proof_digest


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

    def counted_render(intent, local_scope, graph_context=None):
        called["count"] += 1
        return original(intent, local_scope, graph_context)

    monkeypatch.setattr(slm_simulator, "render_template", counted_render)

    pipeline_service.process_query(
        db=db_session, scope=scope, query_text="Show institution size distribution"
    )
    pipeline_service.process_query(
        db=db_session, scope=scope, query_text="Show institution size distribution"
    )

    assert called["count"] == 1


def test_intent_hash_is_persona_scoped(db_session):
    """Same prompt across personas should not share template cache keys."""
    student_scope = _scope_for(db_session, "student@ipeds.local")
    faculty_scope = _scope_for(db_session, "faculty@ipeds.local")

    student_output = interpreter_service.run(
        db_session,
        student_scope,
        "Show my academic summary",
    )
    faculty_output = interpreter_service.run(
        db_session,
        faculty_scope,
        "Show my academic summary",
    )

    assert student_output.intent_hash != faculty_output.intent_hash


def test_notices_query_plan_avoids_owner_row_scope(db_session):
    """Broadcast domains should not be constrained by owner/course row-scope filters."""
    scope = _scope_for(db_session, "student@ipeds.local")
    interpreted = interpreter_service.run(
        db_session,
        scope,
        "Show latest notices relevant to students",
    )

    assert interpreted.intent.domain == "notices"
    plan = compiler_service.compile_intent(scope, interpreted.intent)

    assert "owner_id" not in plan.filters
    assert "course_ids" not in plan.filters


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


def test_compiler_uses_domain_source_binding(db_session):
    """Test compiler resolves source type from tenant domain-source binding."""
    scope = _scope_for(db_session, "executive@ipeds.local")

    source = DataSource(
        tenant_id=scope.tenant_id,
        name="Campus Claims Source",
        source_type=DataSourceType.mock_claims,
        config_encrypted="e30=",
        department_scope=[],
        status=DataSourceStatus.connected,
    )
    db_session.add(source)
    db_session.flush()

    binding = db_session.query(DomainSourceBinding).filter(
        DomainSourceBinding.tenant_id == scope.tenant_id,
        DomainSourceBinding.domain == "campus",
    ).one_or_none()
    if binding is None:
        binding = DomainSourceBinding(
            tenant_id=scope.tenant_id,
            domain="campus",
            source_type=DataSourceType.mock_claims,
            data_source_id=source.id,
            is_active=True,
        )
    binding.source_type = DataSourceType.mock_claims
    binding.data_source_id = source.id
    binding.is_active = True
    db_session.add(binding)
    db_session.commit()

    interpreted = interpreter_service.run(db_session, scope, "Show total enrollment")
    plan = compiler_service.compile_intent(scope, interpreted.intent, db_session)

    assert plan.source_type == "mock_claims"
    assert plan.data_source_id == source.id


def test_compiler_prefers_graph_source_binding_when_graph_exists(db_session):
    """Compiler should resolve source from control graph metadata when available."""
    scope = _scope_for(db_session, "executive@ipeds.local")
    interpreted = interpreter_service.run(db_session, scope, "Show total enrollment")

    domain_node = ControlGraphNode(
        id=str(uuid.uuid4()),
        tenant_id=scope.tenant_id,
        node_type="domain",
        node_key=interpreted.intent.domain,
        label=interpreted.intent.domain,
        attributes={},
    )
    intent_node = ControlGraphNode(
        id=str(uuid.uuid4()),
        tenant_id=scope.tenant_id,
        node_type="intent",
        node_key=interpreted.intent.name,
        label=interpreted.intent.name,
        attributes={"slot_keys": list(interpreted.intent.slot_keys)},
    )
    source_type_node = ControlGraphNode(
        id=str(uuid.uuid4()),
        tenant_id=scope.tenant_id,
        node_type="source_type",
        node_key="mock_claims",
        label="mock_claims",
        attributes={},
    )
    db_session.add_all([domain_node, intent_node, source_type_node])
    db_session.flush()

    db_session.add_all(
        [
            ControlGraphEdge(
                id=str(uuid.uuid4()),
                tenant_id=scope.tenant_id,
                edge_type="intent_targets_domain",
                source_node_id=intent_node.id,
                target_node_id=domain_node.id,
                attributes={},
            ),
            ControlGraphEdge(
                id=str(uuid.uuid4()),
                tenant_id=scope.tenant_id,
                edge_type="domain_bound_to_source",
                source_node_id=domain_node.id,
                target_node_id=source_type_node.id,
                attributes={"is_active": True},
            ),
        ]
    )
    db_session.commit()

    plan = compiler_service.compile_intent(scope, interpreted.intent, db_session)

    assert plan.source_type == "mock_claims"
    assert plan.data_source_id is None


def test_compiler_rejects_slots_not_allowed_by_graph(db_session):
    """Compiler must fail closed when intent slots drift from graph metadata."""
    scope = _scope_for(db_session, "executive@ipeds.local")
    interpreted = interpreter_service.run(db_session, scope, "Show total enrollment")

    domain_node = ControlGraphNode(
        id=str(uuid.uuid4()),
        tenant_id=scope.tenant_id,
        node_type="domain",
        node_key=interpreted.intent.domain,
        label=interpreted.intent.domain,
        attributes={},
    )
    intent_node = ControlGraphNode(
        id=str(uuid.uuid4()),
        tenant_id=scope.tenant_id,
        node_type="intent",
        node_key=interpreted.intent.name,
        label=interpreted.intent.name,
        attributes={"slot_keys": ["graph_only_slot"]},
    )
    source_type_node = ControlGraphNode(
        id=str(uuid.uuid4()),
        tenant_id=scope.tenant_id,
        node_type="source_type",
        node_key="ipeds_claims",
        label="ipeds_claims",
        attributes={},
    )
    db_session.add_all([domain_node, intent_node, source_type_node])
    db_session.flush()

    db_session.add_all(
        [
            ControlGraphEdge(
                id=str(uuid.uuid4()),
                tenant_id=scope.tenant_id,
                edge_type="intent_targets_domain",
                source_node_id=intent_node.id,
                target_node_id=domain_node.id,
                attributes={},
            ),
            ControlGraphEdge(
                id=str(uuid.uuid4()),
                tenant_id=scope.tenant_id,
                edge_type="domain_bound_to_source",
                source_node_id=domain_node.id,
                target_node_id=source_type_node.id,
                attributes={"is_active": True},
            ),
        ]
    )
    db_session.commit()

    with pytest.raises(ValidationError) as exc:
        compiler_service.compile_intent(scope, interpreted.intent, db_session)

    assert exc.value.code == "GRAPH_SLOT_KEY_MISMATCH"


def test_tool_layer_requires_bound_source_for_external_type(db_session):
    """External source types must include a concrete data_source_id binding."""
    scope = _scope_for(db_session, "executive@ipeds.local")
    interpreted = interpreter_service.run(db_session, scope, "Show total enrollment")
    plan = compiler_service.compile_intent(scope, interpreted.intent, db_session)

    plan.source_type = "postgresql"
    plan.data_source_id = None

    with pytest.raises(ValidationError) as exc:
        tool_layer_service.execute(db_session, plan)

    assert exc.value.code == "PLAN_SOURCE_BINDING_INCOMPLETE"


def test_tool_layer_routes_postgresql_to_sql_connector(db_session, monkeypatch):
    """PostgreSQL route should construct SQLConnector and execute through it."""
    scope = _scope_for(db_session, "executive@ipeds.local")
    interpreted = interpreter_service.run(db_session, scope, "Show total enrollment")

    calls = {"connect": 0, "execute": 0}

    def fake_connect(self):
        calls["connect"] += 1

    def fake_execute_query(self, db, plan):
        calls["execute"] += 1
        return {"total_enrollment": 123}

    monkeypatch.setattr(SQLConnector, "connect", fake_connect)
    monkeypatch.setattr(SQLConnector, "execute_query", fake_execute_query)

    config_payload = {
        "connection_url": "postgresql://username:password@db.example.edu:5432/campus",
    }
    source = DataSource(
        tenant_id=scope.tenant_id,
        name="Campus SQL",
        source_type=DataSourceType.postgresql,
        config_encrypted=base64.b64encode(
            json.dumps(config_payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
        ).decode("utf-8"),
        department_scope=[],
        status=DataSourceStatus.connected,
    )
    db_session.add(source)
    db_session.flush()

    plan = compiler_service.compile_intent(scope, interpreted.intent, db_session)
    plan.source_type = "postgresql"
    plan.data_source_id = source.id

    values = tool_layer_service.execute(db_session, plan)

    assert calls["connect"] == 1
    assert calls["execute"] == 1
    assert values["total_enrollment"] == 123


def test_tool_layer_routes_mysql_to_sql_connector(db_session, monkeypatch):
    """MySQL route should construct SQLConnector and execute through it."""
    scope = _scope_for(db_session, "executive@ipeds.local")
    interpreted = interpreter_service.run(db_session, scope, "Show total enrollment")

    calls = {"connect": 0, "execute": 0}

    def fake_connect(self):
        calls["connect"] += 1

    def fake_execute_query(self, db, plan):
        calls["execute"] += 1
        return {"total_enrollment": 321}

    monkeypatch.setattr(SQLConnector, "connect", fake_connect)
    monkeypatch.setattr(SQLConnector, "execute_query", fake_execute_query)

    config_payload = {
        "connection_url": "mysql+pymysql://username:password@db.example.edu:3306/campus",
    }
    source = DataSource(
        tenant_id=scope.tenant_id,
        name="Campus MySQL",
        source_type=DataSourceType.mysql,
        config_encrypted=base64.b64encode(
            json.dumps(config_payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
        ).decode("utf-8"),
        department_scope=[],
        status=DataSourceStatus.connected,
    )
    db_session.add(source)
    db_session.flush()

    plan = compiler_service.compile_intent(scope, interpreted.intent, db_session)
    plan.source_type = "mysql"
    plan.data_source_id = source.id

    values = tool_layer_service.execute(db_session, plan)

    assert calls["connect"] == 1
    assert calls["execute"] == 1
    assert values["total_enrollment"] == 321


def test_interpreter_fails_closed_for_undetermined_domain(db_session):
    """Interpreter should fail closed instead of defaulting to a hardcoded domain."""
    scope = _scope_for(db_session, "executive@ipeds.local")

    with pytest.raises(ValidationError) as exc:
        interpreter_service.run(db_session, scope, "qwerty non domain signal")

    assert exc.value.code == "DOMAIN_UNDETERMINED"


def test_identity_requires_role_policy_configuration(db_session):
    """Auth should fail when no active role policy exists for the resolved role candidates."""
    scope = _scope_for(db_session, "executive@ipeds.local")
    user = User(
        id=str(uuid.uuid4()),
        tenant_id=scope.tenant_id,
        email="orphan-role@ipeds.local",
        name="Orphan Role",
        persona_type=PersonaType.admin_staff,
        department="Admissions",
        external_id="ORPHAN-001",
        admin_function="mystery",
        course_ids=[],
        masked_fields=[],
        status=UserStatus.active,
    )
    db_session.add(user)
    db_session.commit()

    with pytest.raises(AuthenticationError) as exc:
        identity_service.authenticate_google(db_session, "mock:orphan-role@ipeds.local")

    assert exc.value.code == "ROLE_POLICY_NOT_CONFIGURED"


def test_student_gpa_query_prefers_grade_intent(db_session):
    """A GPA-focused student query should map to the grade summary intent."""
    scope = _scope_for(db_session, "student@ipeds.local")
    interpreted = interpreter_service.run(
        db_session,
        scope,
        "Show my current GPA and passed subjects.",
    )

    assert interpreted.intent.domain == "academic"
    assert interpreted.intent.entity_type == "grade_summary"
    assert interpreted.intent.name == "student_grades"


def test_student_academic_summary_does_not_default_to_campus(db_session):
    """Personal academic summary wording should remain in student academic scope."""
    scope = _scope_for(db_session, "student@ipeds.local")
    interpreted = interpreter_service.run(
        db_session,
        scope,
        "Give me a short summary of my academics",
    )

    assert interpreted.intent.domain == "academic"


def test_faculty_dashboard_summary_uses_academic_fallback(db_session):
    """Faculty summary/dashboard prompts should avoid accidental campus routing."""
    scope = _scope_for(db_session, "faculty@ipeds.local")
    interpreted = interpreter_service.run(
        db_session,
        scope,
        "Give me a quick faculty dashboard summary.",
    )

    assert interpreted.intent.domain == "academic"


def test_student_combined_academic_and_finance_query_merges_domains(db_session):
    """Student prompts that explicitly combine academics and fee context should return both domains."""
    scope = _scope_for(db_session, "student@ipeds.local")
    result = pipeline_service.process_query(
        db=db_session,
        scope=scope,
        query_text="Give me a summary of my academics and fee status.",
    )

    assert result.was_blocked is False
    assert result.source == "multi_domain"
    assert set(result.domains_accessed) == {"academic", "finance"}
    assert "Academic:" in result.response_text
    assert "Finance:" in result.response_text


def test_faculty_combined_hr_and_notices_query_merges_domains(db_session):
    """Faculty prompts that combine HR and notices should return both scoped summaries."""
    scope = _scope_for(db_session, "faculty@ipeds.local")
    result = pipeline_service.process_query(
        db=db_session,
        scope=scope,
        query_text="Show my leave status and latest notices.",
    )

    assert result.was_blocked is False
    assert result.source == "multi_domain"
    assert set(result.domains_accessed) == {"hr", "notices"}
    assert "Hr:" in result.response_text
    assert "Notices:" in result.response_text


def test_faculty_course_query_mentions_course_scope(db_session):
    """Faculty course prompts should surface which course IDs are in scope."""
    scope = _scope_for(db_session, "faculty@ipeds.local")
    assert scope.course_ids

    result = pipeline_service.process_query(
        db=db_session,
        scope=scope,
        query_text="How many courses am I handling right now?",
    )

    assert result.was_blocked is False
    assert any(course_id in result.response_text for course_id in scope.course_ids)
