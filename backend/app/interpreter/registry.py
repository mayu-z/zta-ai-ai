from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.db.models import DomainKeyword, IntentDefinition, IntentDetectionKeyword
from app.interpreter.domain_gate import AGGREGATION_MODIFIERS
from app.interpreter.intent_extractor import IntentRule


_DERIVED_DOMAIN_KEYWORD_STOPWORDS = {
    "a",
    "all",
    "an",
    "and",
    "by",
    "count",
    "dashboard",
    "data",
    "detail",
    "details",
    "for",
    "get",
    "in",
    "info",
    "list",
    "metric",
    "metrics",
    "of",
    "overview",
    "record",
    "records",
    "report",
    "reports",
    "show",
    "status",
    "summary",
    "the",
    "to",
    "total",
    "view",
}

# Runtime keyword hints improve natural-language domain detection for existing
# tenants without requiring a DB reseed.
_RUNTIME_DOMAIN_KEYWORD_HINTS: dict[str, tuple[str, ...]] = {
    "academic": (
        "class",
        "classes",
        "subject",
        "subjects",
        "enrolled",
        "enrollment",
        "enrolment",
        "semester",
        "gpa",
    ),
    "finance": (
        "fees",
        "balance",
        "balances",
        "due",
        "tuition",
        "scholarship",
    ),
    "hr": (
        "vacation",
        "timesheet",
        "workload",
    ),
    "admissions": (
        "admission",
        "applications",
        "applicant",
        "applicants",
    ),
    "exam": (
        "exams",
        "results",
        "scores",
    ),
    "department": (
        "departments",
        "hod",
    ),
    "campus": (
        "hostel",
        "infrastructure",
        "institution",
    ),
    "admin": (
        "users",
        "access",
        "permissions",
    ),
    "notices": (
        "notices",
        "announcements",
        "alerts",
    ),
}


def _normalize_keywords(values: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if not values:
        return ()

    normalized: list[str] = []
    for value in values:
        keyword = str(value).strip().lower()
        if keyword and keyword not in normalized:
            normalized.append(keyword)
    return tuple(normalized)


def _tokenize_derived_keywords(value: str) -> tuple[str, ...]:
    tokens = [
        token
        for token in re.split(r"[^a-z0-9]+", value.lower())
        if len(token) >= 3 and token not in _DERIVED_DOMAIN_KEYWORD_STOPWORDS
    ]
    return tuple(tokens)


def derive_domain_keywords_from_intent_rules(
    intent_rules: tuple[IntentRule, ...],
) -> dict[str, tuple[str, ...]]:
    """Build fallback domain keywords from intent rules for domain onboarding bootstraps."""
    derived: dict[str, set[str]] = {}

    for rule in intent_rules:
        domain = rule.domain.strip().lower()
        if not domain:
            continue

        domain_keywords = derived.setdefault(domain, set())
        domain_keywords.add(domain)

        candidates = [rule.name, rule.entity_type, *rule.keywords, *rule.slot_keys]
        for candidate in candidates:
            normalized = str(candidate).strip().lower()
            if not normalized:
                continue

            if " " in normalized and len(normalized) >= 4:
                domain_keywords.add(normalized)

            for token in _tokenize_derived_keywords(normalized):
                domain_keywords.add(token)

    return {
        domain: tuple(sorted(keywords))
        for domain, keywords in derived.items()
        if keywords
    }


def load_domain_keywords(
    db: Session,
    tenant_id: str,
) -> tuple[dict[str, tuple[str, ...]], tuple[str, ...]]:
    rows = db.scalars(
        select(DomainKeyword).where(
            DomainKeyword.tenant_id == tenant_id,
            DomainKeyword.is_active.is_(True),
        )
    ).all()

    loaded: dict[str, tuple[str, ...]] = {}
    for row in rows:
        keywords = _normalize_keywords(row.keywords)
        if not keywords:
            continue
        loaded[row.domain] = keywords

    if not loaded:
        raise ValidationError(
            message="No active domain keyword configuration is available for this tenant",
            code="DOMAIN_KEYWORDS_NOT_CONFIGURED",
        )

    # Merge built-in hints for better natural-language matching.
    for domain, hints in _RUNTIME_DOMAIN_KEYWORD_HINTS.items():
        existing = list(loaded.get(domain, ()))
        for hint in hints:
            if hint not in existing:
                existing.append(hint)
        if existing:
            loaded[domain] = tuple(existing)

    return loaded, AGGREGATION_MODIFIERS


def load_intent_rules(db: Session, tenant_id: str) -> tuple[IntentRule, ...]:
    rows = db.scalars(
        select(IntentDefinition)
        .where(
            IntentDefinition.tenant_id == tenant_id,
            IntentDefinition.is_active.is_(True),
        )
        .order_by(IntentDefinition.priority.asc(), IntentDefinition.intent_name.asc())
    ).all()

    loaded_rules: list[IntentRule] = []
    for row in rows:
        intent_name = row.intent_name.strip().lower()
        if not intent_name:
            continue

        slot_keys = _normalize_keywords(row.slot_keys)
        keywords = _normalize_keywords(row.keywords)
        persona_types = _normalize_keywords(row.persona_types)

        # slot_keys are required for safe detokenization.
        if not slot_keys:
            continue

        loaded_rules.append(
            IntentRule(
                name=intent_name,
                domain=row.domain,
                entity_type=row.entity_type,
                slot_keys=slot_keys,
                keywords=keywords,
                requires_aggregation=row.requires_aggregation,
                persona_types=persona_types,
                is_default=row.is_default,
                priority=row.priority,
            )
        )

    if not loaded_rules:
        raise ValidationError(
            message="No active intent definition configuration is available for this tenant",
            code="INTENT_RULES_NOT_CONFIGURED",
        )

    return tuple(loaded_rules)


def load_intent_detection_keywords(
    db: Session,
    tenant_id: str,
) -> dict[str, dict[str, list[str]]]:
    """Load intent detection keywords from database.

    Returns a nested dictionary mapping:
        intent_name -> keyword_type -> list of keywords

    Example:
        {
            "student_grades": {
                "grade_marker": ["gpa", "grade", "grades", "passed subject", "passed subjects", "marks"],
                "subject_marker": ["subject", "course"]
            },
            "student_attendance": {
                "attendance_marker": ["attendance", "present", "absent"]
            }
        }

    Args:
        db: SQLAlchemy session
        tenant_id: Tenant ID to filter keywords

    Returns:
        Nested dictionary of detection keywords keyed by intent_name and keyword_type
    """
    rows = db.scalars(
        select(IntentDetectionKeyword).where(
            IntentDetectionKeyword.tenant_id == tenant_id,
            IntentDetectionKeyword.is_active.is_(True),
        )
    ).all()

    result: dict[str, dict[str, list[str]]] = {}
    for row in rows:
        if row.intent_name not in result:
            result[row.intent_name] = {}
        if row.keyword_type not in result[row.intent_name]:
            result[row.intent_name][row.keyword_type] = []
        result[row.intent_name][row.keyword_type].append(row.keyword)

    return result
