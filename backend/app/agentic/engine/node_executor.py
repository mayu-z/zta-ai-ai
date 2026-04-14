from __future__ import annotations

from typing import Any

from app.agentic.engine.node_types import (
    ActionNodeHandler,
    ApprovalNodeHandler,
    ConditionNodeHandler,
    FetchNodeHandler,
)
from app.agentic.engine.node_types.base_handler import BaseNodeHandler
from app.agentic.models.agent_definition import ExecutionContext, NodeDefinition, NodeResult


class UnknownNodeType(Exception):
    pass


class NodeExecutor:
    def __init__(
        self,
        node_handlers: dict[str, BaseNodeHandler] | None = None,
        *,
        action_registry: Any | None = None,
        policy_engine: Any | None = None,
        scope_guard: Any | None = None,
        approval_layer: Any | None = None,
    ):
        if node_handlers is not None:
            self._handlers = node_handlers
        else:
            self._handlers = {
                "action": ActionNodeHandler(action_registry=action_registry),
                "approval": ApprovalNodeHandler(action_registry=action_registry, approval_layer=approval_layer),
                "condition": ConditionNodeHandler(),
                "fetch": FetchNodeHandler(
                    action_registry=action_registry,
                    policy_engine=policy_engine,
                    scope_guard=scope_guard,
                ),
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
