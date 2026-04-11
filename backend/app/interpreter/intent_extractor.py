from __future__ import annotations

import dataclasses
import re
from datetime import UTC, datetime

from app.core.exceptions import ValidationError
from app.schemas.pipeline import InterpretedIntent


@dataclasses.dataclass(frozen=True)
class IntentRule:
    name: str
    domain: str
    entity_type: str
    slot_keys: tuple[str, ...]
    keywords: tuple[str, ...]
    requires_aggregation: bool = False
    persona_types: tuple[str, ...] = ()
    is_default: bool = False
    priority: int = 100


INTENT_RULES: tuple[IntentRule, ...] = ()


def _keyword_pattern(keyword: str) -> str:
    normalized = keyword.strip().lower()
    if not normalized:
        return r"$^"

    if " " in normalized:
        return rf"\b{re.escape(normalized)}\b"

    if re.fullmatch(r"[a-z]+", normalized):
        if normalized.endswith("y") and len(normalized) > 3:
            stem = re.escape(normalized[:-1])
            return rf"\b(?:{re.escape(normalized)}|{stem}ies)\b"
        if normalized.endswith("s"):
            return rf"\b{re.escape(normalized)}\b"
        return rf"\b{re.escape(normalized)}(?:s|es)?\b"

    return rf"\b{re.escape(normalized)}\b"


def _keyword_matches(lower_prompt: str, keyword: str) -> bool:
    return bool(re.search(_keyword_pattern(keyword), lower_prompt))


def _keyword_match_stats(lower_prompt: str, keywords: tuple[str, ...]) -> tuple[int, int]:
    """Return (match_count, first_match_index) for candidate rule scoring."""
    match_count = 0
    first_index = len(lower_prompt) + 1

    for keyword in keywords:
        match = re.search(_keyword_pattern(keyword), lower_prompt)
        if not match:
            continue
        match_count += 1
        first_index = min(first_index, match.start())

    return match_count, first_index


def _detection_keyword_match_count(
    lower_prompt: str,
    intent_name: str,
    detection_keywords: dict[str, dict[str, list[str]]],
) -> int:
    by_type = detection_keywords.get(intent_name, {})
    if not by_type:
        return 0

    count = 0
    for keywords in by_type.values():
        for keyword in keywords:
            if _keyword_matches(lower_prompt, keyword):
                count += 1
    return count


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


def _persona_matches(rule: IntentRule, persona_type: str) -> bool:
    if not rule.persona_types:
        return True
    return persona_type in rule.persona_types


def _select_fallback_rule(
    rules: tuple[IntentRule, ...],
    detected_domains: list[str],
    persona_type: str,
) -> IntentRule:
    in_domain = [
        rule
        for rule in rules
        if rule.domain in detected_domains and _persona_matches(rule, persona_type)
    ]
    default_in_domain = next((rule for rule in in_domain if rule.is_default), None)
    if default_in_domain is not None:
        return default_in_domain
    if in_domain:
        return in_domain[0]

    by_persona = [rule for rule in rules if _persona_matches(rule, persona_type)]
    default_for_persona = next((rule for rule in by_persona if rule.is_default), None)
    if default_for_persona is not None:
        return default_for_persona
    if by_persona:
        return by_persona[0]

    return rules[0]


def extract_intent(
    raw_prompt: str,
    sanitized_prompt: str,
    aliased_prompt: str,
    detected_domains: list[str],
    persona_type: str,
    intent_rules: tuple[IntentRule, ...] | None = None,
    detection_keywords: dict[str, dict[str, list[str]]] | None = None,
) -> InterpretedIntent:
    lower_prompt = aliased_prompt.lower()
    rules = intent_rules or ()
    detection_keywords = detection_keywords or {}

    if not rules:
        raise ValidationError(
            message="No intent rules are configured for this tenant",
            code="INTENT_RULES_NOT_CONFIGURED",
        )

    # Try to match a specific intent rule by weighted keyword scoring.
    # This avoids first-match bias when multiple rules share common keywords.
    rule: IntentRule | None = None
    best_score: tuple[int, int, int, int, int, int] | None = None

    for candidate in rules:
        # Skip rules that don't match detected domains
        if candidate.domain not in detected_domains:
            continue
        if not _persona_matches(candidate, persona_type):
            continue

        match_count, first_index = _keyword_match_stats(lower_prompt, candidate.keywords)

        detection_match_count = _detection_keyword_match_count(
            lower_prompt=lower_prompt,
            intent_name=candidate.name,
            detection_keywords=detection_keywords,
        )

        if match_count == 0 and detection_match_count == 0:
            continue

        # Score order:
        # 1) detection-keyword matches, 2) matched rule keywords,
        # 3) prefer specific (non-default) rules,
        # 4) earlier keyword mention, 5) lower rule priority number,
        # 6) more rule keywords as a weak specificity tie-break.
        candidate_score = (
            detection_match_count,
            match_count,
            1 if not candidate.is_default else 0,
            -first_index,
            -candidate.priority,
            len(candidate.keywords),
        )

        if best_score is None or candidate_score > best_score:
            best_score = candidate_score
            rule = candidate

    # If no specific rule matched, choose a safe fallback from configured rules.
    if rule is None:
        rule = _select_fallback_rule(rules, detected_domains, persona_type)

    return _build_intent(
        rule,
        raw_prompt,
        sanitized_prompt,
        aliased_prompt,
        detected_domains,
        lower_prompt,
    )


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
        persona_types=rule.persona_types,
        raw_prompt=raw_prompt,
        sanitized_prompt=sanitized_prompt,
        aliased_prompt=aliased_prompt,
        filters=filters,
        aggregation=aggregation,
        slot_keys=list(rule.slot_keys),
        detected_domains=detected_domains,
    )
