from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

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

    @staticmethod
    def _utc_now_naive() -> datetime:
        return datetime.now(tz=UTC).replace(tzinfo=None)

    async def evaluate(
        self,
        action: ActionConfig,
        claim_set: ClaimSet,
        ctx: RequestContext,
    ) -> ApprovalDecision:
        del claim_set
        if not action.requires_confirmation and not action.human_approval_required:
            return ApprovalDecision(
                approved=True,
                approver_alias=ctx.user_alias,
                timestamp=self._utc_now_naive(),
            )

        key = self._pending_key(ctx, action.action_id)
        now = self._utc_now_naive()
        expires_at = now + timedelta(seconds=self._default_timeout_seconds)
        nonce = uuid4().hex
        redis_client.set_json(
            key,
            {
                "tenant_id": str(ctx.tenant_id),
                "session_id": ctx.session_id,
                "action_id": action.action_id,
                "user_alias": ctx.user_alias,
                "nonce": nonce,
                "created_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
            },
            ttl_seconds=self._default_timeout_seconds,
        )

        return ApprovalDecision(
            approved=False,
            cancellation_reason="confirmation_required",
            metadata={"pending_key": key, "expires_at": expires_at.isoformat(), "nonce": nonce},
        )
