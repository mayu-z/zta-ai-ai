from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.agentic.models.agent_context import AgentStatus, ClaimSet, IntentClassification, RequestContext
from app.agentic.models.agent_definition import AgentDefinition, ExecutionContext


def _definition_payload() -> dict:
    return {
        "agent_id": "test_agent_v1",
        "display_name": "Test Agent",
        "version": "1.0.0",
        "description": "test definition",
        "trigger": {"type": "user_query", "config": {}},
        "permissions": {
            "allowed_personas": ["student"],
            "requires_confirmation": False,
            "human_approval_required": False,
            "approval_level": None,
        },
        "data_scope": {
            "required": ["fees.own"],
            "has_sensitive_fields": False,
            "cache_results": True,
        },
        "nodes": [
            {
                "node_id": "fetch_fees",
                "type": "fetch",
                "config": {"entity": "fees"},
                "output_key": "fees_data",
            },
            {
                "node_id": "check_has_fees",
                "type": "condition",
                "config": {"expression": "fees_data.row_count > 0"},
            },
        ],
        "edges": [
            {"from": "START", "to": "fetch_fees"},
            {"from": "fetch_fees", "to": "check_has_fees"},
            {"from": "check_has_fees", "to": "END_SUCCESS", "condition": "true"},
            {"from": "check_has_fees", "to": "END_NO_FEES", "condition": "false"},
        ],
        "config": {},
        "audit": {"log_fields": [], "hash_fields": [], "retention_days": 365},
        "metadata": {
            "created_at": "2026-04-15",
            "created_by": "engineering",
            "tenant_overridable_fields": [],
        },
    }


def _execution_context() -> ExecutionContext:
    tenant_id = uuid4()
    definition = AgentDefinition.model_validate(_definition_payload())
    intent = IntentClassification(
        is_agentic=True,
        action_id="test_agent_v1",
        confidence=0.9,
        extracted_entities={},
        raw_intent_text="check fees",
    )
    request_ctx = RequestContext(
        tenant_id=tenant_id,
        user_alias="STU-100",
        session_id="sid-123",
        persona="student",
        department_id="CSE",
        jwt_claims={"tenant_id": str(tenant_id)},
    )
    claim_set = ClaimSet(
        claims={"outstanding_balance": 1200},
        field_classifications={"outstanding_balance": "GENERAL"},
        source_alias="fees",
        fetched_at=datetime.now(UTC).replace(tzinfo=None),
        row_count=1,
    )
    return ExecutionContext(
        intent=intent,
        ctx=request_ctx,
        definition=definition,
        claim_sets={"fees_data": claim_set},
        computed_values={"trigger_context": {"stage": "overdue"}},
    )


def test_agent_definition_valid_and_resolve_next() -> None:
    definition = AgentDefinition.model_validate(_definition_payload())
    assert definition.resolve_next("check_has_fees", True) == "END_SUCCESS"
    assert definition.resolve_next("check_has_fees", False) == "END_NO_FEES"


def test_agent_definition_rejects_duplicate_node_ids() -> None:
    payload = _definition_payload()
    payload["nodes"].append(
        {
            "node_id": "fetch_fees",
            "type": "fetch",
            "config": {"entity": "fees"},
        }
    )
    with pytest.raises(ValueError, match="Duplicate node IDs"):
        AgentDefinition.model_validate(payload)


def test_agent_definition_rejects_unknown_edge_reference() -> None:
    payload = _definition_payload()
    payload["edges"][0] = {"from": "START", "to": "missing_node"}
    with pytest.raises(ValueError, match="Edge references unknown node"):
        AgentDefinition.model_validate(payload)


def test_agent_definition_rejects_cycles() -> None:
    payload = _definition_payload()
    payload["nodes"] = [
        {"node_id": "n1", "type": "fetch", "config": {}},
        {"node_id": "n2", "type": "compute", "config": {}},
    ]
    payload["edges"] = [
        {"from": "START", "to": "n1"},
        {"from": "n1", "to": "n2"},
        {"from": "n2", "to": "n1"},
        {"from": "n2", "to": "END"},
    ]
    with pytest.raises(ValueError, match="Circular graph references"):
        AgentDefinition.model_validate(payload)


def test_execution_context_resolve_and_build_result() -> None:
    exec_ctx = _execution_context()

    assert exec_ctx.resolve("{{fees_data.claims.outstanding_balance}}") == 1200
    assert exec_ctx.resolve("{{ctx.user_alias}}") == "STU-100"
    assert exec_ctx.resolve("stage={{trigger_context.stage}}") == "stage=overdue"

    exec_ctx.store("_final_status", "SUCCESS")
    exec_ctx.store("_final_message", "completed")
    exec_ctx.store("_result_data", {"ok": True})

    result = exec_ctx.build_result()
    assert result.status == AgentStatus.SUCCESS
    assert result.message == "completed"
    assert result.data == {"ok": True}
