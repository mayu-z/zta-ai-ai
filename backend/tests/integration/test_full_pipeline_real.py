from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text

from app.agentic.compiler.execution_planner import ExecutionPlanner
from app.agentic.compiler.scope_injector import ScopeInjector
from app.agentic.compiler.write_guard import WriteGuard
from app.agentic.connectors.claimset_builder import ClaimSetBuilder, FieldSchema, MaskingEngine, SchemaRegistry
from app.agentic.connectors.registry import ConnectorPool
from app.agentic.connectors.router import ConnectorRouter, SourceConfig, TenantConfigService
from app.agentic.core.approval_layer import ApprovalDecision
from app.agentic.core.audit_logger import AuditLogger
from app.agentic.core.compiler_interface import CompilerInterface
from app.agentic.core.policy_engine import PolicyDecision
from app.agentic.core.scope_guard import ScopeGuard
from app.agentic.engine.agent_runner import AgentRunner
from app.agentic.engine.node_executor import NodeExecutor
from app.agentic.models.action_config import ActionConfig
from app.agentic.models.agent_context import IntentClassification, RequestContext
from app.agentic.models.agent_definition import AgentDefinition


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class StaticRegistry:
    def __init__(self, action: ActionConfig):
        self._action = action

    async def get(self, action_id, tenant_id):
        del action_id, tenant_id
        return self._action


class StaticPolicy:
    async def evaluate(self, action, ctx):
        del action, ctx
        return PolicyDecision(allowed=True)


class StaticApproval:
    async def evaluate(self, action, claim_set, ctx):
        del action, claim_set
        return ApprovalDecision(approved=True, approver_alias=ctx.user_alias, timestamp=_utcnow_naive())


class StaticDefinitionLoader:
    def __init__(self, definition: AgentDefinition):
        self._definition = definition

    async def load(self, agent_id, tenant_id):
        del tenant_id
        if agent_id == self._definition.agent_id:
            return self._definition
        return None


class StaticTenantConfig(TenantConfigService):
    def __init__(self, sync_url: str):
        self._sync_url = sync_url

    async def get_source_for_entity(self, *, entity: str, tenant_id: UUID):
        del tenant_id
        return SourceConfig(
            source_type="postgres",
            source_id="pg-main",
            entity_mapping=entity,
            field_mappings={},
            connection_config={"connection_url": self._sync_url},
        )


def _seed(sync_url: str, tenant_id: str) -> None:
    engine = create_engine(sync_url)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS fees"))
        conn.execute(
            text(
                """
                CREATE TABLE fees (
                    id SERIAL PRIMARY KEY,
                    tenant_id VARCHAR(64) NOT NULL,
                    student_id VARCHAR(64) NOT NULL,
                    outstanding_balance INTEGER NOT NULL,
                    due_date VARCHAR(64)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO fees (tenant_id, student_id, outstanding_balance, due_date)
                VALUES
                  (:tenant_id, 'STU-001', 5000, '2026-05-01'),
                  (:tenant_id, 'STU-002', 9000, '2026-06-01')
                """
            ),
            {"tenant_id": tenant_id},
        )


def _definition(action_id: str) -> AgentDefinition:
    return AgentDefinition.model_validate(
        {
            "agent_id": action_id,
            "display_name": "Fee Reminder",
            "version": "1.0.0",
            "description": "dynamic full pipeline test",
            "trigger": {"type": "user_query"},
            "intent": {"action_id": action_id},
            "policy": {"allowed_personas": ["student"], "required_data_scope": ["fees.own"]},
            "steps": [
                {"node_id": "validate_action", "type": "action", "config": {"action_id": action_id}},
                {
                    "node_id": "fetch_fees",
                    "type": "fetch",
                    "config": {"action_id": action_id},
                    "output_key": "fees_data",
                },
                {
                    "node_id": "verify_scope",
                    "type": "condition",
                    "config": {
                        "expression": "fees_data.row_count == 1 and fees_data.claims.outstanding_balance == 5000"
                    },
                },
            ],
            "edges": [
                {"from": "START", "to": "validate_action"},
                {"from": "validate_action", "to": "fetch_fees"},
                {"from": "fetch_fees", "to": "verify_scope"},
                {"from": "verify_scope", "to": "END_SUCCESS", "condition": "true"},
                {"from": "verify_scope", "to": "END_FAILED", "condition": "false"},
            ],
        }
    )


@pytest.mark.asyncio
async def test_full_pipeline_with_real_db() -> None:
    tc = pytest.importorskip("testcontainers.postgres")
    PostgresContainer = tc.PostgresContainer

    tenant_id = uuid4()
    with PostgresContainer("postgres:16") as container:
        sync_url = container.get_connection_url()
        _seed(sync_url, str(tenant_id))

        schema = SchemaRegistry()
        schema.register(
            tenant_id=tenant_id,
            entity="fees",
            fields={
                "student_id": FieldSchema("student_id", "student_id", "IDENTIFIER"),
                "outstanding_balance": FieldSchema("outstanding_balance", "outstanding_balance", "GENERAL"),
                "due_date": FieldSchema("due_date", "due_date", "GENERAL"),
            },
        )

        planner = ExecutionPlanner(
            scope_injector=ScopeInjector(),
            connector_router=ConnectorRouter(ConnectorPool(), StaticTenantConfig(sync_url)),
            claimset_builder=ClaimSetBuilder(schema, MaskingEngine()),
            write_guard=WriteGuard(),
            audit_logger=AuditLogger(),
        )
        compiler = CompilerInterface(planner=planner)
        action = ActionConfig(
            action_id="fee_reminder_v1",
            tenant_id=tenant_id,
            display_name="Fee Reminder",
            description="desc",
            trigger_type="user_query",
            required_data_scope=["fees.own"],
            output_type="notification",
            allowed_personas=["student"],
            requires_confirmation=False,
        )

        registry = StaticRegistry(action)
        runner = AgentRunner(
            definition_loader=StaticDefinitionLoader(_definition(action.action_id)),
            node_executor=NodeExecutor(
                action_registry=registry,
                policy_engine=StaticPolicy(),
                scope_guard=ScopeGuard(compiler=compiler),
                approval_layer=StaticApproval(),
            ),
            action_registry=registry,
            policy_engine=StaticPolicy(),
            audit_logger=AuditLogger(),
        )

        result = await runner.run(
            agent_id=action.action_id,
            intent=IntentClassification(
                is_agentic=True,
                action_id="fee_reminder_v1",
                confidence=0.99,
                extracted_entities={},
                raw_intent_text="fee reminder",
            ),
            ctx=RequestContext(
                tenant_id=tenant_id,
                user_alias="STU-001",
                session_id="sid-1",
                persona="student",
                department_id="CS",
                jwt_claims={},
            ),
        )

        assert result.status.value == "SUCCESS"
        assert result.data is not None
        assert len(result.data.get("steps_executed", [])) == 3
