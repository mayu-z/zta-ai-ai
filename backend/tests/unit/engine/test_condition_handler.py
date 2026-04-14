from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.agentic.engine.node_types.condition_handler import ConditionNodeHandler, UnsafeExpression, safe_eval
from app.agentic.models.agent_context import ClaimSet, IntentClassification, RequestContext
from app.agentic.models.agent_definition import AgentDefinition, ExecutionContext, NodeDefinition, NodeTypeEnum


def _definition() -> AgentDefinition:
    return AgentDefinition.model_validate(
        {
            "agent_id": "cond_test_v1",
            "display_name": "Condition Test",
            "version": "1.0.0",
            "description": "condition test",
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
                    "node_id": "check",
                    "type": "condition",
                    "config": {"expression": "fees_data.row_count > 0"},
                }
            ],
            "edges": [
                {"from": "START", "to": "check"},
                {"from": "check", "to": "END_SUCCESS", "condition": "true"},
                {"from": "check", "to": "END_NO_DATA", "condition": "false"},
            ],
            "config": {},
            "audit": {"log_fields": [], "hash_fields": [], "retention_days": 365},
            "metadata": {
                "created_at": "2026-04-15",
                "created_by": "engineering",
                "tenant_overridable_fields": [],
            },
        }
    )


def _exec_ctx(row_count: int = 1) -> ExecutionContext:
    tenant_id = uuid4()
    claim_set = ClaimSet(
        claims={"outstanding_balance": 1000},
        field_classifications={"outstanding_balance": "GENERAL"},
        source_alias="fees",
        fetched_at=datetime.now(UTC).replace(tzinfo=None),
        row_count=row_count,
    )
    return ExecutionContext(
        intent=IntentClassification(
            is_agentic=True,
            action_id="cond_test_v1",
            confidence=0.9,
            extracted_entities={},
            raw_intent_text="fees",
        ),
        ctx=RequestContext(
            tenant_id=tenant_id,
            user_alias="STU-42",
            session_id="sid-42",
            persona="student",
            department_id="CSE",
            jwt_claims={"tenant_id": str(tenant_id)},
        ),
        definition=_definition(),
        claim_sets={"fees_data": claim_set},
        computed_values={"cache_key": "cache:test:missing"},
    )


@pytest.mark.asyncio
async def test_condition_handler_evaluates_row_count_expression() -> None:
    handler = ConditionNodeHandler()
    node = NodeDefinition(
        node_id="check",
        type=NodeTypeEnum.CONDITION,
        config={"expression": "fees_data.row_count > 0"},
    )

    result = await handler.execute(node, _exec_ctx(row_count=2))
    assert result.condition_value is True


@pytest.mark.asyncio
async def test_condition_handler_supports_template_and_allowlisted_function() -> None:
    handler = ConditionNodeHandler()
    node = NodeDefinition(
        node_id="check_cache",
        type=NodeTypeEnum.CONDITION,
        config={"expression": "redis_key_exists('{{cache_key}}') == False"},
    )

    result = await handler.execute(node, _exec_ctx(row_count=1))
    assert result.condition_value is True


def test_safe_eval_blocks_non_allowlisted_function_calls() -> None:
    with pytest.raises(UnsafeExpression, match="allowlisted"):
        safe_eval("__import__('os').system('dir')", execution_context=_exec_ctx())


def test_safe_eval_rejects_unknown_variables() -> None:
    with pytest.raises(UnsafeExpression, match="Unknown variable"):
        safe_eval("unknown_symbol > 0", execution_context=_exec_ctx())
