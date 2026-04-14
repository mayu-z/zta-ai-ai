from __future__ import annotations

from abc import ABC, abstractmethod
import re
from typing import Any

from app.agentic.models.agent_definition import ExecutionContext, NodeDefinition, NodeResult


class BaseNodeHandler(ABC):
    @abstractmethod
    async def execute(self, node: NodeDefinition, ctx: ExecutionContext) -> NodeResult:
        ...

    def resolve_config(self, node: NodeDefinition, exec_ctx: ExecutionContext) -> dict[str, Any]:
        return self._resolve_value(node.config, exec_ctx)

    def _resolve_value(self, value: Any, exec_ctx: ExecutionContext) -> Any:
        if isinstance(value, str):
            return self._resolve_string(value, exec_ctx)
        if isinstance(value, dict):
            return {
                key: self._resolve_value(item, exec_ctx)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._resolve_value(item, exec_ctx) for item in value]
        return value

    def _resolve_string(self, value: str, exec_ctx: ExecutionContext) -> Any:
        full_token = re.match(r"^\s*\{\{\s*[^{}]+\s*\}\}\s*$", value)
        if full_token:
            return exec_ctx.resolve(value)

        token_pattern = re.compile(r"\{\{\s*[^{}]+\s*\}\}")
        if not token_pattern.search(value):
            return value

        def _replace(match: re.Match[str]) -> str:
            resolved = exec_ctx.resolve(match.group(0))
            return "" if resolved is None else str(resolved)

        return token_pattern.sub(_replace, value)
