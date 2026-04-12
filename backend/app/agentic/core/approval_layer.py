from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from app.agentic.models.action_config import ActionConfig
from app.agentic.models.agent_context import ClaimSet, RequestContext
from app.core.redis_client import redis_client


@dataclass
class ApprovalDecision:
    approved: bool
    approver_alias: str | None = None
    timestamp: datetime | None = None
    cancellation_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ApprovalLayer:
    """Confirmation and approval gate for irreversible actions."""

    def __init__(self, default_timeout_seconds: int = 300) -> None:
        self._default_timeout_seconds = default_timeout_seconds

    def _pending_key(self, ctx: RequestContext, action_id: str) -> str:
        return f"approval:pending:{ctx.tenant_id}:{ctx.session_id}:{action_id}"

    async def evaluate(
        self,
        action: ActionConfig,
        claim_set: ClaimSet,
        ctx: RequestContext,
    ) -> ApprovalDecision:
        if not action.requires_confirmation and not action.human_approval_required:
            return ApprovalDecision(
                approved=True,
                approver_alias=ctx.user_alias,
                timestamp=datetime.utcnow(),
            )

        if claim_set.claims.get("_approval_granted") is True:
            approver = claim_set.claims.get("_approver_alias") or ctx.user_alias
            return ApprovalDecision(
                approved=True,
                approver_alias=str(approver),
                timestamp=datetime.utcnow(),
                metadata={"source": "claim_set"},
            )

        key = self._pending_key(ctx, action.action_id)
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=self._default_timeout_seconds)
        redis_client.set_json(
            key,
            {
                "tenant_id": str(ctx.tenant_id),
                "session_id": ctx.session_id,
                "action_id": action.action_id,
                "created_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
            },
            ttl_seconds=self._default_timeout_seconds,
        )

        return ApprovalDecision(
            approved=False,
            cancellation_reason="confirmation_required",
            metadata={"pending_key": key, "expires_at": expires_at.isoformat()},
        )
