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
        name="executive_kpi",
        domain="campus",
        entity_type="executive_summary",
        slot_keys=("kpi_value", "trend_delta"),
        keywords=("kpi", "summary", "trend", "campus"),
        requires_aggregation=True,
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

    if persona_type == "executive":
        rule = next(rule for rule in INTENT_RULES if rule.name == "executive_kpi")
    else:
        rule = None
        for candidate in INTENT_RULES:
            if candidate.domain not in detected_domains:
                continue
            if any(keyword in lower_prompt for keyword in candidate.keywords):
                rule = candidate
                break

        if rule is None:
            domain = detected_domains[0]
            rule = IntentRule(
                name="domain_summary",
                domain=domain,
                entity_type=f"{domain}_summary",
                slot_keys=("primary_value", "secondary_value"),
                keywords=(domain,),
            )

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
