from __future__ import annotations

import dataclasses
import re
from datetime import UTC, datetime

from app.schemas.pipeline import InterpretedIntent


@dataclasses.dataclass(frozen=True)
class IntentRule:
    name: str
    domain: str
    entity_type: str
    slot_keys: tuple[str, ...]
    keywords: tuple[str, ...]
    requires_aggregation: bool = False


INTENT_RULES: tuple[IntentRule, ...] = (
    # IPEDS institution-level data (always available)
    # More specific intents first, then general ones
    IntentRule(
        name="institution_size_distribution",
        domain="campus",
        entity_type="institution_size_summary",
        slot_keys=("small_count", "medium_count", "large_count", "total_institutions"),
        keywords=("size", "small", "medium", "large", "distribution"),
        requires_aggregation=True,
    ),
    IntentRule(
        name="institution_demographics",
        domain="campus",
        entity_type="institution_demographics",
        slot_keys=("hbcu_count", "public_count", "private_count", "total_institutions"),
        keywords=(
            "hbcu",
            "public",
            "private",
            "demographics",
            "sector",
            "control",
            "type",
        ),
        requires_aggregation=True,
    ),
    IntentRule(
        name="executive_enrollment_overview",
        domain="campus",
        entity_type="institution_enrollment_summary",
        slot_keys=("total_enrollment", "institution_count"),
        keywords=(
            "enrollment",
            "enrolment",
            "headcount",
            "student count",
            "students",
            "enrolled",
        ),
        requires_aggregation=True,
    ),
    IntentRule(
        name="executive_kpi",
        domain="campus",
        entity_type="executive_summary",
        slot_keys=("kpi_value", "trend_delta"),
        keywords=("kpi", "trend", "campus kpi", "overview", "metrics", "performance"),
        requires_aggregation=True,
    ),
    IntentRule(
        name="admissions_overview",
        domain="admissions",
        entity_type="admin_function_summary",
        slot_keys=("function_metric", "record_count"),
        keywords=(
            "admission",
            "admissions",
            "applicant",
            "applicants",
            "open admission",
        ),
        requires_aggregation=True,
    ),
    IntentRule(
        name="institution_profile",
        domain="admin",
        entity_type="institution_catalog",
        slot_keys=("profile",),
        keywords=(
            "institution profile",
            "university profile",
            "college profile",
            "school profile",
            "info",
            "details",
        ),
        requires_aggregation=False,
    ),
    # Student-level data (requires tenant's own database, not IPEDS)
    IntentRule(
        name="student_attendance",
        domain="academic",
        entity_type="attendance_summary",
        slot_keys=("attendance_percentage", "subject_count"),
        keywords=("attendance", "present"),
    ),
    IntentRule(
        name="student_grades",
        domain="academic",
        entity_type="grade_summary",
        slot_keys=("gpa", "passed_subjects"),
        keywords=("grade", "gpa", "result"),
    ),
    IntentRule(
        name="student_fee",
        domain="finance",
        entity_type="fee_summary",
        slot_keys=("fee_balance", "due_date"),
        keywords=("fee", "balance", "payment"),
    ),
    IntentRule(
        name="faculty_course_attendance",
        domain="academic",
        entity_type="faculty_course_summary",
        slot_keys=("course_count", "avg_attendance"),
        keywords=("my courses", "course attendance", "course"),
    ),
    IntentRule(
        name="department_metrics",
        domain="department",
        entity_type="department_summary",
        slot_keys=("department_metric", "student_count"),
        keywords=("department", "dept", "faculty performance"),
    ),
    IntentRule(
        name="admin_function_report",
        domain="finance",
        entity_type="admin_function_summary",
        slot_keys=("function_metric", "record_count"),
        keywords=("finance", "payments", "applications", "records"),
    ),
    IntentRule(
        name="admin_data_sources",
        domain="admin",
        entity_type="admin_data_sources",
        slot_keys=("sources",),
        keywords=("data-sources", "data sources", "connectors", "connections"),
    ),
    IntentRule(
        name="admin_audit_log",
        domain="admin",
        entity_type="admin_audit_log",
        slot_keys=("entries",),
        keywords=("audit-log", "audit log", "audit", "activity log", "logs"),
    ),
)


def _extract_filters(prompt: str) -> dict[str, str]:
    lower_prompt = prompt.lower()
    filters: dict[str, str] = {}

    if "this semester" in lower_prompt or "current semester" in lower_prompt:
        filters["semester"] = "current"

    quarter_match = re.search(r"\bq([1-4])\b", lower_prompt)
    if quarter_match:
        filters["quarter"] = f"Q{quarter_match.group(1)}"

    if "today" in lower_prompt:
        filters["date"] = datetime.now(tz=UTC).date().isoformat()

    student_id_match = re.search(r"\b([A-Z]{2,5}-\d{2,8})\b", prompt)
    if student_id_match:
        filters["requested_external_id"] = student_id_match.group(1)

    course_id_match = re.search(r"\b([A-Z]{2,6}\d{2,4})\b", prompt)
    if course_id_match:
        filters["requested_course"] = course_id_match.group(1)

    return filters


def extract_intent(
    raw_prompt: str,
    sanitized_prompt: str,
    aliased_prompt: str,
    detected_domains: list[str],
    persona_type: str,
) -> InterpretedIntent:
    lower_prompt = aliased_prompt.lower()

    # Persona-specific intent mapping for ambiguous queries
    PERSONA_INTENT_OVERRIDES: dict[str, dict[str, str]] = {
        "faculty": {
            # Faculty asking about "attendance" or "courses" should get faculty intent
            "attendance": "faculty_course_attendance",
            "course": "faculty_course_attendance",
            "my courses": "faculty_course_attendance",
        },
        "student": {
            # Students asking about "attendance" should get student intent
            "attendance": "student_attendance",
            "grade": "student_grades",
            "gpa": "student_grades",
            "fee": "student_fee",
        },
        "dept_head": {
            # Dept heads asking about metrics should get department intent
            "department": "department_metrics",
            "faculty": "department_metrics",
        },
    }

    # Check for persona-specific overrides first
    overrides = PERSONA_INTENT_OVERRIDES.get(persona_type, {})
    for keyword, intent_name in overrides.items():
        if keyword in lower_prompt:
            rule = next((r for r in INTENT_RULES if r.name == intent_name), None)
            if rule and rule.domain in detected_domains:
                return _build_intent(rule, raw_prompt, sanitized_prompt, aliased_prompt, 
                                     detected_domains, lower_prompt)

    # Try to match a specific intent rule by keywords
    rule = None
    for candidate in INTENT_RULES:
        # Skip rules that don't match detected domains
        if candidate.domain not in detected_domains:
            continue
        if any(keyword in lower_prompt for keyword in candidate.keywords):
            rule = candidate
            break

    # If no specific rule matched, use persona-aware fallbacks
    if rule is None:
        if persona_type == "executive":
            # For executives, default to enrollment overview or KPI
            if any(
                kw in lower_prompt
                for kw in ("enrollment", "enrolment", "headcount", "student count")
            ):
                rule = next(
                    r for r in INTENT_RULES if r.name == "executive_enrollment_overview"
                )
            else:
                rule = next(r for r in INTENT_RULES if r.name == "executive_kpi")
        else:
            # Use domain-specific fallbacks that map to existing data
            domain = detected_domains[0] if detected_domains else "academic"
            DOMAIN_FALLBACK_INTENTS: dict[str, str] = {
                "campus": "executive_kpi",
                "admissions": "admissions_overview",
                "admin": "institution_profile",
                # academic/finance/department/hr require tenant-specific data
                # Fall back to executive_kpi for aggregated IPEDS view
                "academic": "executive_kpi",
                "finance": "executive_kpi",
                "department": "executive_kpi",
                "hr": "executive_kpi",
            }
            fallback_name = DOMAIN_FALLBACK_INTENTS.get(domain, "executive_kpi")
            rule = next(
                (r for r in INTENT_RULES if r.name == fallback_name),
                INTENT_RULES[0],  # Default to first rule (executive_kpi)
            )

    return _build_intent(rule, raw_prompt, sanitized_prompt, aliased_prompt,
                         detected_domains, lower_prompt)


def _build_intent(
    rule: IntentRule,
    raw_prompt: str,
    sanitized_prompt: str,
    aliased_prompt: str,
    detected_domains: list[str],
    lower_prompt: str,
) -> InterpretedIntent:
    """Build InterpretedIntent from matched rule."""
    aggregation = "aggregate" if rule.requires_aggregation else None
    if "aggregate" in lower_prompt or "summary" in lower_prompt:
        aggregation = aggregation or "summary"

    filters = _extract_filters(sanitized_prompt)

    return InterpretedIntent(
        name=rule.name,
        domain=rule.domain,
        entity_type=rule.entity_type,
        raw_prompt=raw_prompt,
        sanitized_prompt=sanitized_prompt,
        aliased_prompt=aliased_prompt,
        filters=filters,
        aggregation=aggregation,
        slot_keys=list(rule.slot_keys),
        detected_domains=detected_domains,
    )
