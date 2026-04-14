from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.agentic.models.agent_definition import AgentDefinition


class AgentDefinitionValidationError(ValueError):
    pass


class AgentDefinitionSchemaValidator:
    def validate(self, payload: dict[str, Any]) -> AgentDefinition:
        try:
            return AgentDefinition.model_validate(payload)
        except ValidationError as exc:
            raise AgentDefinitionValidationError(str(exc)) from exc
