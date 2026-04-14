from __future__ import annotations

from typing import Any

from app.agentic.core.scope_guard import ScopeViolation
from app.agentic.engine.node_types.base_handler import BaseNodeHandler
from app.agentic.models.agent_context import AgentStatus
from app.agentic.models.agent_definition import ExecutionContext, NodeDefinition, NodeResult


class FetchNodeHandler(BaseNodeHandler):
    def __init__(self, *, action_registry: Any, policy_engine: Any, scope_guard: Any):
        self._registry = action_registry
        self._policy = policy_engine
        self._scope = scope_guard

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

        policy_decision = await self._policy.evaluate(action, ctx.ctx)
        if not policy_decision.allowed:
            return NodeResult(
                should_halt=True,
                halt_status=AgentStatus.PERMISSION_DENIED,
                halt_message=policy_decision.denial_reason or "Permission denied",
            )

        try:
            claim_set = await self._scope.fetch_scoped(action, ctx.ctx, policy_decision)
        except ScopeViolation:
            return NodeResult(
                should_halt=True,
                halt_status=AgentStatus.SCOPE_DENIED,
                halt_message="Access denied: data outside your scope.",
            )

        return NodeResult(output=claim_set)

    @staticmethod
    def _resolve_action_id(config: dict[str, Any], ctx: ExecutionContext) -> str:
        return str(
            config.get("action_id")
            or ctx.intent.action_id
            or ctx.definition.intent.action_id
            or ctx.definition.agent_id
        )
