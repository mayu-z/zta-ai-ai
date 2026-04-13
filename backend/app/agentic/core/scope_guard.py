from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agentic.models.action_config import ActionConfig
from app.agentic.models.agent_context import ClaimSet, RequestContext
from app.agentic.core.policy_engine import PolicyDecision


class ScopeViolation(Exception):
    pass


@dataclass
class ScopeGuard:
    """Inject mandatory scope constraints before any connector access."""

    compiler: Any | None = None

    async def fetch_scoped(
        self,
        action: ActionConfig,
        ctx: RequestContext,
        policy_decision: PolicyDecision | None = None,
    ) -> ClaimSet:
        if self.compiler is None or not hasattr(self.compiler, "fetch_data"):
            raise ScopeViolation("compiler dependency is required for scoped claim resolution")

        decision = policy_decision or PolicyDecision(allowed=True)
        claim_set = await self.compiler.fetch_data(action=action, ctx=ctx, policy_decision=decision)
        claims = dict(claim_set.claims)

        if str(claims.get("tenant_id") or "") != str(ctx.tenant_id):
            raise ScopeViolation("tenant mismatch in claim set")

        for scope in action.required_data_scope:
            token = scope.strip().lower()
            if token.endswith(".own"):
                subject_alias = claims.get("subject_alias") or claims.get("user_alias")
                if subject_alias and str(subject_alias) != ctx.user_alias:
                    raise ScopeViolation("own scope mismatch")

            if token.endswith("department_scope"):
                claim_dept = str(claims.get("department_id") or "")
                if ctx.persona != "registrar" and claim_dept and claim_dept != ctx.department_id:
                    raise ScopeViolation("department scope mismatch")

        raw_keys = [key for key in claims.keys() if key.endswith("_raw_id") or key.endswith("_db_id")]
        if raw_keys:
            raise ScopeViolation(f"raw identifiers are not permitted in claim set: {', '.join(raw_keys)}")

        return claim_set
