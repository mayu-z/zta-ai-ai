from __future__ import annotations

from datetime import datetime

from app.core.exceptions import AuthorizationError
from app.interpreter.domain_gate import is_domain_allowed
from app.schemas.pipeline import CompiledQueryPlan, InterpretedIntent, PolicyDecision, ScopeContext


class PolicyEngine:
    def authorize(self, scope: ScopeContext, intent: InterpretedIntent, plan: CompiledQueryPlan) -> PolicyDecision:
        if scope.persona_type == "it_head" or not scope.chat_enabled:
            raise AuthorizationError(
                message="IT Head is restricted to admin dashboard and cannot access business data chat",
                code="IT_HEAD_CHAT_BLOCKED",
            )

        if not is_domain_allowed(intent.domain, scope.allowed_domains):
            raise AuthorizationError(message="Domain not allowed for persona", code="POLICY_DOMAIN_DENY")

        if scope.aggregate_only and not plan.requires_aggregate:
            raise AuthorizationError(message="Executive access requires aggregate output", code="EXEC_AGGREGATE_ONLY")

        local_hour = datetime.now().hour
        if intent.domain in {"finance", "hr"} and (local_hour < 9 or local_hour > 19):
            raise AuthorizationError(
                message="Sensitive domain queries are only allowed during business hours",
                code="ABAC_TIME_BLOCK",
            )

        if intent.domain in {"finance", "hr"} and (not scope.device_trusted or not scope.mfa_verified):
            raise AuthorizationError(
                message="Sensitive domain requires trusted device and MFA",
                code="ABAC_TRUST_BLOCK",
            )

        return PolicyDecision(allowed=True)

    def apply_field_masking(self, values: dict[str, object], masked_fields: list[str]) -> tuple[dict[str, object], list[str]]:
        if not masked_fields:
            return values, []

        masked = dict(values)
        applied: list[str] = []
        for field in masked_fields:
            if field == "*":
                for key in list(masked.keys()):
                    masked[key] = "***MASKED***"
                    applied.append(key)
                break
            if field in masked:
                masked[field] = "***MASKED***"
                applied.append(field)

        return masked, sorted(set(applied))


policy_engine = PolicyEngine()
