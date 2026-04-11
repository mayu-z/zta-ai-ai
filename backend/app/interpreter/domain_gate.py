from __future__ import annotations

import re

from app.core.exceptions import AuthorizationError, ValidationError

# Modifier keywords - only trigger campus domain when no explicit domain is found
AGGREGATION_MODIFIERS: tuple[str, ...] = (
    "kpi",
    "aggregate",
    "summary",
    "trend",
    "overview",
    "metrics",
)


def _keyword_pattern(keyword: str) -> str:
    normalized = keyword.strip().lower()
    if not normalized:
        return r"$^"

    # Keep phrase matching strict; only expand light morphology for single words.
    if " " in normalized:
        return rf"\b{re.escape(normalized)}\b"

    if re.fullmatch(r"[a-z]+", normalized):
        if normalized.endswith("ies") or normalized.endswith("ses"):
            return rf"\b{re.escape(normalized)}\b"
        if normalized.endswith("y") and len(normalized) > 3:
            stem = re.escape(normalized[:-1])
            return rf"\b(?:{re.escape(normalized)}|{stem}ies)\b"
        if normalized.endswith("s"):
            return rf"\b{re.escape(normalized)}\b"
        return rf"\b{re.escape(normalized)}(?:s|es)?\b"

    return rf"\b{re.escape(normalized)}\b"


def _keyword_matches(prompt: str, keyword: str) -> bool:
    return bool(re.search(_keyword_pattern(keyword), prompt))


def normalize_domain(domain: str) -> str:
    if "_" in domain:
        return domain.split("_", 1)[0]
    return domain


def detect_domains(
    prompt: str,
    domain_keywords: dict[str, tuple[str, ...]],
    aggregation_modifiers: tuple[str, ...] | None = None,
    persona_type: str | None = None,
) -> list[str]:
    lower_prompt = prompt.lower()
    detected: list[str] = []
    if not domain_keywords:
        raise ValidationError(
            message="No domain keyword configuration is available",
            code="DOMAIN_KEYWORDS_NOT_CONFIGURED",
        )
    aggregation_modifiers = aggregation_modifiers or AGGREGATION_MODIFIERS

    # First pass: detect explicit domain keywords
    for domain, keywords in domain_keywords.items():
        for keyword in keywords:
            if _keyword_matches(lower_prompt, keyword):
                detected.append(domain)
                break

    explicit_campus_markers = (
        "campus",
        "cross campus",
        "nationwide",
        "institution-wide",
        "institution wide",
        "all institutions",
    )
    campus_metric_markers = (
        "enrollment",
        "headcount",
        "institution",
        "demographics",
        "hbcu",
        "public",
        "private",
        "size distribution",
    )

    # Second pass: if no explicit domain found but aggregation modifiers are present,
    # only infer campus for executive/admin-style prompts or explicit campus wording.
    if not detected:
        has_aggregation_modifier = any(
            _keyword_matches(lower_prompt, mod)
            for mod in aggregation_modifiers
        )
        if has_aggregation_modifier:
            if any(_keyword_matches(lower_prompt, marker) for marker in explicit_campus_markers):
                detected = ["campus"]
            elif persona_type in {"executive", "it_head", "it_admin"}:
                detected = ["campus"]

    # If campus was inferred from broad KPI language but another explicit domain is
    # present, prefer the explicit domain unless the prompt explicitly asks campus-wide.
    if "campus" in detected and len(detected) > 1:
        has_explicit_campus = any(
            _keyword_matches(lower_prompt, marker) for marker in explicit_campus_markers
        )
        has_campus_metric_signal = any(
            _keyword_matches(lower_prompt, marker) for marker in campus_metric_markers
        )
        if not has_explicit_campus and not has_campus_metric_signal:
            detected = [domain for domain in detected if domain != "campus"]

    return sorted(set(detected))


def is_domain_allowed(domain: str, allowed_domains: list[str]) -> bool:
    canonical = normalize_domain(domain)
    return any(normalize_domain(allowed) == canonical for allowed in allowed_domains)


def enforce_domain_gate(
    detected_domains: list[str], allowed_domains: list[str]
) -> None:
    blocked = [
        domain
        for domain in detected_domains
        if not is_domain_allowed(domain, allowed_domains)
    ]
    if blocked:
        allowed_display = ", ".join(sorted(set(allowed_domains))) or "none"
        raise AuthorizationError(
            message=(
                f"Out-of-scope domain(s): {', '.join(blocked)}. "
                f"Allowed domains for your role: {allowed_display}."
            ),
            code="DOMAIN_FORBIDDEN",
        )
