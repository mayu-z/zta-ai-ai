from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
        if self.compiler is not None and hasattr(self.compiler, "fetch_data"):
            decision = policy_decision or PolicyDecision(allowed=True)
            return await self.compiler.fetch_data(action=action, ctx=ctx, policy_decision=decision)

        claims = dict(action.extra_config.get("mock_claims", {}))
        claims.setdefault("tenant_id", str(ctx.tenant_id))
        claims.setdefault("user_alias", ctx.user_alias)
        claims.setdefault("department_id", ctx.department_id)

        if claims.get("tenant_id") != str(ctx.tenant_id):
            raise ScopeViolation("tenant mismatch in claim set")

        for scope in action.required_data_scope:
            token = scope.strip().lower()
            if token.endswith(".own"):
                subject_alias = claims.get("subject_alias") or claims.get("user_alias")
                if subject_alias and str(subject_alias) != ctx.user_alias:
                    raise ScopeViolation("own scope mismatch")
                claims["subject_alias"] = ctx.user_alias

            if token.endswith("department_scope"):
                claim_dept = str(claims.get("department_id") or "")
                if ctx.persona != "registrar" and claim_dept and claim_dept != ctx.department_id:
                    raise ScopeViolation("department scope mismatch")

        raw_keys = [key for key in claims.keys() if key.endswith("_raw_id") or key.endswith("_db_id")]
        if raw_keys:
            raise ScopeViolation(f"raw identifiers are not permitted in claim set: {', '.join(raw_keys)}")

        classifications: dict[str, str] = dict(action.extra_config.get("field_classifications", {}))
        for key in claims:
            classifications.setdefault(key, "GENERAL")

        row_count = int(action.extra_config.get("row_count", 1))
        return ClaimSet(
            claims=claims,
            field_classifications=classifications,
            source_alias=str(action.extra_config.get("source_alias", "scope_guard")),
            fetched_at=datetime.utcnow(),
            row_count=row_count,
        )
