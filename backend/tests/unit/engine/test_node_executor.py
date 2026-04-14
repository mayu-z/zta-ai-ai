from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.agentic.engine.node_executor import NodeExecutor, UnknownNodeType
from app.agentic.models.agent_context import ClaimSet, IntentClassification, RequestContext
from app.agentic.models.agent_definition import AgentDefinition, ExecutionContext, NodeDefinition, NodeTypeEnum


def _definition() -> AgentDefinition:
    return AgentDefinition.model_validate(
        {
            "agent_id": "executor_test_v1",
            "display_name": "Executor Test",
            "version": "1.0.0",
            "description": "executor test",
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
        claims={"outstanding_balance": 999},
        field_classifications={"outstanding_balance": "GENERAL"},
        source_alias="fees",
        fetched_at=datetime.now(UTC).replace(tzinfo=None),
        row_count=row_count,
    )
    return ExecutionContext(
        intent=IntentClassification(
            is_agentic=True,
            action_id="executor_test_v1",
            confidence=0.9,
            extracted_entities={},
            raw_intent_text="fees",
        ),
        ctx=RequestContext(
            tenant_id=tenant_id,
            user_alias="STU-88",
            session_id="sid-88",
            persona="student",
            department_id="CSE",
            jwt_claims={"tenant_id": str(tenant_id)},
        ),
        definition=_definition(),
        claim_sets={"fees_data": claim_set},
        computed_values={},
    )


@pytest.mark.asyncio
async def test_node_executor_dispatches_registered_handler() -> None:
    executor = NodeExecutor()
    node = NodeDefinition(
        node_id="check",
        type=NodeTypeEnum.CONDITION,
        config={"expression": "fees_data.row_count > 0"},
    )

    result = await executor.execute(node, _exec_ctx(row_count=2))
    assert result.condition_value is True


@pytest.mark.asyncio
async def test_node_executor_raises_for_missing_handler() -> None:
    executor = NodeExecutor(node_handlers={})
    node = NodeDefinition(node_id="fetch", type=NodeTypeEnum.FETCH, config={"entity": "fees"})

    with pytest.raises(UnknownNodeType, match="No handler registered"):
        await executor.execute(node, _exec_ctx(row_count=1))
