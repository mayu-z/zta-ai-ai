from __future__ import annotations

import re

from app.core.exceptions import ValidationError

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+previous\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+all\s+above", re.IGNORECASE),
    re.compile(r"you\s+are\s+now", re.IGNORECASE),
    re.compile(r"reveal\s+system\s+prompt", re.IGNORECASE),
    re.compile(r"print\s+the\s+hidden\s+instructions", re.IGNORECASE),
    re.compile(r"developer\s+message", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"\bdan\b", re.IGNORECASE),
    re.compile(r"base64", re.IGNORECASE),
    re.compile(r"drop\s+table", re.IGNORECASE),
]


def sanitize_prompt(prompt: str) -> tuple[str, list[str]]:
    stripped = " ".join(prompt.split())
    if not stripped:
        raise ValidationError(message="Prompt is empty", code="EMPTY_PROMPT")

    removed: list[str] = []
    sanitized = stripped

    for pattern in INJECTION_PATTERNS:
        if pattern.search(sanitized):
            removed.append(pattern.pattern)
            sanitized = pattern.sub("", sanitized)

    sanitized = re.sub(r"[\x00-\x1F\x7F]", "", sanitized).strip()
    if not sanitized:
        raise ValidationError(
            message="Prompt became empty after sanitization", code="PROMPT_BLOCKED"
        )

    if len(sanitized) > 500:
        sanitized = sanitized[:500]

    return sanitized, removed
