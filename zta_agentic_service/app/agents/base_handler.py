from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.db.agent_models import AgentInstance
else:
    AgentInstance = Any


@dataclass
class AgentContext:
    """Execution envelope passed to handlers after upstream policy and scope checks."""

    action_id: str
    instance: AgentInstance
    tenant_id: str
    user_id: str | None
    claim_set: dict[str, Any]
    trigger_payload: dict[str, Any]
    confirmed: bool = False


@dataclass
class AgentResult:
    status: str
    output: dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    confirmation_prompt: str | None = None
    rollback_performed: bool = False
    error: str | None = None


class BaseAgentHandler(ABC):
    """Contract implemented by all registry-driven agent handlers."""

    @abstractmethod
    async def execute(self, ctx: AgentContext) -> AgentResult:
        """Execute agent logic using only the scoped data in `ctx.claim_set`."""

    @abstractmethod
    async def rollback(self, ctx: AgentContext, partial_result: AgentResult) -> None:
        """Undo side effects after execution failures where possible."""

    @abstractmethod
    def validate_config(self, config: dict[str, Any]) -> list[str]:
        """Validate tenant instance config at enable/edit time."""

    @property
    @abstractmethod
    def is_side_effect(self) -> bool:
        """Return True when handler performs write or external side effects."""
