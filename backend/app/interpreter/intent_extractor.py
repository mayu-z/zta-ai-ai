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

_SUMMARY_STYLE_MARKERS = (
    "summary",
    "overview",
    "status",
    "snapshot",
)

_COUNT_STYLE_MARKERS = (
    "how many",
    "count",
    "number of",
    "total",
    "enrolled",
    "enrollment",
)

_LIST_STYLE_MARKERS = (
    "list",
    "detail",
    "details",
    "breakdown",
    "show all",
    "all records",
    "each",
)

_SEMANTIC_STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "get",
    "give",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "show",
    "the",
    "to",
    "what",
    "with",
}


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


def _semantic_tokens(text: str) -> set[str]:
    tokens = {
        token
        for token in re.findall(r"[a-z0-9_]{3,}", text.lower())
        if token not in _SEMANTIC_STOPWORDS
    }
    return tokens


def _semantic_terms_for_rule(
    rule: IntentRule,
    detection_keywords: dict[str, dict[str, list[str]]],
) -> set[str]:
    terms: set[str] = set()

    by_type = detection_keywords.get(rule.name, {})
    detection_terms = [keyword for values in by_type.values() for keyword in values]

    candidates = [
        rule.name,
        rule.domain,
        rule.entity_type,
        *rule.keywords,
        *rule.slot_keys,
        *detection_terms,
    ]
    for candidate in candidates:
        normalized = str(candidate).strip().lower().replace("-", "_")
        if not normalized:
            continue
        terms.update(_semantic_tokens(normalized.replace("_", " ")))

    return terms


def _semantic_overlap_score(
    lower_prompt: str,
    rule: IntentRule,
    detection_keywords: dict[str, dict[str, list[str]]],
) -> int:
    prompt_tokens = _semantic_tokens(lower_prompt)
    if not prompt_tokens:
        return 0

    rule_terms = _semantic_terms_for_rule(rule, detection_keywords)
    if not rule_terms:
        return 0

    return len(prompt_tokens.intersection(rule_terms))


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


def _intent_style_score(lower_prompt: str, rule: IntentRule) -> int:
    score = 0
    has_summary_style = any(marker in lower_prompt for marker in _SUMMARY_STYLE_MARKERS)
    has_count_style = any(marker in lower_prompt for marker in _COUNT_STYLE_MARKERS)
    has_list_style = any(marker in lower_prompt for marker in _LIST_STYLE_MARKERS)
    has_recent_style = "recent" in lower_prompt or "latest" in lower_prompt

    slot_keys_lower = tuple(slot.lower() for slot in rule.slot_keys)
    has_count_slot = any(
        "count" in slot
        or "total" in slot
        or "enrollment" in slot
        for slot in slot_keys_lower
    )
    has_list_slot = any(
        slot in {"record_name", "record_value"}
        or slot.endswith("_name")
        or slot.endswith("_value")
        for slot in slot_keys_lower
    )

    if has_summary_style and rule.is_default:
        score += 3
    if has_summary_style and has_list_slot:
        score -= 2

    if has_count_style and has_count_slot:
        score += 3
    if has_count_style and has_list_slot:
        score -= 1

    if has_list_style and not rule.is_default:
        score += 2
    if has_list_style and has_list_slot:
        score += 1

    # Avoid generic "show ..." prompts accidentally selecting *_list intents.
    if has_list_slot and not has_list_style and not has_summary_style and not has_count_style:
        score -= 1

    if has_recent_style and has_list_slot:
        score -= 1
    if has_recent_style and rule.is_default:
        score += 1

    return score


def _classify_request_style(lower_prompt: str) -> str:
    if any(marker in lower_prompt for marker in _COUNT_STYLE_MARKERS):
        return "count"
    if any(marker in lower_prompt for marker in _SUMMARY_STYLE_MARKERS):
        return "summary"
    if any(marker in lower_prompt for marker in _LIST_STYLE_MARKERS):
        return "list"
    if "recent" in lower_prompt or "latest" in lower_prompt:
        return "recent"
    return "default"


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


def _select_semantic_fallback_rule(
    rules: tuple[IntentRule, ...],
    detected_domains: list[str],
    persona_type: str,
    lower_prompt: str,
    detection_keywords: dict[str, dict[str, list[str]]],
) -> IntentRule | None:
    in_domain = [
        rule
        for rule in rules
        if rule.domain in detected_domains and _persona_matches(rule, persona_type)
    ]
    candidates = in_domain or [
        rule for rule in rules if _persona_matches(rule, persona_type)
    ]
    if not candidates:
        return None

    best_rule: IntentRule | None = None
    best_score: tuple[int, int, int, int, int] | None = None
    for candidate in candidates:
        semantic_overlap = _semantic_overlap_score(
            lower_prompt,
            candidate,
            detection_keywords,
        )
        if semantic_overlap == 0:
            continue

        detection_matches = _detection_keyword_match_count(
            lower_prompt=lower_prompt,
            intent_name=candidate.name,
            detection_keywords=detection_keywords,
        )
        keyword_matches, _ = _keyword_match_stats(lower_prompt, candidate.keywords)

        score = (
            semantic_overlap,
            detection_matches,
            keyword_matches,
            _intent_style_score(lower_prompt, candidate),
            -candidate.priority,
        )
        if best_score is None or score > best_score:
            best_score = score
            best_rule = candidate

    return best_rule


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

        semantic_overlap = _semantic_overlap_score(
            lower_prompt,
            candidate,
            detection_keywords,
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
            _intent_style_score(lower_prompt, candidate),
            match_count,
            semantic_overlap,
            1 if candidate.is_default else 0,
            -first_index,
            -candidate.priority,
            len(candidate.keywords),
        )

        if best_score is None or candidate_score > best_score:
            best_score = candidate_score
            rule = candidate

    # If no specific rule matched, choose a safe fallback from configured rules.
    if rule is None:
        semantic_rule = _select_semantic_fallback_rule(
            rules=rules,
            detected_domains=detected_domains,
            persona_type=persona_type,
            lower_prompt=lower_prompt,
            detection_keywords=detection_keywords,
        )
        rule = semantic_rule or _select_fallback_rule(
            rules,
            detected_domains,
            persona_type,
        )

    return _build_intent(
        rule,
        raw_prompt,
        sanitized_prompt,
        aliased_prompt,
        detected_domains,
        lower_prompt,
        persona_type,
    )


def _build_intent(
    rule: IntentRule,
    raw_prompt: str,
    sanitized_prompt: str,
    aliased_prompt: str,
    detected_domains: list[str],
    lower_prompt: str,
    persona_type: str,
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
        persona_type=persona_type,
        request_style=_classify_request_style(lower_prompt),
        persona_types=rule.persona_types,
        raw_prompt=raw_prompt,
        sanitized_prompt=sanitized_prompt,
        aliased_prompt=aliased_prompt,
        filters=filters,
        aggregation=aggregation,
        slot_keys=list(rule.slot_keys),
        detected_domains=detected_domains,
    )
