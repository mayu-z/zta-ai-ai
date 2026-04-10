from __future__ import annotations

from datetime import datetime

from app.core.exceptions import AuthorizationError
from app.interpreter.domain_gate import is_domain_allowed
from app.schemas.pipeline import (
    CompiledQueryPlan,
    InterpretedIntent,
    PolicyDecision,
    ScopeContext,
)


class PolicyEngine:
    def authorize(
        self, scope: ScopeContext, intent: InterpretedIntent, plan: CompiledQueryPlan
    ) -> PolicyDecision:
        # IT Head can only access admin domain through chat
        if scope.role_key in {"it_head", "it_admin"} or scope.persona_type == "it_head":
            if intent.domain != "admin":
                raise AuthorizationError(
                    message="IT Head is restricted to admin dashboard and cannot access business data chat",
                    code="IT_HEAD_CHAT_BLOCKED",
                )
            # Allow admin domain queries for IT Head
            return PolicyDecision(allowed=True)

        if not scope.chat_enabled:
            raise AuthorizationError(
                message="Chat access is disabled for this user",
                code="CHAT_DISABLED",
            )

        if not is_domain_allowed(intent.domain, scope.allowed_domains):
            raise AuthorizationError(
                message="Domain not allowed for persona", code="POLICY_DOMAIN_DENY"
            )

        if scope.aggregate_only and not plan.requires_aggregate:
            raise AuthorizationError(
                message="Executive access requires aggregate output",
                code="EXEC_AGGREGATE_ONLY",
            )

        sensitive_domains = set(scope.sensitive_domains or [])
        if intent.domain in sensitive_domains:
            if scope.require_business_hours_for_sensitive:
                local_hour = datetime.now().hour
                if (
                    local_hour < scope.business_hours_start
                    or local_hour > scope.business_hours_end
                ):
                    raise AuthorizationError(
                        message="Sensitive domain queries are only allowed during business hours",
                        code="ABAC_TIME_BLOCK",
                    )

            if (
                scope.require_trusted_device_for_sensitive and not scope.device_trusted
            ) or (scope.require_mfa_for_sensitive and not scope.mfa_verified):
                raise AuthorizationError(
                    message="Sensitive domain requires trusted device and MFA",
                    code="ABAC_TRUST_BLOCK",
                )

        return PolicyDecision(allowed=True)

    def apply_field_masking(
        self, values: dict[str, object], masked_fields: list[str]
    ) -> tuple[dict[str, object], list[str]]:
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
