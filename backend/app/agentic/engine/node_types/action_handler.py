from __future__ import annotations

from typing import Any

from app.agentic.engine.node_types.base_handler import BaseNodeHandler
from app.agentic.models.agent_context import AgentStatus
from app.agentic.models.agent_definition import ExecutionContext, NodeDefinition, NodeResult


class ActionNodeHandler(BaseNodeHandler):
    def __init__(self, *, action_registry: Any):
        self._registry = action_registry

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

        return NodeResult(
            output={
                "action_id": action.action_id,
                "trigger_type": action.trigger_type,
                "output_type": action.output_type,
                "required_data_scope": list(action.required_data_scope),
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
