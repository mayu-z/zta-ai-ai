from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.agentic.engine.node_types.base_handler import BaseNodeHandler
from app.agentic.models.agent_context import AgentStatus, ClaimSet
from app.agentic.models.agent_definition import ExecutionContext, NodeDefinition, NodeResult


class ApprovalNodeHandler(BaseNodeHandler):
    def __init__(self, *, action_registry: Any, approval_layer: Any):
        self._registry = action_registry
        self._approval = approval_layer

    async def execute(self, node: NodeDefinition, ctx: ExecutionContext) -> NodeResult:
        config = self.resolve_config(node, ctx)
        action_id = self._resolve_action_id(config, ctx)
        action = await self._registry.get(action_id, ctx.ctx.tenant_id)
        if action is None or not action.is_enabled:
            return NodeResult(
                should_halt=True,
                halt_status=AgentStatus.FAILED,
                halt_message=f"Action '{action_id}' is unavailable",
            )

        claim_key = str(config.get("claim_set_key") or "")
        claim_set = self._resolve_claim_set(ctx, claim_key)
        decision = await self._approval.evaluate(action, claim_set, ctx.ctx)
        if not decision.approved:
            return NodeResult(
                output=decision.metadata,
                should_halt=True,
                halt_status=AgentStatus.PENDING_APPROVAL,
                halt_message=decision.cancellation_reason or "Approval required",
            )

        return NodeResult(
            output={
                "approved": True,
                "approver_alias": decision.approver_alias,
                "timestamp": decision.timestamp.isoformat() if decision.timestamp else None,
            }
        )

    @staticmethod
    def _resolve_action_id(config: dict[str, Any], ctx: ExecutionContext) -> str:
        return str(
            config.get("action_id")
            or ctx.intent.action_id
            or ctx.definition.intent.action_id
            or ctx.definition.agent_id
        )

    @staticmethod
    def _resolve_claim_set(ctx: ExecutionContext, claim_set_key: str) -> ClaimSet:
        if claim_set_key and claim_set_key in ctx.claim_sets:
            return ctx.claim_sets[claim_set_key]

        if ctx.claim_sets:
            return next(iter(ctx.claim_sets.values()))

        return ClaimSet(
            claims={"tenant_id": str(ctx.ctx.tenant_id)},
            field_classifications={"tenant_id": "GENERAL"},
            source_alias="approval",
            fetched_at=datetime.now(tz=UTC).replace(tzinfo=None),
            row_count=0,
        )
