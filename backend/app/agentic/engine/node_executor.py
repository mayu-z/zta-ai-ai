from __future__ import annotations

from typing import Any

from app.agentic.engine.node_types.base_handler import BaseNodeHandler
from app.agentic.engine.node_types.condition_handler import ConditionNodeHandler
from app.agentic.models.agent_definition import ExecutionContext, NodeDefinition, NodeResult


class UnknownNodeType(Exception):
    pass


class NodeExecutor:
    def __init__(self, node_handlers: dict[str, BaseNodeHandler] | None = None):
        self._handlers = node_handlers or {
            "condition": ConditionNodeHandler(),
        }

    async def execute(self, node: NodeDefinition, ctx: ExecutionContext) -> NodeResult:
        node_type = self._to_handler_key(node.type)
        handler = self._handlers.get(node_type)
        if handler is None:
            raise UnknownNodeType(f"No handler registered for node type: {node_type}")
        return await handler.execute(node, ctx)

    @staticmethod
    def _to_handler_key(node_type: Any) -> str:
        if hasattr(node_type, "value"):
            return str(node_type.value)
        return str(node_type)
