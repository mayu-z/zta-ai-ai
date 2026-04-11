from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DomainKeyword, DomainSourceBinding, IntentDefinition, RolePolicy


@dataclass(slots=True)
class OnboardingIssue:
    severity: str
    code: str
    message: str
    domain: str | None = None
    details: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }
        if self.domain is not None:
            payload["domain"] = self.domain
        if self.details:
            payload["details"] = self.details
        return payload


def validate_interpreter_onboarding(
    db: Session,
    tenant_id: str,
    domain: str | None = None,
) -> dict[str, object]:
    normalized_domain = domain.strip().lower() if domain else None

    domain_rows = db.scalars(
        select(DomainKeyword).where(
            DomainKeyword.tenant_id == tenant_id,
            DomainKeyword.is_active.is_(True),
        )
    ).all()
    intent_rows = db.scalars(
        select(IntentDefinition).where(
            IntentDefinition.tenant_id == tenant_id,
            IntentDefinition.is_active.is_(True),
        )
    ).all()
    binding_rows = db.scalars(
        select(DomainSourceBinding).where(
            DomainSourceBinding.tenant_id == tenant_id,
            DomainSourceBinding.is_active.is_(True),
        )
    ).all()
    role_rows = db.scalars(
        select(RolePolicy).where(
            RolePolicy.tenant_id == tenant_id,
            RolePolicy.is_active.is_(True),
        )
    ).all()

    keywords_by_domain = {row.domain.strip().lower(): row for row in domain_rows}
    bindings_by_domain = {row.domain.strip().lower(): row for row in binding_rows}

    intents_by_domain: dict[str, list[IntentDefinition]] = {}
    for row in intent_rows:
        key = row.domain.strip().lower()
        intents_by_domain.setdefault(key, []).append(row)

    all_domains = sorted(
        set(keywords_by_domain.keys())
        | set(bindings_by_domain.keys())
        | set(intents_by_domain.keys())
    )

    issues: list[OnboardingIssue] = []

    if normalized_domain:
        if normalized_domain not in all_domains:
            issues.append(
                OnboardingIssue(
                    severity="error",
                    code="DOMAIN_NOT_CONFIGURED",
                    message="Requested domain has no onboarding configuration",
                    domain=normalized_domain,
                )
            )
            domains_to_check: list[str] = [normalized_domain]
        else:
            domains_to_check = [normalized_domain]
    else:
        domains_to_check = all_domains

    if not domains_to_check:
        issues.append(
            OnboardingIssue(
                severity="error",
                code="NO_INTERPRETER_DOMAINS_CONFIGURED",
                message="No active interpreter onboarding configuration exists for this tenant",
            )
        )

    for check_domain in domains_to_check:
        keyword_row = keywords_by_domain.get(check_domain)
        if keyword_row is None:
            issues.append(
                OnboardingIssue(
                    severity="warning",
                    code="DOMAIN_KEYWORDS_MISSING",
                    message=(
                        "Domain keyword mapping is missing; runtime will rely on derived fallback "
                        "from intent definitions"
                    ),
                    domain=check_domain,
                )
            )
        elif not keyword_row.keywords:
            issues.append(
                OnboardingIssue(
                    severity="warning",
                    code="DOMAIN_KEYWORDS_EMPTY",
                    message="Domain keyword mapping exists but has no active keywords",
                    domain=check_domain,
                )
            )

        domain_intents = intents_by_domain.get(check_domain, [])
        if not domain_intents:
            issues.append(
                OnboardingIssue(
                    severity="error",
                    code="DOMAIN_INTENTS_MISSING",
                    message="No active intent definitions are configured for this domain",
                    domain=check_domain,
                )
            )
        else:
            default_count = 0
            personas: set[str] = set()
            for intent in domain_intents:
                if intent.is_default:
                    default_count += 1
                if not intent.slot_keys:
                    issues.append(
                        OnboardingIssue(
                            severity="error",
                            code="INTENT_SLOT_KEYS_MISSING",
                            message="Intent definition must include slot_keys",
                            domain=check_domain,
                            details={"intent_name": intent.intent_name},
                        )
                    )
                for persona in intent.persona_types or []:
                    normalized = str(persona).strip().lower()
                    if normalized:
                        personas.add(normalized)

            if default_count == 0:
                issues.append(
                    OnboardingIssue(
                        severity="error",
                        code="DOMAIN_DEFAULT_INTENT_MISSING",
                        message="At least one default intent is required for safe fallback routing",
                        domain=check_domain,
                    )
                )

            if not personas:
                issues.append(
                    OnboardingIssue(
                        severity="warning",
                        code="DOMAIN_INTENT_PERSONAS_MISSING",
                        message="Intent definitions do not declare persona_types coverage",
                        domain=check_domain,
                    )
                )

        if check_domain not in bindings_by_domain:
            issues.append(
                OnboardingIssue(
                    severity="warning",
                    code="DOMAIN_SOURCE_BINDING_MISSING",
                    message="No active domain source binding is configured",
                    domain=check_domain,
                )
            )

        covered_by_role_policy = any(
            check_domain in {str(value).strip().lower() for value in (role.allowed_domains or [])}
            for role in role_rows
        )
        if not covered_by_role_policy:
            issues.append(
                OnboardingIssue(
                    severity="warning",
                    code="DOMAIN_ROLE_COVERAGE_MISSING",
                    message="No active role policy currently grants this domain",
                    domain=check_domain,
                )
            )

    error_count = sum(1 for issue in issues if issue.severity == "error")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")

    return {
        "tenant_id": tenant_id,
        "domain": normalized_domain,
        "domains_checked": domains_to_check,
        "ready": error_count == 0,
        "summary": {
            "errors": error_count,
            "warnings": warning_count,
            "active_domain_keywords": len(domain_rows),
            "active_intent_definitions": len(intent_rows),
            "active_domain_source_bindings": len(binding_rows),
            "active_role_policies": len(role_rows),
        },
        "issues": [issue.to_dict() for issue in issues],
    }
