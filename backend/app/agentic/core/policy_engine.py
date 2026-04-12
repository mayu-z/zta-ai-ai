from __future__ import annotations

from dataclasses import dataclass, field

from app.agentic.models.action_config import ActionConfig
from app.agentic.models.agent_context import RequestContext


@dataclass
class PolicyDecision:
    allowed: bool
    denial_reason: str | None = None
    masked_fields: list[str] = field(default_factory=list)
    conditions: dict[str, object] = field(default_factory=dict)


class PolicyEngine:
    """RBAC/ABAC gate before any scoped data fetch."""

    async def evaluate(self, action: ActionConfig, ctx: RequestContext) -> PolicyDecision:
        persona = (ctx.persona or "").strip().lower()
        allowed_personas = {item.strip().lower() for item in action.allowed_personas}
        if persona not in allowed_personas:
            return PolicyDecision(
                allowed=False,
                denial_reason="PERMISSION_DENIED: persona is not allowed for this action",
            )

        required_claims = action.extra_config.get("required_jwt_claims", {})
        for key, expected_value in required_claims.items():
            if ctx.jwt_claims.get(key) != expected_value:
                return PolicyDecision(
                    allowed=False,
                    denial_reason=f"PERMISSION_DENIED: missing required claim '{key}'",
                )

        masked_fields = list(action.extra_config.get("masked_fields", []))
        return PolicyDecision(
            allowed=True,
            masked_fields=masked_fields,
            conditions={"persona": persona, "tenant_id": str(ctx.tenant_id)},
        )
